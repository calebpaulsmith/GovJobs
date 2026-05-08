"""Shared scaffolding for public-map ingest scripts.

Every ingest script in ``scripts/ingest_*.py`` follows the same outline:

1. Open the database, init the schema, mark the source ``begin_run``.
2. Read input — per ADR-0027, scripts default to a known canonical URL (or a
   small checked-in seed CSV) and only fall through to ``--input`` /
   ``PUBLIC_MAP_*`` env vars as overrides. ``resolve_or_download`` handles the
   discovery + cache + download flow.
3. Parse and upsert rows.
4. Mark ``complete_run`` with the row count, or ``fail_run`` with the error.
5. Close the connection.

This module wraps step 1, 4, and 5 so each script focuses on parse + upsert.
"""
from __future__ import annotations

import io
import logging
import shutil
import sqlite3
import sys
import traceback
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from src.data_source_registry import begin_run, complete_run, fail_run
from src.database import connect, init_schema

logger = logging.getLogger(__name__)

# Default cache root for downloaded ingest inputs (ADR-0027).
EXTERNAL_ROOT = Path(__file__).resolve().parents[1] / "data" / "external"
DEFAULT_HTTP_TIMEOUT = 60


def run_ingest(
    *,
    source_key: str,
    display_name: str,
    category: str,
    work: Callable[[sqlite3.Connection], int],
    database_path: Path,
    notes: str | None = None,
) -> int:
    """Run an ingest with status-registry wrapping.

    ``work`` receives an open connection and must return the row count
    written by the ingest. Exceptions inside ``work`` are recorded via
    ``fail_run`` and re-raised so the orchestrator can decide what to do.
    """
    conn = connect(database_path)
    init_schema(conn)
    begin_run(conn, source_key, display_name, category)
    try:
        row_count = work(conn)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        fail_run(conn, source_key, message)
        logger.exception("ingest failed: %s", source_key)
        conn.close()
        raise
    complete_run(conn, source_key, row_count=row_count, notes=notes)
    conn.close()
    return row_count


def emit_summary(source_key: str, row_count: int, notes: str | None = None) -> None:
    """Pretty CLI line — scripts call this from main()."""
    parts = [f"[{source_key}] wrote {row_count:,} rows"]
    if notes:
        parts.append(f"({notes})")
    sys.stdout.write(" ".join(parts) + "\n")
    sys.stdout.flush()


def relative_to_repo(path: Path, repo: Path) -> str:
    """Return ``path`` as a repo-relative POSIX string when possible.

    Falls back to the absolute string when ``path`` is outside ``repo``
    (e.g. inside a pytest tmp_path). The exporter and admin UI both join
    the path against REPO at read time, so this handles either case.
    """
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def stash_geojson_feature(
    feature: dict[str, Any],
    *,
    output_dir: Path,
    filename: str,
) -> Path:
    """Write one GeoJSON feature (or geometry) to disk and return the path.

    Used by polygon ingests so the SQLite row stores only ``polygon_path``,
    not the polygon blob itself.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename
    if isinstance(feature, dict) and feature.get("type") in {"Polygon", "MultiPolygon"}:
        # Wrap a bare geometry in a Feature for consistency.
        payload: dict[str, Any] = {"type": "Feature", "properties": {}, "geometry": feature}
    else:
        payload = feature
    import json as _json

    with target.open("w", encoding="utf-8") as handle:
        _json.dump(payload, handle, separators=(",", ":"))
    return target


def load_geojson_input(path: Path) -> dict[str, Any]:
    """Read a local GeoJSON file. Raises ValueError on bad input."""
    import json as _json

    with path.open("r", encoding="utf-8") as handle:
        data = _json.load(handle)
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(
            f"{path} is not a GeoJSON FeatureCollection (type={data.get('type')!r})"
        )
    if "features" not in data:
        raise ValueError(f"{path} FeatureCollection has no 'features' array")
    return data


def trace_for_status() -> str:
    """Truncated traceback string for storage in data_source_status.last_error."""
    return traceback.format_exc()[-1900:]


# ---------- Self-bootstrapping ingest helpers (ADR-0027) ---------------------


def resolve_or_download(
    *,
    source_key: str,
    default_url: str | None,
    cache_dir: Path | None = None,
    filename: str | None = None,
    user_input: Path | None = None,
    seed_path: Path | None = None,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> Path:
    """Resolve an ingest input path with this priority (per ADR-0027):

    1. ``user_input`` if provided (operator override via ``--input`` or env var).
    2. A cached copy under ``cache_dir`` (defaults to
       ``data/external/<source_key>/``) named ``filename`` (or the URL's
       basename) — used on every run after the first network fetch.
    3. ``seed_path`` — a small public-domain CSV checked into the repo. Used
       for sources that publish only HTML pages (e.g. OPM locality definitions)
       where there is no stable machine-readable URL.
    4. ``default_url`` — downloaded with ``requests.get`` and cached. Raises
       ``RuntimeError`` if the download fails so the registry's ``fail_run``
       captures the error.

    Returns the local path the caller can read from.
    """
    if user_input is not None:
        if not user_input.exists():
            raise FileNotFoundError(
                f"[{source_key}] --input path does not exist: {user_input}"
            )
        return user_input

    cache_dir = cache_dir or (EXTERNAL_ROOT / source_key)
    cache_dir.mkdir(parents=True, exist_ok=True)

    name = filename
    if name is None and default_url:
        name = default_url.rsplit("/", 1)[-1]
    if name is None and seed_path is not None:
        name = seed_path.name
    if name is None:
        raise ValueError(
            f"[{source_key}] resolve_or_download needs a filename, default_url, "
            "or seed_path"
        )

    cached = cache_dir / name
    if cached.exists() and cached.stat().st_size > 0:
        logger.debug("[%s] using cached input: %s", source_key, cached)
        return cached

    if seed_path is not None and seed_path.exists():
        logger.info("[%s] copying seed CSV into cache: %s", source_key, seed_path)
        shutil.copyfile(seed_path, cached)
        return cached

    if not default_url:
        raise RuntimeError(
            f"[{source_key}] no cached input, no seed CSV, and no default URL "
            "to fall back on. Provide --input or set the env var."
        )

    logger.info("[%s] downloading default source: %s", source_key, default_url)
    response = requests.get(default_url, timeout=timeout, stream=True)
    response.raise_for_status()
    with cached.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if chunk:
                handle.write(chunk)
    logger.info(
        "[%s] cached %d bytes at %s",
        source_key,
        cached.stat().st_size,
        cached,
    )
    return cached


def shapefile_zip_to_geojson(
    zip_path: Path,
    *,
    properties_to_keep: set[str] | None = None,
) -> dict[str, Any]:
    """Convert a Census TIGER cartographic-boundary ZIP to GeoJSON.

    Census CB ZIPs ship .shp/.shx/.dbf/.prj together. They're already in WGS84
    (EPSG:4326), so no reprojection is required. We use ``pyshp`` (pure-Python,
    no GDAL dependency) to read the shapefile and emit a FeatureCollection.

    ``properties_to_keep`` (when given) filters per-feature attributes to a
    small set so downstream files stay compact. ``None`` keeps everything.
    """
    try:
        import shapefile  # pyshp
    except ImportError as exc:  # pragma: no cover — covered indirectly by tests
        raise RuntimeError(
            "pyshp is required for shapefile→GeoJSON conversion. "
            "Run `pip install -r requirements.txt`."
        ) from exc

    shp_bytes: bytes | None = None
    shx_bytes: bytes | None = None
    dbf_bytes: bytes | None = None

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            lower = member.lower()
            if lower.endswith(".shp"):
                shp_bytes = zf.read(member)
            elif lower.endswith(".shx"):
                shx_bytes = zf.read(member)
            elif lower.endswith(".dbf"):
                dbf_bytes = zf.read(member)

    if shp_bytes is None or shx_bytes is None or dbf_bytes is None:
        raise ValueError(f"{zip_path} is missing required shapefile members")

    reader = shapefile.Reader(
        shp=io.BytesIO(shp_bytes),
        shx=io.BytesIO(shx_bytes),
        dbf=io.BytesIO(dbf_bytes),
    )
    features: list[dict[str, Any]] = []
    field_names = [f[0] for f in reader.fields if f[0] != "DeletionFlag"]
    for record in reader.shapeRecords():
        geometry = record.shape.__geo_interface__
        attrs: dict[str, Any] = dict(zip(field_names, list(record.record)))
        if properties_to_keep is not None:
            attrs = {k: v for k, v in attrs.items() if k in properties_to_keep}
        features.append(
            {"type": "Feature", "geometry": geometry, "properties": attrs}
        )
    reader.close()
    return {"type": "FeatureCollection", "features": features}


def write_geojson(payload: dict[str, Any], target: Path) -> Path:
    """Write a GeoJSON FeatureCollection (or geometry) to ``target``."""
    import json as _json

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        _json.dump(payload, handle, separators=(",", ":"))
    return target


def ensure_geojson_input(
    *,
    source_key: str,
    default_url: str,
    user_input: Path | None,
    properties_to_keep: set[str] | None = None,
    cache_dir: Path | None = None,
) -> Path:
    """One-stop helper for polygon ingests.

    Resolves the input via :func:`resolve_or_download`. If the resolved path is
    a Census TIGER ZIP, extracts and converts it to GeoJSON via
    :func:`shapefile_zip_to_geojson`, caches the GeoJSON next to the ZIP, and
    returns that GeoJSON path. If the resolved path is already GeoJSON, returns
    it unchanged.
    """
    input_path = resolve_or_download(
        source_key=source_key,
        default_url=default_url,
        user_input=user_input,
        cache_dir=cache_dir,
    )
    if input_path.suffix.lower() != ".zip":
        return input_path

    geojson_path = input_path.with_suffix(".geojson")
    if geojson_path.exists() and geojson_path.stat().st_size > 0:
        return geojson_path
    payload = shapefile_zip_to_geojson(
        input_path, properties_to_keep=properties_to_keep
    )
    write_geojson(payload, geojson_path)
    return geojson_path
