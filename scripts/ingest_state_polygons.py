"""Ingest US state polygons into the ``state_polygons`` table.

Source: Census TIGER cartographic boundary file. By default the script
downloads the 1:5,000,000 ``cb_2023_us_state_5m.zip`` shapefile from the
Census public CDN, converts it to GeoJSON in pure Python via ``pyshp``, and
caches both files under ``data/external/census_states/``. Pass ``--input`` to
override with a local GeoJSON or shapefile ZIP. Per ADR-0027, the script runs
end-to-end from a clean checkout with no environment variables.

Expected feature properties (case-insensitive): ``STUSPS`` (2-letter state
code) and ``NAME``.

Run:
    python scripts/ingest_state_polygons.py
    python scripts/ingest_state_polygons.py --input data/external/my_states.geojson
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


SOURCE_KEY = "census_states"
DISPLAY_NAME = "Census state polygons"
CATEGORY = "geometry"
DEFAULT_OUTPUT = REPO / "data" / "external" / "state_polygons"
DEFAULT_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_5m.zip"
)
KEEP_PROPERTIES = {"STUSPS", "NAME", "GEOID", "STATEFP"}


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
        work=lambda conn: import_states_from_geojson(
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
