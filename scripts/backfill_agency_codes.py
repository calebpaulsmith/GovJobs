"""Backfill agency_code / department_code on existing jobs from raw JSON.

The Search normalizer was missing the ``UserArea.Details.OrganizationCodes``
path, so jobs imported before that fix landed in SQLite with
``agency_code = NULL``. This script re-reads the raw Search responses on
disk, parses them with the (now-fixed) normalizer, and updates each job
in place. It is idempotent — running it twice is a no-op.

Run:
    python scripts/backfill_agency_codes.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import connect, init_schema  # noqa: E402
from src.usajobs_normalize import job_from_search_item, job_from_historic_record  # noqa: E402

logger = logging.getLogger(__name__)


def _backfill_search(conn, raw_root: Path) -> tuple[int, int]:
    """Re-parse Search responses; UPDATE jobs by usajobs_control_number.

    Returns ``(scanned, updated)``.
    """
    scanned = 0
    updated = 0
    files = sorted(raw_root.rglob("*.json"))
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skip unreadable %s: %s", path, exc)
            continue
        items = payload.get("SearchResult", {}).get("SearchResultItems", [])
        for item in items:
            scanned += 1
            normalized = job_from_search_item(item)
            cn = normalized.get("usajobs_control_number")
            agency_code = normalized.get("agency_code")
            department_code = normalized.get("department_code")
            if not cn or (agency_code is None and department_code is None):
                continue
            cur = conn.execute(
                """
                UPDATE jobs
                SET agency_code = COALESCE(?, agency_code),
                    department_code = COALESCE(?, department_code)
                WHERE source = 'usajobs_search'
                  AND usajobs_control_number = ?
                  AND (agency_code IS NULL OR department_code IS NULL)
                """,
                (agency_code, department_code, cn),
            )
            if cur.rowcount:
                updated += cur.rowcount
        conn.commit()
    return scanned, updated


def _backfill_historic(conn, raw_root: Path) -> tuple[int, int]:
    """Re-parse HistoricJoa responses; UPDATE jobs by usajobs_control_number."""
    scanned = 0
    updated = 0
    files = sorted(raw_root.rglob("*.json"))
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skip unreadable %s: %s", path, exc)
            continue
        # HistoricJoa response shape: {"data": [...]}
        records = payload.get("data") or payload.get("Data") or []
        for record in records:
            scanned += 1
            if not isinstance(record, dict):
                continue
            normalized = job_from_historic_record(record)
            cn = normalized.get("usajobs_control_number")
            agency_code = normalized.get("agency_code")
            department_code = normalized.get("department_code")
            if not cn or (agency_code is None and department_code is None):
                continue
            cur = conn.execute(
                """
                UPDATE jobs
                SET agency_code = COALESCE(?, agency_code),
                    department_code = COALESCE(?, department_code)
                WHERE source = 'usajobs_historic'
                  AND usajobs_control_number = ?
                  AND (agency_code IS NULL OR department_code IS NULL)
                """,
                (agency_code, department_code, cn),
            )
            if cur.rowcount:
                updated += cur.rowcount
        conn.commit()
    return scanned, updated


def _backfill_from_name(conn) -> int:
    """Last-resort fill: when raw JSON didn't yield a code, match by agency name.

    Many jobs share an agency name with a known agency_codes row. This is
    case-insensitive and only fires for rows still missing a code.
    """
    cur = conn.execute(
        """
        UPDATE jobs
        SET agency_code = (
            SELECT ac.code FROM agency_codes ac
            WHERE LOWER(TRIM(ac.name)) = LOWER(TRIM(jobs.agency))
            LIMIT 1
        )
        WHERE agency_code IS NULL
          AND TRIM(COALESCE(agency, '')) <> ''
        """
    )
    name_filled = cur.rowcount
    cur = conn.execute(
        """
        UPDATE jobs
        SET department_code = (
            SELECT ac.department_code FROM agency_codes ac
            WHERE ac.code = jobs.agency_code
            LIMIT 1
        )
        WHERE agency_code IS NOT NULL
          AND department_code IS NULL
        """
    )
    dept_filled = cur.rowcount
    conn.commit()
    return name_filled + dept_filled


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = load_config()
    conn = connect(config.database_path)
    init_schema(conn)

    raw_root = Path(config.raw_data_path)

    print("Backfilling Search rows from raw JSON...")
    scanned_s, updated_s = _backfill_search(conn, raw_root / "usajobs_search")
    print(f"  scanned={scanned_s:,}  updated={updated_s:,}")

    print("Backfilling Historic rows from raw JSON...")
    scanned_h, updated_h = _backfill_historic(conn, raw_root / "usajobs_historic")
    print(f"  scanned={scanned_h:,}  updated={updated_h:,}")

    print("Filling remaining gaps by agency-name match...")
    name_filled = _backfill_from_name(conn)
    print(f"  rows filled by name match: {name_filled:,}")

    print()
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    with_code = conn.execute("SELECT COUNT(*) FROM jobs WHERE agency_code IS NOT NULL").fetchone()[0]
    distinct_codes = conn.execute("SELECT COUNT(DISTINCT agency_code) FROM jobs WHERE agency_code IS NOT NULL").fetchone()[0]
    print(f"jobs:             {total_jobs:,}")
    print(f"  with code:      {with_code:,}  ({100*with_code/total_jobs:.1f}%)")
    print(f"  distinct codes: {distinct_codes:,}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
