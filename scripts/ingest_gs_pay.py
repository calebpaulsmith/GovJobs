"""Ingest OPM General Schedule pay tables.

GS has 15 grades × 10 steps. The base table (locality_code = '') and each
locality table (e.g. CHI, DCB, RUS) are ingested as rows in ``pay_scales``.

Input format (CSV with header):
    year,grade,step,locality_code,annual_rate,source_url
    2026,01,01,,21986,https://www.opm.gov/...general-schedule/
    2026,01,02,,22720,https://www.opm.gov/...general-schedule/
    ...
    2026,13,01,CHI,110803,https://www.opm.gov/...chicago/
    ...

``locality_code`` is empty for the base table; otherwise the locality code
that matches ``locality_pay_areas.code``. Per ADR-0018 every row stores its
``source`` (a label) and ``source_url`` (the canonical OPM page).

Run:
    python scripts/ingest_gs_pay.py --input data/external/gs_pay_2026_base.csv
    python scripts/ingest_gs_pay.py --input data/external/gs_pay_2026_chi.csv
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

SOURCE_KEY = "opm_gs_pay"
DISPLAY_NAME = "OPM GS pay tables"
CATEGORY = "pay"
SEED_CSV = REPO / "data" / "external" / "opm_gs_pay" / "2025_base.csv"

REQUIRED_COLUMNS = {"year", "grade", "step", "annual_rate"}


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
        default="opm:gs_pay",
        help="Source label written to pay_scales.source.",
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="Optional canonical URL applied when the CSV column is missing.",
    )
    parser.add_argument(
        "--source-key",
        default=SOURCE_KEY,
        help="Override the data_source_status key (e.g. opm_gs_pay_2026_chi).",
    )
    return parser.parse_args()


def _norm_grade(value: str) -> str:
    s = (value or "").strip()
    return s.zfill(2) if s.isdigit() else s


def _norm_step(value: str) -> int:
    s = (value or "").strip()
    return int(s) if s.isdigit() else 0


def import_gs_pay_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    pay_plan: str,
    source: str,
    default_source_url: str | None,
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
            try:
                year = int((row.get("year") or "").strip())
                rate = float((row.get("annual_rate") or "").strip())
            except ValueError:
                continue
            grade = _norm_grade(row.get("grade") or "")
            step = _norm_step(row.get("step") or "0")
            locality = (row.get("locality_code") or "").strip().upper()
            url = (row.get("source_url") or "").strip() or default_source_url
            if not grade or rate <= 0:
                continue
            conn.execute(
                """
                INSERT INTO pay_scales (
                    pay_plan, year, grade, step, locality_code,
                    annual_rate, source, source_url, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pay_plan, year, grade, step, locality_code) DO UPDATE SET
                    annual_rate=excluded.annual_rate,
                    source=excluded.source,
                    source_url=COALESCE(excluded.source_url, pay_scales.source_url),
                    imported_at=excluded.imported_at
                """,
                (pay_plan, year, grade, step, locality, rate, source, url, now),
            )
            written += 1
    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    resolved = resolve_or_download(
        source_key=args.source_key,
        default_url=None,
        cache_dir=SEED_CSV.parent,
        filename=SEED_CSV.name,
        user_input=args.input,
        seed_path=SEED_CSV,
    )
    row_count = run_ingest(
        source_key=args.source_key,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=f"input={resolved.name}",
        work=lambda conn: import_gs_pay_from_csv(
            conn,
            input_path=resolved,
            pay_plan="GS",
            source=args.source,
            default_source_url=args.source_url,
        ),
    )
    emit_summary(args.source_key, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
