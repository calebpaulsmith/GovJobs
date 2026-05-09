"""Ingest OPM annual locality-pay percentages.

Source: OPM publishes the locality pay percentage that applies on top of
the GS base table for each locality area, each year. Per ADR-0018 the
ingest is auditable: every row stores its source.

Input format (CSV with header):
    locality_code,year,adjustment_pct
    CHI,2026,32.45
    DCB,2026,33.26
    RUS,2026,17.00

Optional columns: ``locality_name`` to seed the area row when not yet
present (the canonical seed comes from ``ingest_locality_definitions.py``).

Run:
    python scripts/ingest_locality_pay.py --input data/external/locality_pay_2026.csv
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

SOURCE_KEY = "opm_locality_pay"
DISPLAY_NAME = "OPM locality pay percentages"
CATEGORY = "pay"
SEED_CSV = REPO / "data" / "external" / "opm_locality_pay" / "2026.csv"

REQUIRED_COLUMNS = {"locality_code", "year", "adjustment_pct"}


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
    parser.add_argument("--source", default="opm:locality_pay")
    parser.add_argument("--source-url", default=None)
    return parser.parse_args()


def import_locality_pay_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
    source_url: str | None,
) -> int:
    now = utc_now()
    written = 0
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
            pct_raw = (row.get("adjustment_pct") or "").strip().rstrip("%")
            if not code or not year_raw or not pct_raw:
                continue
            try:
                year = int(year_raw)
                pct = float(pct_raw)
            except ValueError:
                continue
            name = (row.get("locality_name") or row.get("name") or "").strip() or code

            conn.execute(
                """
                INSERT INTO locality_pay_areas (
                    code, year, name, description, adjustment_pct,
                    polygon_path, source, source_url, imported_at
                )
                VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?)
                ON CONFLICT(code, year) DO UPDATE SET
                    name=CASE
                        WHEN locality_pay_areas.name = locality_pay_areas.code THEN excluded.name
                        ELSE locality_pay_areas.name
                    END,
                    adjustment_pct=excluded.adjustment_pct,
                    source=excluded.source,
                    source_url=COALESCE(excluded.source_url, locality_pay_areas.source_url),
                    imported_at=excluded.imported_at
                """,
                (code, year, name, pct, source, source_url, now),
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
        work=lambda conn: import_locality_pay_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
            source_url=args.source_url,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
