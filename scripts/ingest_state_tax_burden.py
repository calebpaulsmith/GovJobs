"""Ingest state-local tax burden (Tax Foundation) into ``state_tax_burden``.

The Tax Foundation publishes an annual "State and Local Tax Burdens" study —
total state-local taxes paid by a state's residents as a share of that state's
income (their "Effective Tax Rate" column). Source page:
<https://taxfoundation.org/data/all/state/tax-burden-by-state-2022/>.

This is a D.5.27 V1.1 signal for the Localities screen: a state-level
cost-of-living-adjacent figure shown per locality via the locality's primary
state. It is **state-level only** — there is no locality-level tax burden — so
the website labels it accordingly.

Expected CSV columns (header required, case-insensitive):
    year, state, burden_pct
``state`` is a 2-letter postal code (DC included); ``burden_pct`` is the
effective state-local tax rate as a percent of income (e.g. ``9.8``).

Per ADR-0027 this is self-bootstrapping: with no ``--input`` it reads the
checked-in seed (Tax Foundation Calendar Year 2022 study) so a clean checkout
builds offline.

Run:
    python scripts/ingest_state_tax_burden.py --input data/external/tax_2024.csv
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

SOURCE_KEY = "state_tax_burden"
DISPLAY_NAME = "State-Local Tax Burden (Tax Foundation)"
CATEGORY = "col"
SEED_CSV = REPO / "data" / "external" / "state_tax_burden" / "2022.csv"

REQUIRED_COLUMNS = {"year", "state", "burden_pct"}


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
    parser.add_argument("--source", default="taxfoundation:burden")
    return parser.parse_args()


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip().rstrip("%")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def import_tax_burden_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
) -> int:
    now = utc_now()
    written = 0
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        normalized_fields = {
            (name or "").strip().lower(): name for name in (reader.fieldnames or [])
        }
        missing = REQUIRED_COLUMNS - set(normalized_fields)
        if missing:
            raise ValueError(
                f"CSV missing required columns: {sorted(missing)}; got {reader.fieldnames!r}"
            )
        for row in reader:
            year_raw = row.get(normalized_fields["year"], "").strip()
            state = row.get(normalized_fields["state"], "").strip().upper()
            burden = _to_float(row.get(normalized_fields["burden_pct"], ""))
            if not year_raw or len(state) != 2 or burden is None:
                continue
            try:
                year = int(year_raw)
            except ValueError:
                continue
            conn.execute(
                """
                INSERT INTO state_tax_burden (year, state, burden_pct, source, imported_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(year, state, source) DO UPDATE SET
                    burden_pct=excluded.burden_pct,
                    imported_at=excluded.imported_at
                """,
                (year, state, burden, source, now),
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
        work=lambda conn: import_tax_burden_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
