"""Shared scaffolding for public-map ingest scripts.

Every ingest script in ``scripts/ingest_*.py`` follows the same outline:

1. Open the database, init the schema, mark the source ``begin_run``.
2. Read input (network URL by default, or ``--input`` local file).
3. Parse and upsert rows.
4. Mark ``complete_run`` with the row count, or ``fail_run`` with the error.
5. Close the connection.

This module wraps step 1, 4, and 5 so each script focuses on parse + upsert.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.data_source_registry import begin_run, complete_run, fail_run
from src.database import connect, init_schema

logger = logging.getLogger(__name__)


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
