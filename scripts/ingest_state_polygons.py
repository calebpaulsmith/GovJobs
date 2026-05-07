"""Ingest US state polygons into the ``state_polygons`` table.

Source: Census TIGER cartographic boundary GeoJSON. The Census Bureau
publishes shapefiles natively; convert once with mapshaper, QGIS, or
``ogr2ogr`` and pass the resulting GeoJSON via ``--input``.

Expected feature properties (case-insensitive): ``STUSPS`` (2-letter state
code) and ``NAME``. Other property names are accepted as fallbacks.

Run:
    python scripts/ingest_state_polygons.py --input data/external/states.geojson
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
    load_geojson_input,
    relative_to_repo,
    run_ingest,
    stash_geojson_feature,
)


SOURCE_KEY = "census_states"
DISPLAY_NAME = "Census state polygons"
CATEGORY = "geometry"
DEFAULT_OUTPUT = REPO / "data" / "external" / "state_polygons"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="GeoJSON FeatureCollection of state polygons.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Directory where per-state GeoJSON files are written "
            f"(default: {DEFAULT_OUTPUT.relative_to(REPO)})."
        ),
    )
    parser.add_argument(
        "--source",
        default="census:tiger",
        help="Source label written to state_polygons.source.",
    )
    return parser.parse_args()


def _state_code(props: dict) -> str | None:
    for key in ("STUSPS", "stusps", "STATE", "state", "STATE_ABBR"):
        value = props.get(key)
        if value:
            return str(value).strip().upper()
    return None


def _state_name(props: dict) -> str | None:
    for key in ("NAME", "name", "STATE_NAME"):
        value = props.get(key)
        if value:
            return str(value).strip()
    return None


def import_states_from_geojson(
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
        code = _state_code(props)
        name = _state_name(props)
        if not code or not name:
            continue
        path = stash_geojson_feature(
            feature,
            output_dir=output_dir,
            filename=f"{code}.geojson",
        )
        relative = relative_to_repo(path, REPO)
        conn.execute(
            """
            INSERT INTO state_polygons (state, name, polygon_path, source, imported_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(state) DO UPDATE SET
                name=excluded.name,
                polygon_path=excluded.polygon_path,
                source=excluded.source,
                imported_at=excluded.imported_at
            """,
            (code, name, relative, source, now),
        )
        written += 1
    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    if not args.input.exists():
        sys.stderr.write(f"ERROR: input not found at {args.input}\n")
        return 1
    cfg = load_config()
    row_count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=f"input={args.input.name}",
        work=lambda conn: import_states_from_geojson(
            conn,
            input_path=args.input,
            output_dir=args.output_dir,
            source=args.source,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
