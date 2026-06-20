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


OVERSEAS_PAY_CONTEXT = (
    "**Overseas US-federal position.** This is a US federal job located outside "
    "the United States. Base pay still follows the GS schedule in **USD**. "
    "US locality pay does **not** apply abroad — instead, total compensation may "
    "include State Department allowances: a post (cost-of-living) allowance, a "
    "post (hardship) differential, and danger pay, depending on the post. Those "
    "allowances are not yet modeled in this dashboard, so treat the listed salary "
    "as **GS base only**; actual compensation abroad can differ. (Detailed DSSR "
    "allowance modeling is a planned update.)"
)
"""Reusable explainer shown when a single overseas country is in scope.

Stored here as data (not page markup) so Search and any future surface render
the same copy. Per-post DSSR allowance figures arrive in a later stage; until
then this card is the honest stand-in that prevents GS-base pay from reading
as final overseas compensation."""


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


# ---------- Overseas DSSR allowances (DSSR 220 / 500 / 650) ------------------
# US-fed jobs abroad keep GS base (USD) with NO US locality pay; their real comp
# adds State Dept allowances. Sources are the live Web920 tables (verified
# 2026-06-20). These are reads only; scripts/ingest_dssr_allowances.py writes.
_DSSR_HARDSHIP_URL = "https://allowances.state.gov/Web920/hardship.asp"
_DSSR_DANGER_URL = "https://allowances.state.gov/Web920/danger_pay_all.asp"
_DSSR_COLA_URL = "https://allowances.state.gov/Web920/cola.asp"


def overseas_post_allowance(
    conn: sqlite3.Connection, country: Any, city: Any
) -> dict[str, Any] | None:
    """Match a duty station to a DSSR post row.

    Match precision, most to least specific: exact (country_iso, post=city) →
    the country's "Other" catch-all row (State's own country-level fallback) →
    None (caller shows GS base only). Adds a ``match`` field: ``'post'`` |
    ``'country'``. ``country`` is normalized to ISO so an ISO-coded job row joins
    the ingest's ISO column.
    """
    from src.database import normalize_country

    iso = normalize_country(country)
    if not iso:
        return None
    iso = iso.upper()
    city_text = (str(city).strip() if city else "") or None
    if city_text:
        row = conn.execute(
            "SELECT * FROM overseas_post_allowances "
            "WHERE country_iso=? AND post_name=? COLLATE NOCASE",
            (iso, city_text),
        ).fetchone()
        if row:
            out = dict(row)
            out["match"] = "post"
            return out
    row = conn.execute(
        "SELECT * FROM overseas_post_allowances "
        "WHERE country_iso=? AND post_name='Other'",
        (iso,),
    ).fetchone()
    if row:
        out = dict(row)
        out["match"] = "country"
        return out
    return None


def spendable_income_for(
    conn: sqlite3.Connection, salary: float | int | None, family_size: int = 1
) -> dict[str, Any] | None:
    """Annual spendable income for a salary + family size (DSSR 229 table).

    Returns the matching band row, or None when salary is missing or below the
    lowest published band (caller must then withhold the COLA dollar estimate).
    """
    if salary is None:
        return None
    row = conn.execute(
        "SELECT * FROM spendable_income "
        "WHERE family_size=? AND salary_min<=? "
        "AND (salary_max IS NULL OR salary_max>=?) "
        "ORDER BY salary_min DESC LIMIT 1",
        (int(family_size), float(salary), float(salary)),
    ).fetchone()
    return dict(row) if row else None


def overseas_compensation(
    conn: sqlite3.Connection,
    *,
    country: Any,
    city: Any,
    base_salary: float | int | None,
    family_size: int = 1,
) -> dict[str, Any]:
    """Build a traceable overseas comp breakdown for one duty station.

    Returns GS base plus DSSR line items — each with its percentage, the DSSR
    section, the dollar amount, the source URL, and the effective date. Hardship
    and danger are exact (% of base). COLA is % of *spendable income*, so its
    dollar value is an **estimate** flagged with the family-size assumption and
    withheld (not guessed) when the salary is below the published table. An
    unmatched post returns GS base only with an explicit note — never fabricated
    numbers.
    """
    base = float(base_salary) if base_salary is not None else None
    matched = overseas_post_allowance(conn, country, city)
    result: dict[str, Any] = {
        "base_salary": base,
        "matched_post": None,
        "lines": [],
        "estimated_total": base,
        "notes": [],
        "family_size": int(family_size),
    }
    if matched is None:
        result["notes"].append(
            "Duty station not matched in the DSSR allowance tables — GS base "
            "shown; post allowances unknown."
        )
        return result

    result["matched_post"] = {
        "country_name": matched.get("country_name"),
        "post_name": matched.get("post_name"),
        "match": matched.get("match"),
    }
    if matched.get("match") == "country":
        result["notes"].append(
            f"No exact post match; using {matched.get('country_name')} country-level "
            "(\"Other\") rates — approximate for this specific city."
        )
    eff = matched.get("effective_date")
    lines: list[dict[str, Any]] = []

    def _amount(pct: float | None) -> float | None:
        if pct is None or base is None:
            return None
        return round(base * pct / 100.0, 2)

    hardship_pct = matched.get("post_differential_pct")
    if hardship_pct is not None:
        lines.append({
            "label": "Post (hardship) differential", "dssr": "DSSR 500",
            "pct": hardship_pct, "basis": "% of base pay", "amount": _amount(hardship_pct),
            "estimated": False, "source_url": _DSSR_HARDSHIP_URL, "effective_date": eff,
        })
    danger_pct = matched.get("danger_pay_pct")
    if danger_pct is not None:
        lines.append({
            "label": "Danger pay", "dssr": "DSSR 650",
            "pct": danger_pct, "basis": "% of base pay", "amount": _amount(danger_pct),
            "estimated": False, "source_url": _DSSR_DANGER_URL, "effective_date": eff,
        })
    cola_pct = matched.get("cola_pct_spendable_income")
    if cola_pct is not None:
        si = spendable_income_for(conn, base, family_size)
        cola_amount = None
        estimated = True
        assumption = f"family size {int(family_size)}"
        if cola_pct == 0:
            cola_amount = 0.0
        elif si is not None:
            cola_amount = round(cola_pct / 100.0 * si["annual_spendable_income"], 2)
        else:
            result["notes"].append(
                "Post (COLA) allowance dollar estimate withheld: the posting's "
                "salary is outside the published Spendable Income Table."
            )
        lines.append({
            "label": "Post (COLA) allowance", "dssr": "DSSR 220",
            "pct": cola_pct, "basis": "% of spendable income", "amount": cola_amount,
            "estimated": estimated, "assumption": assumption,
            "source_url": _DSSR_COLA_URL, "effective_date": eff,
        })

    result["lines"] = lines
    if base is not None:
        total = base + sum(
            (line["amount"] or 0.0) for line in lines if line.get("amount") is not None
        )
        result["estimated_total"] = round(total, 2)
    return result
