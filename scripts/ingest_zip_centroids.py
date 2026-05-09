"""Ingest ZIP/ZCTA centroids for the public map's offline ZIP search.

Default source is the Census 2024 national ZCTA Gazetteer ZIP. Operator CSV
overrides can use either Census-style columns (`GEOID`, `INTPTLAT`,
`INTPTLONG`) or SimpleMaps-style columns (`zip`, `lat`, `lng`, `city`,
`state_id`, `county_fips`).

Run:
    python scripts/ingest_zip_centroids.py
    python scripts/ingest_zip_centroids.py --input data/external/uszips.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import upsert_zip_centroid  # noqa: E402
from src.ingest_common import emit_summary, resolve_or_download, run_ingest  # noqa: E402


SOURCE_KEY = "census_zcta_gazetteer"
DISPLAY_NAME = "Census ZCTA centroids"
DEFAULT_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_zcta_national.zip"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional CSV/TXT/ZIP override. Defaults to Census 2024 ZCTA Gazetteer.",
    )
    parser.add_argument(
        "--source-key",
        default=SOURCE_KEY,
        help=f"data_source_status key (default: {SOURCE_KEY}).",
    )
    parser.add_argument(
        "--source",
        default="census:zcta_gazetteer_2024",
        help="Source label written to zip_centroids.source.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row cap for smoke tests.",
    )
    return parser.parse_args()


def _rows_from_path(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            members = [name for name in zf.namelist() if name.lower().endswith((".txt", ".csv"))]
            if not members:
                raise ValueError(f"{path} contains no CSV/TXT member")
            with zf.open(members[0]) as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
                return list(_dict_rows(text))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(_dict_rows(handle))


def _dict_rows(handle: io.TextIOBase) -> list[dict[str, str]]:
    sample = handle.read(2048)
    handle.seek(0)
    delimiter = "\t" if "\t" in sample else ","
    reader = csv.DictReader(handle, delimiter=delimiter)
    return [
        {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k is not None}
        for row in reader
    ]


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key.lower())
        if value:
            return value
    return ""


def _coerce_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ingest_file(conn, path: Path, *, source: str, limit: int | None = None) -> int:
    written = 0
    for row in _rows_from_path(path):
        if limit is not None and written >= limit:
            break
        zip_code = re.sub(r"\D", "", _first(row, "zip", "zipcode", "zcta5", "geoid", "zcta5ce20"))[:5]
        lat = _coerce_float(_first(row, "lat", "latitude", "intptlat"))
        lon = _coerce_float(_first(row, "lng", "lon", "longitude", "intptlong"))
        if len(zip_code) != 5 or lat is None or lon is None:
            continue
        upsert_zip_centroid(
            conn,
            zip_code=zip_code,
            lat=lat,
            lon=lon,
            city=_first(row, "city", "postal_city") or None,
            state=_first(row, "state_id", "state", "state_code") or None,
            county_fips=_first(row, "county_fips", "countyfips") or None,
            source=source,
        )
        written += 1
    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    input_path = resolve_or_download(
        source_key=args.source_key,
        default_url=DEFAULT_URL,
        user_input=args.input,
        filename="2024_Gaz_zcta_national.zip",
    )

    def work(conn) -> int:
        return ingest_file(conn, input_path, source=args.source, limit=args.limit)

    rows = run_ingest(
        source_key=args.source_key,
        display_name=DISPLAY_NAME,
        category="geocoding",
        work=work,
        database_path=cfg.database_path,
        notes=f"input={input_path.name}; source={args.source}",
    )
    emit_summary(args.source_key, rows, notes=f"from {input_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
