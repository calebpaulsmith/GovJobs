"""Ingest GSA Federal Real Property Profile (FRPP) buildings.

Per ADR-0025 the public map renders FRPP-listed federal buildings as a
neutral-diamond marker layer at zoom >= 6 to give the user spatial context
that exists independent of any open posting. Per ADR-0027 this script is
self-bootstrapping: with no flags or env vars it falls back to the
checked-in seed CSV at ``data/external/gsa_federal_properties/seed.csv``,
which lists a representative set of well-known federal buildings (HQs,
courthouses, NIH/NASA campuses, etc.) so a clean checkout still produces a
visible layer. The operator can replace the seed with the full GSA FRPP
extract via ``--input`` once they've downloaded it.

Input format (CSV with header):

    frpp_id,name,property_type,agency,agency_code,address,city,state,zip,
    county_fips,latitude,longitude,building_status

``frpp_id``, ``name``, ``state``, ``latitude``, and ``longitude`` are
required. Anything else may be blank. ``latitude``/``longitude`` are stored
as REALs in WGS84 (EPSG:4326).

Run:
    python scripts/ingest_federal_properties.py
    python scripts/ingest_federal_properties.py --input data/external/frpp_full.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import utc_now  # noqa: E402
from src.ingest_common import emit_summary, resolve_or_download, run_ingest  # noqa: E402

SOURCE_KEY = "gsa_federal_properties"
DISPLAY_NAME = "GSA Federal Real Property Profile"
CATEGORY = "geometry"
SEED_CSV = REPO / "data" / "external" / "gsa_federal_properties" / "seed.csv"
DEFAULT_SOURCE = "gsa:frpp_seed"

REQUIRED_COLUMNS = {"frpp_id", "name", "state", "latitude", "longitude"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional CSV with FRPP rows. When omitted, falls back to the "
            f"checked-in seed at {SEED_CSV.relative_to(REPO).as_posix()} "
            "per ADR-0027."
        ),
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="Source label written to federal_properties.source.",
    )
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help=(
            "When set, deletes every existing federal_properties row before "
            "inserting. Use when re-importing the full GSA extract."
        ),
    )
    return parser.parse_args()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: str | None) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_county_fips(value: str | None) -> str | None:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(5)[:5]


def import_properties_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
    replace_all: bool,
) -> int:
    now = utc_now()
    written = 0

    if replace_all:
        conn.execute("DELETE FROM federal_properties")

    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"CSV missing required columns: {sorted(missing)}; "
                f"got {reader.fieldnames!r}"
            )
        for row in reader:
            frpp_id = _clean(row.get("frpp_id"))
            name = _clean(row.get("name"))
            state = _clean(row.get("state"))
            lat = _to_float(row.get("latitude"))
            lon = _to_float(row.get("longitude"))
            if not frpp_id or not name or not state or lat is None or lon is None:
                continue
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                continue

            conn.execute(
                """
                INSERT INTO federal_properties (
                    frpp_id, name, property_type, agency, agency_code,
                    address, city, state, zip, county_fips,
                    latitude, longitude, building_status, source, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(frpp_id) DO UPDATE SET
                    name=excluded.name,
                    property_type=excluded.property_type,
                    agency=excluded.agency,
                    agency_code=excluded.agency_code,
                    address=excluded.address,
                    city=excluded.city,
                    state=excluded.state,
                    zip=excluded.zip,
                    county_fips=excluded.county_fips,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    building_status=excluded.building_status,
                    source=excluded.source,
                    imported_at=excluded.imported_at
                """,
                (
                    frpp_id,
                    name,
                    _clean(row.get("property_type")),
                    _clean(row.get("agency")),
                    _clean(row.get("agency_code")),
                    _clean(row.get("address")),
                    _clean(row.get("city")),
                    state.upper(),
                    _clean(row.get("zip")),
                    _normalize_county_fips(row.get("county_fips")),
                    lat,
                    lon,
                    _clean(row.get("building_status")),
                    source,
                    now,
                ),
            )
            written += 1

    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    resolved = resolve_or_download(
        source_key=SOURCE_KEY,
        default_url=None,
        cache_dir=SEED_CSV.parent,
        filename=SEED_CSV.name,
        user_input=args.input,
        seed_path=SEED_CSV,
    )
    row_count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=f"input={resolved.name}",
        work=lambda conn: import_properties_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
            replace_all=args.replace_all,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
