"""Ingest Census ACS B25064 (median gross rent) into county-level COL rows.

Per `docs/PUBLIC_MAP_DATA_SOURCES.md` (`census_acs_rent`) the public map needs
finer cost-of-living context than BEA's state/CBSA RPP series. The ACS 5-year
estimate of median gross rent (table B25064) is a stable county-level proxy.

Approach (per D.5.10):
    1. Read median gross rent per county AND per state from the input CSV.
    2. For each county, look up the state's BEA RPP from
       ``cost_of_living_index`` (geo_type='state', preferring source ``bea:rpp``).
    3. Compute the county RPP as
       ``state_rpp * (county_rent / state_median_rent)``.
    4. Insert one ``cost_of_living_index`` row per county with
       ``geo_type='county'``, ``geo_code=<5-digit FIPS>``,
       ``rpp_overall=<computed>``, ``rpp_rents=<county_rent>``,
       ``source='census:acs5_b25064'``. Counties whose state has no BEA RPP
       row are skipped (the state-level fallback in the exporter still kicks
       in for those counties).

Per ADR-0027 the script is self-bootstrapping: with no ``--input`` it falls
back to a checked-in seed CSV at ``data/external/census_acs_rent/2023.csv``.

Expected CSV columns (header required, case-insensitive):
    year, geo_type, geo_code, county_name, state, median_rent

``geo_type`` is ``state`` (state postal in ``state``; ``geo_code`` matches) or
``county`` (5-digit FIPS in ``geo_code``).

Run:
    python scripts/ingest_acs_county_rents.py
    python scripts/ingest_acs_county_rents.py --input my_acs_b25064.csv
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

SOURCE_KEY = "census_acs_rent"
DISPLAY_NAME = "Census ACS county median rent (B25064)"
CATEGORY = "col"
SEED_CSV = REPO / "data" / "external" / "census_acs_rent" / "2023.csv"

REQUIRED_COLUMNS = {"year", "geo_type", "geo_code", "median_rent"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional CSV. When omitted, falls back to the checked-in seed at "
            f"{SEED_CSV.relative_to(REPO).as_posix()} per ADR-0027."
        ),
    )
    parser.add_argument("--source", default="census:acs5_b25064")
    return parser.parse_args()


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _state_rpp_lookup(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT year, geo_code, rpp_overall, source
        FROM cost_of_living_index
        WHERE geo_type='state' AND rpp_overall IS NOT NULL
        ORDER BY geo_code,
                 CASE source WHEN 'bea:rpp' THEN 0 ELSE 1 END,
                 year DESC
        """
    ).fetchall()
    out: dict[str, float] = {}
    for row in rows:
        code = (row["geo_code"] or "").strip().upper()
        if not code or code in out:
            continue
        try:
            out[code] = float(row["rpp_overall"])
        except (TypeError, ValueError):
            continue
    return out


def import_acs_rents_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
) -> int:
    """Read the CSV, derive county COL, upsert into ``cost_of_living_index``.

    Returns the number of county rows written. State rows are read for their
    median-rent values but are not inserted (BEA RPP already covers states).
    """
    state_medians: dict[str, tuple[int, float]] = {}
    county_rows: list[tuple[int, str, str, float]] = []

    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        normalized_fields = {
            (name or "").strip().lower(): name
            for name in (reader.fieldnames or [])
        }
        missing = REQUIRED_COLUMNS - set(normalized_fields)
        if missing:
            raise ValueError(
                f"CSV missing required columns: {sorted(missing)}; "
                f"got {reader.fieldnames!r}"
            )
        for row in reader:
            year_raw = row.get(normalized_fields["year"], "").strip()
            geo_type = row.get(normalized_fields["geo_type"], "").strip().lower()
            geo_code = row.get(normalized_fields["geo_code"], "").strip()
            median_rent = _to_float(row.get(normalized_fields["median_rent"], ""))
            state_field = row.get(normalized_fields.get("state", ""), "").strip().upper()
            if not year_raw or not geo_code or median_rent is None or median_rent <= 0:
                continue
            try:
                year = int(year_raw)
            except ValueError:
                continue

            if geo_type == "state":
                state_medians[geo_code.upper()] = (year, median_rent)
            elif geo_type == "county":
                fips = geo_code.zfill(5)[:5]
                if not state_field:
                    continue
                county_rows.append((year, fips, state_field, median_rent))

    state_rpp = _state_rpp_lookup(conn)
    now = utc_now()
    written = 0
    for year, fips, state_code, county_rent in county_rows:
        state_entry = state_medians.get(state_code)
        if state_entry is None:
            continue
        _state_year, state_median = state_entry
        if state_median <= 0:
            continue
        rpp = state_rpp.get(state_code)
        if rpp is None:
            continue
        county_rpp = round(rpp * (county_rent / state_median), 2)
        conn.execute(
            """
            INSERT INTO cost_of_living_index (
                year, geo_type, geo_code, rpp_overall, rpp_goods,
                rpp_services, rpp_rents, source, imported_at
            )
            VALUES (?, 'county', ?, ?, NULL, NULL, ?, ?, ?)
            ON CONFLICT(year, geo_type, geo_code, source) DO UPDATE SET
                rpp_overall=excluded.rpp_overall,
                rpp_rents=excluded.rpp_rents,
                imported_at=excluded.imported_at
            """,
            (year, fips, county_rpp, round(county_rent, 2), source, now),
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
        work=lambda conn: import_acs_rents_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
