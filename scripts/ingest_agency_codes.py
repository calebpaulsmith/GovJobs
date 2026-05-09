"""Ingest the full USAJOBS agency-subelement code list.

The USAJOBS Codelist API publishes the canonical agency-code table at
``https://data.usajobs.gov/api/codelist/agencysubelements``. Each row
pairs a sub-element ``Code`` (e.g. ``HSCB`` for FEMA) with its display
name and the parent department code (e.g. ``HS`` for DHS).

Per ADR-0027 this ingest runs from a clean checkout with no operator
configuration: the response is downloaded on first run, cached under
``data/external/usajobs_agency_codes/``, and reused thereafter. The
``--input`` flag accepts a manual override JSON file.

Run:
    python scripts/ingest_agency_codes.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import upsert_agency_code  # noqa: E402
from src.ingest_common import emit_summary, resolve_or_download, run_ingest  # noqa: E402

logger = logging.getLogger(__name__)

SOURCE_KEY = "usajobs_agency_codes"
DISPLAY_NAME = "USAJOBS agency subelement codes"
CATEGORY = "code_list"
DEFAULT_URL = "https://data.usajobs.gov/api/codelist/agencysubelements"
CACHE_FILENAME = "agencysubelements.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional JSON file (USAJOBS codelist response). Defaults to download.",
    )
    return parser.parse_args()


def _extract_rows(payload: dict) -> list[dict]:
    """Flatten the codelist response to a list of agency-code records."""
    code_list = payload.get("CodeList") or []
    if not code_list:
        return []
    rows: list[dict] = []
    for block in code_list:
        for entry in block.get("ValidValue") or []:
            code = (entry.get("Code") or "").strip()
            if not code:
                continue
            rows.append(
                {
                    "code": code.upper(),
                    "name": (entry.get("Value") or "").strip() or None,
                    "department_code": (entry.get("ParentCode") or "").strip().upper() or None,
                    "active": _parse_active(entry.get("IsDisabled")),
                }
            )
    return rows


def _parse_active(is_disabled: str | None) -> bool | None:
    if is_disabled is None:
        return None
    text = str(is_disabled).strip().lower()
    if text in {"yes", "true", "1"}:
        return False
    if text in {"no", "false", "0"}:
        return True
    return None


def _resolve_department_names(rows: list[dict]) -> dict[str, str]:
    """Build dept_code → dept_name from the rows themselves.

    USAJOBS does not return parent department names directly, but each
    department is also published as its own ValidValue with no ParentCode
    or with itself as ParentCode. As a fallback we leave the name blank
    and let the downstream join fill it in from observed jobs.
    """
    by_code: dict[str, str] = {}
    for row in rows:
        if row["department_code"] is None and row["name"]:
            by_code[row["code"]] = row["name"]
    return by_code


def _do_ingest(
    conn: sqlite3.Connection, *, input_path: Path | None
) -> int:
    source_path = resolve_or_download(
        source_key=SOURCE_KEY,
        default_url=DEFAULT_URL,
        filename=CACHE_FILENAME,
        user_input=input_path,
    )
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rows = _extract_rows(payload)
    if not rows:
        raise RuntimeError(
            "USAJOBS codelist returned 0 rows; refusing to overwrite agency_codes."
        )

    dept_names = _resolve_department_names(rows)
    for row in rows:
        upsert_agency_code(
            conn,
            code=row["code"],
            name=row["name"],
            department_code=row["department_code"],
            department_name=dept_names.get(row["department_code"]) if row["department_code"] else None,
            active=row["active"],
            source="usajobs:codelist:agencysubelements",
        )
    conn.commit()
    return len(rows)


def main() -> int:
    args = _parse_args()
    config = load_config()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    row_count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        work=lambda conn: _do_ingest(conn, input_path=args.input),
        database_path=config.database_path,
        notes=f"source={DEFAULT_URL}",
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
