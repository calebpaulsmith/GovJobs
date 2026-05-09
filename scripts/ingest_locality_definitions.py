"""Ingest OPM's annual locality pay area definitions.

Per ADR-0019 these definitions are the canonical legal source for locality
membership (5 CFR 531.603). Each row pairs a locality code with a county
FIPS code for a given year. They are also the input the dissolve-fallback
relies on when the OPM ArcGIS FeatureServer is unavailable.

Input format (CSV with header):
    locality_code,year,county_fips,inclusion_type
    CHI,2026,17031,core
    CHI,2026,17043,core
    DCB,2026,11001,core
    ...

Optional columns: ``locality_name``, ``description``. When present, these
also seed the ``locality_pay_areas`` row (so a single CSV can do both
membership and area registration). Adjustment percentages live in a separate
ingest (``ingest_locality_pay.py``) so accuracy is auditable per concern.

Run:
    python scripts/ingest_locality_definitions.py \\
        --input data/external/opm_locality_2026.csv
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

SOURCE_KEY = "opm_locality_definitions"
DISPLAY_NAME = "OPM locality pay area definitions"
CATEGORY = "locality"
SEED_CSV = REPO / "data" / "external" / "opm_locality_definitions" / "2026.csv"

REQUIRED_COLUMNS = {"locality_code", "year", "county_fips"}


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
        default="opm:locality_definitions",
        help="Source label written to locality_pay_areas.source.",
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="Optional canonical OPM URL to record alongside each row.",
    )
    parser.add_argument(
        "--replace-year",
        action="store_true",
        help=(
            "When set, deletes existing rows for any (locality, year) seen in the input "
            "before inserting. Use when re-importing a corrected year."
        ),
    )
    return parser.parse_args()


def _normalize_county_fips(value: str) -> str | None:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(5)[:5]


def import_definitions_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
    source_url: str | None,
    replace_year: bool,
) -> int:
    now = utc_now()
    written = 0
    seen_areas: set[tuple[str, int]] = set()

    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"CSV missing required columns: {sorted(missing)}; got {reader.fieldnames!r}"
            )
        for row in reader:
            code = (row.get("locality_code") or "").strip().upper()
            year_raw = (row.get("year") or "").strip()
            fips = _normalize_county_fips(row.get("county_fips") or "")
            if not code or not year_raw or not fips:
                continue
            try:
                year = int(year_raw)
            except ValueError:
                continue
            inclusion_type = (row.get("inclusion_type") or "core").strip().lower() or "core"

            area_key = (code, year)
            if area_key not in seen_areas:
                seen_areas.add(area_key)
                if replace_year:
                    conn.execute(
                        "DELETE FROM locality_pay_counties WHERE locality_code=? AND year=?",
                        (code, year),
                    )
                # Seed the area row if we got a name; preserve adjustment_pct
                # if it was already set by a separate ingest.
                name = (row.get("locality_name") or row.get("name") or "").strip() or code
                description = (row.get("description") or "").strip() or None
                conn.execute(
                    """
                    INSERT INTO locality_pay_areas (
                        code, year, name, description, adjustment_pct,
                        polygon_path, source, source_url, imported_at
                    )
                    VALUES (?, ?, ?, ?, COALESCE((
                        SELECT adjustment_pct FROM locality_pay_areas WHERE code=? AND year=?
                    ), 0), NULL, ?, ?, ?)
                    ON CONFLICT(code, year) DO UPDATE SET
                        name=excluded.name,
                        description=COALESCE(excluded.description, locality_pay_areas.description),
                        source=excluded.source,
                        source_url=COALESCE(excluded.source_url, locality_pay_areas.source_url),
                        imported_at=excluded.imported_at
                    """,
                    (code, year, name, description, code, year, source, source_url, now),
                )

            conn.execute(
                """
                INSERT INTO locality_pay_counties (
                    locality_code, year, county_fips, inclusion_type
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(locality_code, year, county_fips) DO UPDATE SET
                    inclusion_type=excluded.inclusion_type
                """,
                (code, year, fips, inclusion_type),
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
        work=lambda conn: import_definitions_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
            source_url=args.source_url,
            replace_year=args.replace_year,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
