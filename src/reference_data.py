"""Read-side helpers for public-map reference data.

This module is the single place to look up:

* a county's locality pay area (via ``locality_pay_counties``)
* a pay scale row (with locality fallback to base + adjustment%)
* a state, county, or metro polygon path
* a cost-of-living index for a state or CBSA

It performs **reads only**. Ingest scripts in ``scripts/ingest_*.py`` write
the underlying tables; this module is what the pay calculator and the public
map exporter consume.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


REST_OF_US_CODE = "RUS"
"""OPM's "Rest of U.S." catch-all locality used when no specific area applies."""


# ---------- Locality lookups ------------------------------------------------


def locality_for_county(
    conn: sqlite3.Connection,
    county_fips: str,
    year: int,
) -> dict[str, Any] | None:
    """Return the locality pay area row that contains this county in `year`.

    A county can belong to at most one locality pay area in a given year;
    this is enforced by OPM's annual definition list.
    """
    if not county_fips:
        return None
    row = conn.execute(
        """
        SELECT lpa.code, lpa.year, lpa.name, lpa.adjustment_pct, lpa.description,
               lpa.polygon_path, lpa.source, lpa.source_url, lpc.inclusion_type
        FROM locality_pay_counties lpc
        JOIN locality_pay_areas lpa
          ON lpa.code = lpc.locality_code AND lpa.year = lpc.year
        WHERE lpc.county_fips = ? AND lpc.year = ?
        """,
        (county_fips, year),
    ).fetchone()
    return dict(row) if row else None


def locality_for_city_state(
    conn: sqlite3.Connection,
    city: str | None,
    state: str | None,
    year: int,
) -> dict[str, Any] | None:
    """Look up a locality area via the geocoded county for (city, state).

    Falls back to ``None`` when the city has no FIPS county or the county is
    not assigned to a locality area in `year`. Callers that want a hard
    fallback to "Rest of U.S." should use ``locality_or_rus``.
    """
    normalized_city = (city or "").strip().lower()
    normalized_state = (state or "").strip().upper()
    if not normalized_state:
        return None
    if normalized_city:
        row = conn.execute(
            "SELECT county_fips FROM locations_geocoded WHERE city=? AND state=?",
            (normalized_city, normalized_state),
        ).fetchone()
    else:
        row = None
    fips: str | None = row["county_fips"] if row and row["county_fips"] else None
    if fips:
        match = locality_for_county(conn, fips, year)
        if match:
            return match
    return None


def locality_or_rus(
    conn: sqlite3.Connection,
    city: str | None,
    state: str | None,
    year: int,
) -> dict[str, Any]:
    """Like ``locality_for_city_state`` but always returns a row.

    If no specific locality applies, returns the Rest of U.S. row for that
    year. If even RUS is not loaded, returns a synthetic 0% adjustment row
    so callers never have to special-case `None`.
    """
    match = locality_for_city_state(conn, city, state, year)
    if match:
        return match
    rus = conn.execute(
        "SELECT code, year, name, adjustment_pct, description, polygon_path, source, source_url "
        "FROM locality_pay_areas WHERE code=? AND year=?",
        (REST_OF_US_CODE, year),
    ).fetchone()
    if rus:
        result = dict(rus)
        result["inclusion_type"] = "rest_of_us"
        return result
    return {
        "code": REST_OF_US_CODE,
        "year": year,
        "name": "Rest of U.S. (synthetic; no data loaded)",
        "adjustment_pct": 0.0,
        "description": None,
        "polygon_path": None,
        "source": "synthetic",
        "source_url": None,
        "inclusion_type": "rest_of_us",
    }


# ---------- Pay scale lookups -----------------------------------------------


def pay_plan(conn: sqlite3.Connection, code: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM pay_plans WHERE code=?",
        ((code or "").upper(),),
    ).fetchone()
    return dict(row) if row else None


def pay_scale_lookup(
    conn: sqlite3.Connection,
    *,
    pay_plan_code: str,
    year: int,
    grade: str,
    step: int = 0,
    locality_code: str = "",
) -> dict[str, Any] | None:
    """Return one pay-scale row, or None if it isn't loaded.

    ``step=0`` and ``locality_code=""`` are the sentinels used in the
    composite primary key for "no step" and "base / no locality".
    """
    row = conn.execute(
        """
        SELECT pay_plan, year, grade, step, locality_code, annual_rate,
               source, source_url, imported_at
        FROM pay_scales
        WHERE pay_plan=? AND year=? AND grade=? AND step=? AND locality_code=?
        """,
        (
            (pay_plan_code or "").upper(),
            int(year),
            str(grade),
            int(step),
            locality_code or "",
        ),
    ).fetchone()
    return dict(row) if row else None


def base_pay_scale(
    conn: sqlite3.Connection,
    *,
    pay_plan_code: str,
    year: int,
    grade: str,
    step: int = 0,
) -> dict[str, Any] | None:
    """Convenience for the no-locality (base) row."""
    return pay_scale_lookup(
        conn,
        pay_plan_code=pay_plan_code,
        year=year,
        grade=grade,
        step=step,
        locality_code="",
    )


def pay_scales_for_grade(
    conn: sqlite3.Connection,
    *,
    pay_plan_code: str,
    year: int,
    grade: str,
    locality_code: str = "",
) -> list[dict[str, Any]]:
    """All step rows for one (plan, year, grade, locality)."""
    rows = conn.execute(
        """
        SELECT pay_plan, year, grade, step, locality_code, annual_rate,
               source, source_url, imported_at
        FROM pay_scales
        WHERE pay_plan=? AND year=? AND grade=? AND locality_code=?
        ORDER BY step
        """,
        (
            (pay_plan_code or "").upper(),
            int(year),
            str(grade),
            locality_code or "",
        ),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------- Geometry path lookups -------------------------------------------


def state_polygon_path(conn: sqlite3.Connection, state: str) -> str | None:
    row = conn.execute(
        "SELECT polygon_path FROM state_polygons WHERE state=?",
        ((state or "").upper(),),
    ).fetchone()
    return row["polygon_path"] if row else None


def county_record(conn: sqlite3.Connection, fips: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT fips, name, state, cbsa_code, polygon_path, source, imported_at "
        "FROM counties WHERE fips=?",
        ((fips or "").strip(),),
    ).fetchone()
    return dict(row) if row else None


def metro_record(conn: sqlite3.Connection, cbsa_code: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT cbsa_code, name, cbsa_type, polygon_path, source, imported_at "
        "FROM metro_areas WHERE cbsa_code=?",
        ((cbsa_code or "").strip(),),
    ).fetchone()
    return dict(row) if row else None


# ---------- Cost of living --------------------------------------------------


def cost_of_living(
    conn: sqlite3.Connection,
    *,
    geo_type: str,
    geo_code: str,
    year: int | None = None,
    source: str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent (or specified-year) RPP row for a geography.

    ``geo_type`` is ``"state"`` or ``"cbsa"``; ``geo_code`` is the 2-letter
    state code or 5-digit CBSA code. If ``year`` is None, the latest year
    available is returned. If multiple sources provide the same year (e.g.
    BEA + C2ER), an explicit ``source`` argument disambiguates; otherwise the
    BEA row is preferred.
    """
    params: list[Any] = [geo_type, geo_code]
    sql = (
        "SELECT year, geo_type, geo_code, rpp_overall, rpp_goods, rpp_services, "
        "rpp_rents, source, imported_at "
        "FROM cost_of_living_index WHERE geo_type=? AND geo_code=?"
    )
    if year is not None:
        sql += " AND year=?"
        params.append(int(year))
    if source is not None:
        sql += " AND source=?"
        params.append(source)
    sql += " ORDER BY year DESC, CASE source WHEN 'bea:rpp' THEN 0 ELSE 1 END LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None
