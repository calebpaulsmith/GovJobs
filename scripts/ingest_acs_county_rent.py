"""Ingest Census ACS county median gross rent into ``cost_of_living_index``.

D.5.10 (per ADR-0027). Adds a county-level cost-of-living signal so the
public map's CountyDetail surface and downstream consumers can show
within-state COL variation. BEA does not publish county-level RPP, so we
estimate it as::

    county_col_index = state_rpp * (county_rent / state_median_rent)

where ``state_rpp`` is the latest BEA RPP overall for the state (loaded by
``scripts/ingest_bea_rpp.py``) and ``state_median_rent`` is the median of the
county rents present in the input for the same state. With the checked-in
seed CSV (a few counties per state) the estimate is bootstrap quality; once
an operator pulls a full Census ACS B25064 county file via ``--input``, the
estimate becomes meaningful for every county in the file.

CSV schema (header required, case-insensitive)::

    year, state, county_fips, county_name, median_rent

``county_fips`` must be a 5-digit string (state FIPS + county FIPS, zero-
padded). ``state`` is the 2-letter postal code. ``median_rent`` is in
dollars (no commas, no $).

Run::

    python scripts/ingest_acs_county_rent.py
    python scripts/ingest_acs_county_rent.py --input data/external/acs_b25064_2023.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import utc_now  # noqa: E402
from src.ingest_common import emit_summary, resolve_or_download, run_ingest  # noqa: E402

SOURCE_KEY = "census_acs_rent"
DISPLAY_NAME = "Census ACS county median rent"
CATEGORY = "col"
SEED_CSV = REPO / "data" / "external" / "census_acs_rent" / "2023.csv"

REQUIRED_COLUMNS = {"year", "state", "county_fips", "median_rent"}


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
    parser.add_argument(
        "--source",
        default="census:acs5_b25064",
        help="Source label written to cost_of_living_index.source.",
    )
    return parser.parse_args()


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip().replace(",", "").lstrip("$")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _state_rpp_lookup(conn: sqlite3.Connection) -> dict[str, float]:
    """Latest BEA state RPP keyed by 2-letter postal code."""
    rows = conn.execute(
        """
        SELECT geo_code, year, rpp_overall
        FROM cost_of_living_index
        WHERE geo_type = 'state' AND rpp_overall IS NOT NULL
        ORDER BY geo_code,
                 CASE source WHEN 'bea:rpp' THEN 0 ELSE 1 END,
                 year DESC
        """,
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


def import_acs_county_rent_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
) -> int:
    """Read ``input_path``, derive county COL index, upsert rows.

    Returns the number of rows written. Rows with a missing state RPP fall
    back to the county's own rent ratio without RPP scaling (logged but not
    skipped), so the dataset still reflects within-state variance.
    """
    state_rpp = _state_rpp_lookup(conn)
    now = utc_now()

    # First pass: read every (year, state, fips, rent) into memory so we can
    # compute per-(year, state) median rent before deriving the index.
    parsed: list[tuple[int, str, str, str, float]] = []
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        normalized = {
            (name or "").strip().lower(): name for name in (reader.fieldnames or [])
        }
        missing = REQUIRED_COLUMNS - set(normalized)
        if missing:
            raise ValueError(
                f"CSV missing required columns: {sorted(missing)}; got {reader.fieldnames!r}"
            )
        for row in reader:
            year_raw = (row.get(normalized["year"], "") or "").strip()
            state_raw = (row.get(normalized["state"], "") or "").strip().upper()
            fips_raw = (row.get(normalized["county_fips"], "") or "").strip()
            rent = _to_float(row.get(normalized["median_rent"], ""))
            name = (
                row.get(normalized.get("county_name", ""), "")
                if "county_name" in normalized
                else ""
            ) or ""
            if not year_raw or not state_raw or not fips_raw or rent is None:
                continue
            try:
                year = int(year_raw)
            except ValueError:
                continue
            fips = fips_raw.zfill(5)[:5]
            parsed.append((year, state_raw, fips, name.strip(), rent))

    medians: dict[tuple[int, str], float] = {}
    rents_by_state: dict[tuple[int, str], list[float]] = defaultdict(list)
    for year, state, _fips, _name, rent in parsed:
        rents_by_state[(year, state)].append(rent)
    for key, values in rents_by_state.items():
        medians[key] = statistics.median(values)

    written = 0
    for year, state, fips, _name, rent in parsed:
        median_rent = medians.get((year, state)) or rent
        if median_rent <= 0:
            continue
        rent_ratio = rent / median_rent
        rpp_state = state_rpp.get(state)
        if rpp_state is not None:
            col_index = round(rpp_state * rent_ratio, 2)
        else:
            # No state RPP in the database yet — store the within-state ratio
            # scaled to a 100-base index so downstream code still has a value
            # rather than NULL. Operator should run BEA RPP first.
            col_index = round(rent_ratio * 100.0, 2)
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
            (year, fips, col_index, rent, source, now),
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
        work=lambda conn: import_acs_county_rent_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
        ),
    )
    emit_summary(SOURCE_KEY, row_count, notes=f"from {resolved.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
