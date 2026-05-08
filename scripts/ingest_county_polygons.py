"""Ingest US county polygons into the ``counties`` table.

Source: Census TIGER cartographic boundary file. By default the script
downloads ``cb_2023_us_county_500k.zip`` (~3,200 counties, 1:500,000) from
the Census public CDN, converts it to GeoJSON via ``pyshp``, and caches both
files under ``data/external/census_counties/``. Pass ``--input`` to override
with a local GeoJSON or shapefile ZIP. Per ADR-0027, the script runs
end-to-end from a clean checkout with no environment variables.

Expected feature properties: ``GEOID`` (5-digit county FIPS) and ``NAME``.
``STATEFP`` is used to derive the 2-letter state when ``STUSPS`` isn't
present, via a small static map.

Run:
    python scripts/ingest_county_polygons.py
    python scripts/ingest_county_polygons.py --input data/external/my_counties.geojson
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

SOURCE_KEY = "census_counties"
DISPLAY_NAME = "Census county polygons"
CATEGORY = "geometry"
DEFAULT_OUTPUT = REPO / "data" / "external" / "county_polygons"
DEFAULT_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
)
KEEP_PROPERTIES = {"GEOID", "NAME", "STATEFP", "STUSPS", "CBSAFP", "STATE_NAME"}

STATE_FP_TO_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
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


def import_counties_from_geojson(
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
        fips = _props_value(props, "GEOID", "geoid", "FIPS", "fips")
        name = _props_value(props, "NAME", "name")
        statefp = _props_value(props, "STATEFP", "statefp")
        usps = _props_value(props, "STUSPS", "stusps")
        if not fips or not name:
            continue
        if not usps and statefp and statefp in STATE_FP_TO_USPS:
            usps = STATE_FP_TO_USPS[statefp]
        if not usps:
            continue
        cbsa = _props_value(props, "CBSAFP", "cbsafp", "CBSA_CODE")
        path = stash_geojson_feature(
            feature,
            output_dir=output_dir,
            filename=f"{fips}.geojson",
        )
        relative = relative_to_repo(path, REPO)
        conn.execute(
            """
            INSERT INTO counties (fips, name, state, cbsa_code, polygon_path, source, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fips) DO UPDATE SET
                name=excluded.name,
                state=excluded.state,
                cbsa_code=excluded.cbsa_code,
                polygon_path=excluded.polygon_path,
                source=excluded.source,
                imported_at=excluded.imported_at
            """,
            (fips, name, usps.upper(), cbsa, relative, source, now),
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
        work=lambda conn: import_counties_from_geojson(
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
