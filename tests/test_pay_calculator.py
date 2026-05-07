from __future__ import annotations

import sqlite3

import pytest

from src.database import (
    connect,
    init_schema,
    upsert_geocoded_location,
    utc_now,
)
from src.pay_calculator import calculate_job_pay_table, lookup_single_rate


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
        """,
        (code, year, name, adjustment_pct, now),
    )
    for fips in counties:
        conn.execute(
            """
            INSERT INTO locality_pay_counties (locality_code, year, county_fips, inclusion_type)
            VALUES (?, ?, ?, 'core')
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


def test_returns_locality_row_when_present(conn):
    upsert_geocoded_location(
        conn, city="Chicago", state="IL", lat=41.8781, lon=-87.6298, county_fips="17031"
    )
    _seed_locality(
        conn, code="CHI", year=2026, name="Chicago-Naperville",
        adjustment_pct=32.45, counties=["17031"],
    )
    # Use a hand-picked illustrative value for the published OPM 2026 GS-13 step 5 Chicago.
    # This is the calculator's contract: when a locality-specific row exists, it's
    # used verbatim — no derivation from base + percentage.
    expected_value = 122_500.00
    _seed_pay_row(
        conn, pay_plan_code="GS", year=2026, grade="13", step=5,
        locality_code="CHI", rate=expected_value,
    )

    table = calculate_job_pay_table(
        conn,
        pay_plan_code="GS",
        year=2026,
        city="Chicago",
        state="IL",
        grade_low=13,
        grade_high=13,
    )
    cell = table["grades"]["13"]["05"]
    assert cell["rate"] == expected_value
    assert cell["method"] == "locality_row"
    assert table["locality"]["code"] == "CHI"


def test_falls_back_to_base_plus_adjustment(conn):
    upsert_geocoded_location(
        conn, city="Chicago", state="IL", lat=41.8781, lon=-87.6298, county_fips="17031"
    )
    _seed_locality(
        conn, code="CHI", year=2026, name="Chicago-Naperville",
        adjustment_pct=32.45, counties=["17031"],
    )
    _seed_pay_row(
        conn, pay_plan_code="GS", year=2026, grade="13", step=5,
        locality_code="", rate=92_000,
    )

    cell = calculate_job_pay_table(
        conn, pay_plan_code="GS", year=2026, city="Chicago", state="IL",
        grade_low=13, grade_high=13,
    )["grades"]["13"]["05"]

    expected = round(92_000 * 1.3245, 2)
    assert cell["rate"] == expected
    assert cell["method"] == "base_plus_adjustment"
    assert cell["adjustment_pct"] == pytest.approx(32.45)


def test_grade_range_expansion(conn):
    upsert_geocoded_location(
        conn, city="Chicago", state="IL", lat=41.8781, lon=-87.6298, county_fips="17031"
    )
    _seed_locality(conn, code="CHI", year=2026, name="Chicago", adjustment_pct=30.0, counties=["17031"])
    for grade in ("13", "14", "15"):
        _seed_pay_row(
            conn, pay_plan_code="GS", year=2026, grade=grade, step=1,
            locality_code="", rate=80_000,
        )

    table = calculate_job_pay_table(
        conn, pay_plan_code="GS", year=2026, city="Chicago", state="IL",
        grade_low=13, grade_high=15,
    )
    assert sorted(table["grades"].keys()) == ["13", "14", "15"]


def test_falls_back_to_rus_when_no_locality_match(conn):
    _seed_locality(
        conn, code="RUS", year=2026, name="Rest of U.S.", adjustment_pct=17.0, counties=[]
    )
    _seed_pay_row(
        conn, pay_plan_code="GS", year=2026, grade="13", step=1,
        locality_code="", rate=80_000,
    )

    table = calculate_job_pay_table(
        conn, pay_plan_code="GS", year=2026, city="Coopersville", state="MI",
        grade_low=13, grade_high=13,
    )
    assert table["locality"]["code"] == "RUS"
    cell = table["grades"]["13"]["01"]
    assert cell["method"] == "base_plus_adjustment"
    assert cell["rate"] == round(80_000 * 1.17, 2)


def test_emits_note_when_pay_plan_unknown(conn):
    table = calculate_job_pay_table(
        conn, pay_plan_code="ZZ-NOT-A-PLAN", year=2026, city=None, state="ID",
        grade_low=1, grade_high=1,
    )
    assert any("not registered" in n for n in table["notes"])


def test_lookup_single_rate_locality_row(conn):
    upsert_geocoded_location(
        conn, city="Chicago", state="IL", lat=41.8781, lon=-87.6298, county_fips="17031"
    )
    _seed_locality(conn, code="CHI", year=2026, name="Chicago", adjustment_pct=32.45, counties=["17031"])
    _seed_pay_row(
        conn, pay_plan_code="GS", year=2026, grade="13", step=5,
        locality_code="CHI", rate=122_500,
    )

    cell = lookup_single_rate(
        conn, pay_plan_code="GS", year=2026, city="Chicago", state="IL",
        grade=13, step=5,
    )
    assert cell["rate"] == 122_500
    assert cell["method"] == "locality_row"
    assert cell["locality"]["code"] == "CHI"
