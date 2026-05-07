"""Locality-adjusted pay tables for federal jobs.

For a given (pay_plan, year, city, state, grade range), produce a table of
``{grade: {step: annual_rate}}`` reflecting the locality adjustment that
applies to the duty station. Used by:

* ``src/public_map_export.py`` to embed pay tables in ``jobs_detail.json``
* ``pages/11_Public_Map_Admin.py`` to spot-check a job's pay table
* The future job-card popup on the public site

The calculator is **deterministic** and **explainable**: every returned cell
carries provenance — the locality area used, the source row id, and whether
the rate came directly from a locality-specific scale or was derived as
``base * (1 + adjustment_pct/100)``.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from src.reference_data import (
    base_pay_scale,
    locality_or_rus,
    pay_plan,
    pay_scale_lookup,
    pay_scales_for_grade,
)

logger = logging.getLogger(__name__)


def _grade_range(grade_low: str | int | None, grade_high: str | int | None) -> list[str]:
    """Expand a (low, high) grade pair into the inclusive grade list.

    Pads single-digit numeric grades to two digits ('1' -> '01') so they sort
    naturally and match how OPM publishes them.
    """
    def _norm(value: Any) -> str | None:
        if value is None or value == "":
            return None
        s = str(value).strip()
        return s.zfill(2) if s.isdigit() else s

    low = _norm(grade_low)
    high = _norm(grade_high) or low
    if not low:
        return []
    if low == high:
        return [low]
    if low.isdigit() and high.isdigit():
        a, b = int(low), int(high)
        if b < a:
            a, b = b, a
        return [str(g).zfill(2) for g in range(a, b + 1)]
    return [low] if low else []


def _apply_adjustment(base_rate: float, adjustment_pct: float) -> float:
    return round(base_rate * (1 + adjustment_pct / 100.0), 2)


def calculate_job_pay_table(
    conn: sqlite3.Connection,
    *,
    pay_plan_code: str,
    year: int,
    city: str | None,
    state: str | None,
    grade_low: str | int | None,
    grade_high: str | int | None = None,
) -> dict[str, Any]:
    """Return the locality-adjusted pay table for one job.

    Result shape::

        {
            "pay_plan": "GS",
            "year": 2026,
            "locality": {"code": "CHI", "name": "Chicago...", "adjustment_pct": 32.45,
                         "inclusion_type": "core", "source": "..."},
            "grades": {
                "13": {"01": {"rate": 110803.0, "method": "locality_row", "source": "..."}, ...},
                "14": {...},
            },
            "notes": [...],   # provenance / fallback notes
        }
    """
    plan = pay_plan(conn, pay_plan_code)
    notes: list[str] = []
    locality = locality_or_rus(conn, city, state, year)

    if plan is None:
        notes.append(
            f"pay_plan {pay_plan_code!r} not registered in pay_plans; "
            "treating as unknown"
        )

    grades = _grade_range(grade_low, grade_high)
    grade_table: dict[str, dict[str, dict[str, Any]]] = {}

    for grade in grades:
        steps_for_grade: dict[str, dict[str, Any]] = {}
        # Try locality-specific rows first (full set, all steps).
        locality_rows = pay_scales_for_grade(
            conn,
            pay_plan_code=pay_plan_code,
            year=year,
            grade=grade,
            locality_code=locality["code"],
        )
        if locality_rows:
            for row in locality_rows:
                step_key = f"{row['step']:02d}" if row["step"] else "00"
                steps_for_grade[step_key] = {
                    "rate": row["annual_rate"],
                    "method": "locality_row",
                    "locality_code": row["locality_code"],
                    "source": row["source"],
                    "source_url": row.get("source_url"),
                }
        else:
            # Fall back to base table + adjustment_pct.
            base_rows = pay_scales_for_grade(
                conn,
                pay_plan_code=pay_plan_code,
                year=year,
                grade=grade,
                locality_code="",
            )
            if not base_rows:
                notes.append(
                    f"no pay_scales rows for ({pay_plan_code}, {year}, grade {grade})"
                )
                continue
            adjustment = float(locality.get("adjustment_pct") or 0.0)
            for row in base_rows:
                step_key = f"{row['step']:02d}" if row["step"] else "00"
                steps_for_grade[step_key] = {
                    "rate": _apply_adjustment(row["annual_rate"], adjustment),
                    "method": "base_plus_adjustment",
                    "adjustment_pct": adjustment,
                    "locality_code": locality["code"],
                    "source": row["source"],
                    "source_url": row.get("source_url"),
                }
            if adjustment == 0 and locality["code"] != "RUS":
                notes.append(
                    f"locality {locality['code']} has 0% adjustment; "
                    "rates equal the base table"
                )

        if steps_for_grade:
            grade_table[grade] = steps_for_grade

    return {
        "pay_plan": (pay_plan_code or "").upper(),
        "year": year,
        "locality": {
            "code": locality["code"],
            "name": locality["name"],
            "adjustment_pct": locality.get("adjustment_pct"),
            "inclusion_type": locality.get("inclusion_type"),
            "source": locality.get("source"),
        },
        "grades": grade_table,
        "notes": notes,
    }


def lookup_single_rate(
    conn: sqlite3.Connection,
    *,
    pay_plan_code: str,
    year: int,
    city: str | None,
    state: str | None,
    grade: str | int,
    step: int = 1,
) -> dict[str, Any] | None:
    """Return one locality-adjusted cell for spot-check / popup use.

    Prefers a locality-specific pay_scales row; if absent, derives from the
    base row + locality adjustment_pct.
    """
    locality = locality_or_rus(conn, city, state, year)
    grade_str = str(grade).zfill(2) if str(grade).isdigit() else str(grade)
    locality_row = pay_scale_lookup(
        conn,
        pay_plan_code=pay_plan_code,
        year=year,
        grade=grade_str,
        step=step,
        locality_code=locality["code"],
    )
    if locality_row:
        return {
            "rate": locality_row["annual_rate"],
            "method": "locality_row",
            "locality": locality,
            "source": locality_row["source"],
            "source_url": locality_row.get("source_url"),
        }
    base_row = base_pay_scale(
        conn,
        pay_plan_code=pay_plan_code,
        year=year,
        grade=grade_str,
        step=step,
    )
    if not base_row:
        return None
    adjustment = float(locality.get("adjustment_pct") or 0.0)
    return {
        "rate": _apply_adjustment(base_row["annual_rate"], adjustment),
        "method": "base_plus_adjustment",
        "adjustment_pct": adjustment,
        "locality": locality,
        "source": base_row["source"],
        "source_url": base_row.get("source_url"),
    }
