"""Ingest pay tables for non-GS pay plans (FW, ES, AD, FP, LE, VN, etc.).

Same row shape as ``ingest_gs_pay.py`` — every row goes into ``pay_scales``
keyed by ``(pay_plan, year, grade, step, locality_code)``. The pay plan is
specified via ``--plan`` and must already be registered in ``pay_plans``
(seeded by ``init_schema`` or added manually).

Input CSV columns (header required):
    year,grade,step,locality_code,annual_rate,source_url

For pay plans without steps (ES, AD, EX), use ``step=0`` and one row per
grade. For pay plans without locality adjustment, use empty ``locality_code``.

Run:
    python scripts/ingest_other_pay_plans.py --plan FW \\
        --input data/external/fw_pay_2026.csv

Each ``--plan`` writes its own ``data_source_status`` row keyed
``opm_pay_<plan>`` so freshness is tracked per plan.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.ingest_common import emit_summary, run_ingest  # noqa: E402
from scripts.ingest_gs_pay import import_gs_pay_from_csv  # noqa: E402

CATEGORY = "pay"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        required=True,
        help="Pay plan code (e.g. FW, ES, AD, FP, LE, VN, EX, SL, ST).",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--source",
        default=None,
        help="Source label; defaults to 'opm:<plan>_pay'.",
    )
    parser.add_argument("--source-url", default=None)
    return parser.parse_args()


def _ensure_plan_registered(conn: sqlite3.Connection, plan_code: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM pay_plans WHERE code=?", (plan_code,)
    ).fetchone()
    if not row:
        raise RuntimeError(
            f"pay plan {plan_code!r} not registered. Add a row to pay_plans first."
        )


def main() -> int:
    args = _parse_args()
    if not args.input.exists():
        sys.stderr.write(f"ERROR: input not found at {args.input}\n")
        return 1
    plan = args.plan.strip().upper()
    source_key = f"opm_pay_{plan.lower()}"
    display_name = f"OPM {plan} pay tables"
    source_label = args.source or f"opm:{plan.lower()}_pay"
    cfg = load_config()

    def work(conn: sqlite3.Connection) -> int:
        _ensure_plan_registered(conn, plan)
        return import_gs_pay_from_csv(
            conn,
            input_path=args.input,
            pay_plan=plan,
            source=source_label,
            default_source_url=args.source_url,
        )

    row_count = run_ingest(
        source_key=source_key,
        display_name=display_name,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=f"plan={plan};input={args.input.name}",
        work=work,
    )
    emit_summary(source_key, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
