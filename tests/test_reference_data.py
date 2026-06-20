from __future__ import annotations

import sqlite3

import pytest

from src.database import (
    connect,
    init_schema,
    upsert_geocoded_location,
    utc_now,
)
from src.reference_data import (
    base_pay_scale,
    cost_of_living,
    locality_for_city_state,
    locality_for_county,
    locality_or_rus,
    pay_plan,
    pay_scale_lookup,
    pay_scales_for_grade,
)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "federal_jobs.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _seed_locality(conn, *, code, year, name, adjustment_pct, counties):
    now = utc_now()
    conn.execute(
        """
        INSERT INTO locality_pay_areas (
            code, year, name, description, adjustment_pct,
            polygon_path, source, source_url, imported_at
        ) VALUES (?, ?, ?, NULL, ?, NULL, 'test', NULL, ?)
        ON CONFLICT(code, year) DO UPDATE SET
            adjustment_pct=excluded.adjustment_pct,
            imported_at=excluded.imported_at
        """,
        (code, year, name, adjustment_pct, now),
    )
    for fips in counties:
        conn.execute(
            """
            INSERT INTO locality_pay_counties (locality_code, year, county_fips, inclusion_type)
            VALUES (?, ?, ?, 'core')
            ON CONFLICT(locality_code, year, county_fips) DO NOTHING
            """,
            (code, year, fips),
        )
    conn.commit()


def _seed_pay_row(conn, *, pay_plan_code, year, grade, step, locality_code, rate):
    conn.execute(
        """
        INSERT INTO pay_scales (
            pay_plan, year, grade, step, locality_code,
            annual_rate, source, source_url, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'test', NULL, ?)
        """,
        (pay_plan_code, year, grade, step, locality_code, rate, utc_now()),
    )
    conn.commit()


def test_pay_plan_seed_includes_gs(conn):
    plan = pay_plan(conn, "GS")
    assert plan is not None
    assert plan["has_locality_adjustment"] == 1
    assert plan["has_steps"] == 1


def test_locality_for_county_returns_match(conn):
    _seed_locality(
        conn,
        code="CHI",
        year=2026,
        name="Chicago-Naperville",
        adjustment_pct=32.45,
        counties=["17031", "17043"],
    )
    match = locality_for_county(conn, "17031", 2026)
    assert match is not None
    assert match["code"] == "CHI"
    assert match["adjustment_pct"] == pytest.approx(32.45)


def test_locality_for_city_state_uses_geocoded_county(conn):
    upsert_geocoded_location(
        conn,
        city="Chicago",
        state="IL",
        lat=41.8781,
        lon=-87.6298,
        county_fips="17031",
    )
    _seed_locality(
        conn,
        code="CHI",
        year=2026,
        name="Chicago-Naperville",
        adjustment_pct=32.45,
        counties=["17031"],
    )
    match = locality_for_city_state(conn, "Chicago", "IL", 2026)
    assert match is not None
    assert match["code"] == "CHI"


def test_locality_or_rus_falls_back(conn):
    _seed_locality(
        conn, code="RUS", year=2026, name="Rest of U.S.", adjustment_pct=17.0, counties=[]
    )
    locality = locality_or_rus(conn, "Nowheresville", "ID", 2026)
    assert locality["code"] == "RUS"
    assert locality["adjustment_pct"] == pytest.approx(17.0)


def test_locality_or_rus_returns_synthetic_when_unloaded(conn):
    locality = locality_or_rus(conn, None, "ZZ", 2030)
    assert locality["code"] == "RUS"
    assert locality["source"] == "synthetic"


def test_pay_scale_lookup_with_locality_and_base(conn):
    _seed_pay_row(conn, pay_plan_code="GS", year=2026, grade="13", step=1, locality_code="", rate=88_000)
    _seed_pay_row(conn, pay_plan_code="GS", year=2026, grade="13", step=1, locality_code="CHI", rate=110_803)

    base = base_pay_scale(conn, pay_plan_code="GS", year=2026, grade="13", step=1)
    chi = pay_scale_lookup(
        conn, pay_plan_code="GS", year=2026, grade="13", step=1, locality_code="CHI"
    )
    assert base["annual_rate"] == 88_000
    assert chi["annual_rate"] == 110_803


def test_pay_scales_for_grade_orders_by_step(conn):
    for step, rate in [(3, 95000), (1, 88000), (2, 91500)]:
        _seed_pay_row(
            conn, pay_plan_code="GS", year=2026, grade="13", step=step, locality_code="", rate=rate
        )
    rows = pay_scales_for_grade(conn, pay_plan_code="GS", year=2026, grade="13")
    assert [r["step"] for r in rows] == [1, 2, 3]


def test_cost_of_living_prefers_bea_when_multiple_sources(conn):
    now = utc_now()
    conn.executemany(
        """
        INSERT INTO cost_of_living_index (
            year, geo_type, geo_code, rpp_overall, rpp_goods, rpp_services, rpp_rents,
            source, imported_at
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
        """,
        [
            (2024, "state", "IL", 99.5, "bea:rpp", now),
            (2024, "state", "IL", 100.2, "c2er:cost_index", now),
        ],
    )
    conn.commit()
    row = cost_of_living(conn, geo_type="state", geo_code="IL", year=2024)
    assert row["source"] == "bea:rpp"
    assert row["rpp_overall"] == pytest.approx(99.5)


def test_cost_of_living_returns_latest_year_when_unspecified(conn):
    now = utc_now()
    conn.executemany(
        """
        INSERT INTO cost_of_living_index (
            year, geo_type, geo_code, rpp_overall, rpp_goods, rpp_services, rpp_rents,
            source, imported_at
        ) VALUES (?, 'state', 'TX', ?, NULL, NULL, NULL, 'bea:rpp', ?)
        """,
        [(2022, 96.0, now), (2024, 97.5, now)],
    )
    conn.commit()
    assert cost_of_living(conn, geo_type="state", geo_code="TX")["year"] == 2024


# --- Overseas DSSR allowances (Stage 4) ------------------------------------
from src.reference_data import (  # noqa: E402
    overseas_compensation,
    overseas_post_allowance,
    spendable_income_for,
)
from src.database import utc_now  # noqa: E402


def _seed_dssr(conn):
    now = utc_now()
    rows = [
        # country_iso, country_name, post, hardship, danger, cola
        ("IT", "ITALY", "Rome", 0.0, None, 30.0),
        ("IT", "ITALY", "Other", 5.0, None, 25.0),
        ("AF", "AFGHANISTAN", "Kabul", 35.0, 35.0, 0.0),
    ]
    for iso, name, post, h, d, c in rows:
        conn.execute(
            "INSERT INTO overseas_post_allowances (country_iso, country_name, "
            "post_name, post_differential_pct, danger_pay_pct, "
            "cola_pct_spendable_income, effective_date, source_url, imported_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (iso, name, post, h, d, c, "2026-06-14", "https://allowances.state.gov/", now),
        )
    conn.execute(
        "INSERT INTO spendable_income (salary_min, salary_max, family_size, "
        "annual_spendable_income, effective_date, source_url, imported_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (100000, 105999, 1, 37200, "2023-01-01", "https://allowances.state.gov/x.docx", now),
    )
    conn.commit()


def test_overseas_post_allowance_match_precision(conn):
    _seed_dssr(conn)
    exact = overseas_post_allowance(conn, "IT", "Rome")
    assert exact["match"] == "post" and exact["post_name"] == "Rome"
    # Unknown city in a known country falls back to the "Other" country row.
    fallback = overseas_post_allowance(conn, "IT", "Nowheresville")
    assert fallback["match"] == "country" and fallback["post_name"] == "Other"
    # Unknown country -> no match.
    assert overseas_post_allowance(conn, "ZZ", "Atlantis") is None


def test_spendable_income_lookup(conn):
    _seed_dssr(conn)
    row = spendable_income_for(conn, 100000, family_size=1)
    assert row["annual_spendable_income"] == 37200
    # Below the published table -> None (caller must withhold the COLA estimate).
    assert spendable_income_for(conn, 1000, family_size=1) is None
    assert spendable_income_for(conn, None) is None


def test_overseas_compensation_rome_breakdown(conn):
    _seed_dssr(conn)
    comp = overseas_compensation(conn, country="IT", city="Rome", base_salary=100000)
    assert comp["matched_post"]["match"] == "post"
    cola = next(l for l in comp["lines"] if l["dssr"] == "DSSR 220")
    assert cola["pct"] == 30.0
    assert cola["amount"] == pytest.approx(11160.0)  # 30% of 37,200 spendable
    assert cola["estimated"] is True
    assert comp["estimated_total"] == pytest.approx(111160.0)


def test_overseas_compensation_kabul_exact_percent_of_base(conn):
    _seed_dssr(conn)
    comp = overseas_compensation(conn, country="AF", city="Kabul", base_salary=100000)
    amounts = {l["dssr"]: l["amount"] for l in comp["lines"]}
    assert amounts["DSSR 500"] == pytest.approx(35000.0)  # hardship, % of base
    assert amounts["DSSR 650"] == pytest.approx(35000.0)  # danger, % of base
    assert amounts["DSSR 220"] == pytest.approx(0.0)      # cola 0%
    assert comp["estimated_total"] == pytest.approx(170000.0)


def test_overseas_compensation_withholds_cola_dollars_when_salary_below_table(conn):
    _seed_dssr(conn)
    comp = overseas_compensation(conn, country="IT", city="Rome", base_salary=1000)
    cola = next(l for l in comp["lines"] if l["dssr"] == "DSSR 220")
    assert cola["amount"] is None  # withheld, not guessed
    assert any("withheld" in n for n in comp["notes"])


def test_overseas_compensation_unmatched_post_is_base_only(conn):
    _seed_dssr(conn)
    comp = overseas_compensation(conn, country="ZZ", city="Atlantis", base_salary=100000)
    assert comp["matched_post"] is None
    assert comp["lines"] == []
    assert any("not matched" in n for n in comp["notes"])
