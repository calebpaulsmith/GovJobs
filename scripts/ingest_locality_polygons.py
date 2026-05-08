"""Ingest locality pay area polygons.

Per ADR-0019 this script has two paths:

1. **Primary** — fetch the public OPM-themed FeatureServer maintained on
   ArcGIS Online and convert each polygon to GeoJSON.
2. **Fallback** — when the FeatureServer is unreachable or wrong-year, build
   each polygon by dissolving Census county geometries grouped by the
   ``locality_pay_counties`` membership table for the requested year.

The fallback requires both ``ingest_county_polygons.py`` and
``ingest_locality_definitions.py`` to have run successfully.

Either path writes a per-locality GeoJSON to
``data/external/locality_polygons/{year}/{code}.geojson`` and stores the
relative path on ``locality_pay_areas.polygon_path``.

Run:
    python scripts/ingest_locality_polygons.py --year 2026
    python scripts/ingest_locality_polygons.py --year 2026 --force-fallback
    python scripts/ingest_locality_polygons.py --year 2026 --input local.geojson
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import requests  # noqa: E402

from config import load_config  # noqa: E402
from src.database import utc_now  # noqa: E402
from src.ingest_common import (  # noqa: E402
    emit_summary,
    load_geojson_input,
    relative_to_repo,
    run_ingest,
    stash_geojson_feature,
)

SOURCE_KEY = "opm_locality_polygons"
DISPLAY_NAME = "OPM locality pay polygons"
CATEGORY = "geometry"
DEFAULT_OUTPUT = REPO / "data" / "external" / "locality_polygons"

# Per ADR-0019: this is the public FeatureServer endpoint we discovered.
DEFAULT_FEATURESERVICE_URL = (
    "https://services1.arcgis.com/cc7nIINtrZ67dyVJ/arcgis/rest/services/"
    "Locality_Pay_Areas/FeatureServer/1/query"
)


def _resolve_year(conn: sqlite3.Connection, requested: int | None) -> int:
    """Resolve which year to ingest polygons for.

    If ``requested`` is given, use it. Otherwise pick the most recent year
    present in ``locality_pay_counties`` (the canonical membership table per
    ADR-0019). Falls back to the current calendar year only when that table
    is empty — that situation will fail the dissolve path with a clear error.
    """
    if requested is not None:
        return int(requested)
    row = conn.execute(
        "SELECT MAX(year) AS y FROM locality_pay_counties"
    ).fetchone()
    if row and row["y"] is not None:
        return int(row["y"])
    import datetime as _dt

    return _dt.date.today().year


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help=(
            "Year of locality definitions to use. When omitted, picks the "
            "most recent year present in locality_pay_counties (per ADR-0027)."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional local GeoJSON FeatureCollection to ingest in lieu of "
            "fetching the FeatureServer."
        ),
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Skip the FeatureServer entirely and use the county-dissolve fallback.",
    )
    parser.add_argument(
        "--featureserver-url",
        default=DEFAULT_FEATURESERVICE_URL,
    )
    parser.add_argument(
        "--code-property",
        default="locality_code",
        help=(
            "Property name on each FeatureServer feature that holds the "
            "OPM locality code (e.g. 'CHI'). Adjust if the upstream layer "
            "renames its fields."
        ),
    )
    parser.add_argument(
        "--name-property",
        default="locality_name",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument("--source", default="opm_arcgis")
    return parser.parse_args()


# ---------- FeatureServer fetch --------------------------------------------


def fetch_feature_collection(url: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Pull a FeatureCollection from an ArcGIS REST FeatureServer.

    Returns a GeoJSON FeatureCollection. The FeatureServer is asked for
    ``f=geojson`` which most modern Esri services support; if the service
    refuses, a ValueError is raised so the caller can choose to fall back.
    """
    if dry_run:
        return {"type": "FeatureCollection", "features": []}
    params = {
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError(
            f"FeatureServer at {url} did not return a GeoJSON FeatureCollection"
        )
    return payload


# ---------- County-dissolve fallback ---------------------------------------


def _read_geometry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        feature = json.load(handle)
    geom = feature.get("geometry") if isinstance(feature, dict) else None
    if not geom or geom.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"unexpected geometry in {path}")
    return geom


def _merge_geometries(geoms: list[dict[str, Any]]) -> dict[str, Any]:
    """Approximate dissolve: union as a MultiPolygon without simplification.

    SQLite has no GIS support and we don't want a heavy GeoPandas/Shapely
    dependency. The export pipeline can simplify later. For V1 this gives
    callable geometry; visual quality is acceptable because TIGER counties
    already share borders.
    """
    polygons: list[Any] = []
    for geom in geoms:
        if geom["type"] == "Polygon":
            polygons.append(geom["coordinates"])
        elif geom["type"] == "MultiPolygon":
            polygons.extend(geom["coordinates"])
    return {"type": "MultiPolygon", "coordinates": polygons}


def build_locality_polygons_via_dissolve(
    conn: sqlite3.Connection,
    *,
    year: int,
    output_dir: Path,
    source: str,
) -> dict[str, dict[str, Any]]:
    """Build {locality_code: {feature, name}} by dissolving member counties."""
    rows = conn.execute(
        """
        SELECT lpc.locality_code, lpc.county_fips, c.polygon_path,
               COALESCE(lpa.name, lpc.locality_code) AS name
        FROM locality_pay_counties lpc
        JOIN counties c ON c.fips = lpc.county_fips
        LEFT JOIN locality_pay_areas lpa
          ON lpa.code = lpc.locality_code AND lpa.year = lpc.year
        WHERE lpc.year = ?
        """,
        (year,),
    ).fetchall()
    if not rows:
        raise RuntimeError(
            f"No locality-county pairs found for year {year}; "
            "run ingest_locality_definitions.py and ingest_county_polygons.py first."
        )
    by_code: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    missing_polys = 0
    for row in rows:
        code = row["locality_code"]
        names.setdefault(code, row["name"])
        path = REPO / row["polygon_path"] if row["polygon_path"] else None
        if not path or not path.exists():
            missing_polys += 1
            continue
        try:
            geom = _read_geometry(path)
        except ValueError:
            missing_polys += 1
            continue
        by_code.setdefault(code, []).append(geom)
    output: dict[str, dict[str, Any]] = {}
    for code, geoms in by_code.items():
        merged = _merge_geometries(geoms)
        feature = {
            "type": "Feature",
            "properties": {"locality_code": code, "locality_name": names[code]},
            "geometry": merged,
        }
        output[code] = {"feature": feature, "name": names[code]}
    if missing_polys:
        sys.stderr.write(
            f"warning: {missing_polys} member counties had no polygon on disk\n"
        )
    return output


# ---------- Common write step ----------------------------------------------


def write_locality_polygon(
    conn: sqlite3.Connection,
    *,
    code: str,
    name: str,
    feature: dict[str, Any],
    year: int,
    output_dir: Path,
    source: str,
) -> None:
    target_dir = output_dir / str(year)
    path = stash_geojson_feature(
        feature,
        output_dir=target_dir,
        filename=f"{code}.geojson",
    )
    relative = relative_to_repo(path, REPO)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO locality_pay_areas (
            code, year, name, description, adjustment_pct,
            polygon_path, source, source_url, imported_at
        )
        VALUES (?, ?, ?, NULL, COALESCE((
            SELECT adjustment_pct FROM locality_pay_areas WHERE code=? AND year=?
        ), 0), ?, ?, NULL, ?)
        ON CONFLICT(code, year) DO UPDATE SET
            polygon_path=excluded.polygon_path,
            source=excluded.source,
            imported_at=excluded.imported_at
        """,
        (code, year, name, code, year, relative, source, now),
    )


def import_polygons(
    conn: sqlite3.Connection,
    *,
    year: int,
    fc: dict[str, Any],
    code_property: str,
    name_property: str,
    output_dir: Path,
    source: str,
) -> int:
    written = 0
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        code = (props.get(code_property) or "").strip().upper()
        name = (props.get(name_property) or "").strip() or code
        if not code:
            continue
        write_locality_polygon(
            conn,
            code=code,
            name=name,
            feature=feature,
            year=year,
            output_dir=output_dir,
            source=source,
        )
        written += 1
    conn.commit()
    return written


def import_polygons_via_dissolve(
    conn: sqlite3.Connection,
    *,
    year: int,
    output_dir: Path,
) -> int:
    built = build_locality_polygons_via_dissolve(
        conn, year=year, output_dir=output_dir, source="dissolve"
    )
    written = 0
    for code, info in built.items():
        write_locality_polygon(
            conn,
            code=code,
            name=info["name"],
            feature=info["feature"],
            year=year,
            output_dir=output_dir,
            source="dissolve:counties",
        )
        written += 1
    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    notes_parts: list[str] = []

    def work(conn: sqlite3.Connection) -> int:
        year = _resolve_year(conn, args.year)
        notes_parts.append(f"year={year}")
        if args.input:
            if not args.input.exists():
                raise FileNotFoundError(f"input not found at {args.input}")
            fc = load_geojson_input(args.input)
            notes_parts.append("path=local")
            return import_polygons(
                conn,
                year=year,
                fc=fc,
                code_property=args.code_property,
                name_property=args.name_property,
                output_dir=args.output_dir,
                source="opm_arcgis_local",
            )
        if not args.force_fallback:
            try:
                fc = fetch_feature_collection(args.featureserver_url)
                written = import_polygons(
                    conn,
                    year=year,
                    fc=fc,
                    code_property=args.code_property,
                    name_property=args.name_property,
                    output_dir=args.output_dir,
                    source="opm_arcgis",
                )
                if written > 0:
                    notes_parts.append("path=arcgis")
                    return written
                # ArcGIS returned features but none had a recognized
                # `locality_code` — fall through to the dissolve path so
                # we never silently land at zero polygons.
                notes_parts.append("arcgis_zero_recognized")
            except Exception as exc:
                sys.stderr.write(
                    f"FeatureServer fetch failed ({type(exc).__name__}: {exc}); "
                    "falling back to county dissolve.\n"
                )
                notes_parts.append(f"arcgis_failed={type(exc).__name__}")
        notes_parts.append("path=dissolve")
        return import_polygons_via_dissolve(
            conn,
            year=year,
            output_dir=args.output_dir,
        )

    row_count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=";".join(notes_parts),
        work=work,
    )
    emit_summary(SOURCE_KEY, row_count, ";".join(notes_parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
