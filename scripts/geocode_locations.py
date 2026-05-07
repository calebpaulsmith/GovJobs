"""Backfill `locations_geocoded` from a SimpleMaps US Cities CSV.

The SimpleMaps US Cities Basic dataset (CC-BY 4.0) is the source of truth
for (city, state) -> (lat, lon) lookups consumed by the public map export.
Download `uscities.csv` from <https://simplemaps.com/data/us-cities> and pass
its path to this script.

The CSV is expected to have at least the columns: `city`, `state_id`, `lat`,
`lng`, and `county_fips`. Extra columns are ignored. State centroids are
already seeded by `src.database.init_schema`; this script adds the city-level
rows on top.

Run:
    python scripts/geocode_locations.py --csv data/external/uscities.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import (  # noqa: E402
    connect,
    init_schema,
    upsert_geocoded_location,
)


REQUIRED_COLUMNS = {"city", "state_id", "lat", "lng"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the SimpleMaps `uscities.csv` file.",
    )
    parser.add_argument(
        "--source",
        default="simplemaps",
        help="Source label written to locations_geocoded.source (default: simplemaps).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row cap for smoke-testing.",
    )
    return parser.parse_args()


def _coerce_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def backfill(csv_path: Path, source: str, limit: int | None = None) -> tuple[int, int]:
    """Read the CSV and upsert each city row. Returns (rows_seen, rows_written)."""
    cfg = load_config()
    conn = connect(cfg.database_path)
    init_schema(conn)

    rows_seen = 0
    rows_written = 0
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"CSV missing required columns: {sorted(missing)}. "
                f"Got: {reader.fieldnames!r}"
            )
        for row in reader:
            rows_seen += 1
            if limit is not None and rows_written >= limit:
                break
            city = (row.get("city") or "").strip()
            state = (row.get("state_id") or "").strip()
            lat = _coerce_float(row.get("lat"))
            lon = _coerce_float(row.get("lng"))
            if not city or not state or lat is None or lon is None:
                continue
            upsert_geocoded_location(
                conn,
                city=city,
                state=state,
                lat=lat,
                lon=lon,
                county_fips=(row.get("county_fips") or "").strip() or None,
                geo_quality="city",
                source=source,
            )
            rows_written += 1
    conn.commit()
    conn.close()
    return rows_seen, rows_written


def main() -> int:
    args = _parse_args()
    if not args.csv.exists():
        print(f"ERROR: CSV not found at {args.csv}")
        return 1
    rows_seen, rows_written = backfill(args.csv, args.source, args.limit)
    print(f"Read {rows_seen:,} rows; geocoded {rows_written:,} (city, state) pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
