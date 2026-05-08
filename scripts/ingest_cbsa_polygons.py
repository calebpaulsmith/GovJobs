"""Ingest CBSA (metro / micro) polygons into the ``metro_areas`` table.

Source: Census TIGER cartographic boundary file. By default the script
downloads ``cb_2023_us_cbsa_500k.zip`` (~390 metro + ~540 micro CBSAs) from
the Census public CDN, converts it to GeoJSON via ``pyshp``, and caches both
files under ``data/external/census_cbsa/``. Pass ``--input`` to override
with a local GeoJSON or shapefile ZIP. Per ADR-0027.

Expected properties: ``CBSAFP`` or ``GEOID`` (5-digit CBSA code), ``NAME``,
and either ``LSAD`` (e.g. 'M1' for metro, 'M2' for micro) or a ``CBSA_TYPE``
field. Unknown types are stored verbatim.

Run:
    python scripts/ingest_cbsa_polygons.py
    python scripts/ingest_cbsa_polygons.py --input data/external/my_cbsa.geojson
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import utc_now  # noqa: E402
from src.ingest_common import (  # noqa: E402
    emit_summary,
    ensure_geojson_input,
    load_geojson_input,
    relative_to_repo,
    run_ingest,
    stash_geojson_feature,
)

SOURCE_KEY = "census_cbsa"
DISPLAY_NAME = "Census CBSA polygons"
CATEGORY = "geometry"
DEFAULT_OUTPUT = REPO / "data" / "external" / "metro_polygons"
DEFAULT_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_cbsa_500k.zip"
)
KEEP_PROPERTIES = {"CBSAFP", "GEOID", "NAME", "NAMELSAD", "LSAD"}

LSAD_MAP = {
    "M1": "metro",
    "M2": "micro",
    "metro": "metro",
    "micro": "micro",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional local GeoJSON or Census TIGER shapefile ZIP. "
            "When omitted, the script downloads the default Census CB file."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", default="census:tiger")
    return parser.parse_args()


def _props_value(props: dict, *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value:
            return str(value).strip()
    return None


def import_cbsa_from_geojson(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    output_dir: Path,
    source: str,
) -> int:
    fc = load_geojson_input(input_path)
    now = utc_now()
    written = 0
    for feature in fc["features"]:
        props = feature.get("properties") or {}
        code = _props_value(props, "CBSAFP", "cbsafp", "GEOID", "geoid", "CBSA_CODE")
        name = _props_value(props, "NAME", "name", "NAMELSAD")
        lsad = _props_value(props, "LSAD", "lsad", "CBSA_TYPE", "cbsa_type")
        if not code or not name:
            continue
        cbsa_type = LSAD_MAP.get((lsad or "").strip()) or (lsad or "metro")
        path = stash_geojson_feature(
            feature,
            output_dir=output_dir,
            filename=f"{code}.geojson",
        )
        relative = relative_to_repo(path, REPO)
        conn.execute(
            """
            INSERT INTO metro_areas (cbsa_code, name, cbsa_type, polygon_path, source, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cbsa_code) DO UPDATE SET
                name=excluded.name,
                cbsa_type=excluded.cbsa_type,
                polygon_path=excluded.polygon_path,
                source=excluded.source,
                imported_at=excluded.imported_at
            """,
            (code, name, cbsa_type, relative, source, now),
        )
        written += 1
    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    resolved_input = ensure_geojson_input(
        source_key=SOURCE_KEY,
        default_url=DEFAULT_URL,
        user_input=args.input,
        properties_to_keep=KEEP_PROPERTIES,
    )
    row_count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=f"input={resolved_input.name}",
        work=lambda conn: import_cbsa_from_geojson(
            conn,
            input_path=resolved_input,
            output_dir=args.output_dir,
            source=args.source,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
