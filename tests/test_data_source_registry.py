from __future__ import annotations

import sqlite3

import pytest

from src.data_source_registry import (
    begin_run,
    complete_run,
    fail_run,
    freshness_summary,
    get_status,
    list_status,
    set_manual_override,
)
from src.database import connect, init_schema


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "federal_jobs.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def test_begin_run_creates_row(conn):
    begin_run(conn, "census_states", "Census state polygons", "geometry")
    status = get_status(conn, "census_states")
    assert status is not None
    assert status["display_name"] == "Census state polygons"
    assert status["category"] == "geometry"
    assert status["last_run_at"] is not None
    assert status["last_success_at"] is None
    assert status["last_error"] is None


def test_complete_run_records_row_count_and_clears_error(conn):
    begin_run(conn, "bea_rpp", "BEA RPP", "col")
    fail_run(conn, "bea_rpp", "boom")
    assert get_status(conn, "bea_rpp")["last_error"] == "boom"

    complete_run(conn, "bea_rpp", row_count=51, notes="state level only")
    status = get_status(conn, "bea_rpp")
    assert status["row_count"] == 51
    assert status["last_error"] is None
    assert status["last_success_at"] is not None
    assert status["notes"] == "state level only"


def test_fail_run_truncates_long_error_messages(conn):
    begin_run(conn, "opm_gs_pay", "OPM GS Pay", "pay")
    fail_run(conn, "opm_gs_pay", "X" * 4000)
    assert len(get_status(conn, "opm_gs_pay")["last_error"]) <= 2000


def test_set_manual_override_toggles_flag(conn):
    begin_run(conn, "opm_locality_pay", "OPM locality %", "pay")
    set_manual_override(conn, "opm_locality_pay", True, notes="2026 corrected manually")
    status = get_status(conn, "opm_locality_pay")
    assert status["manual_override"] == 1
    assert status["notes"] == "2026 corrected manually"

    set_manual_override(conn, "opm_locality_pay", False)
    assert get_status(conn, "opm_locality_pay")["manual_override"] == 0


def test_invalid_category_rejected(conn):
    with pytest.raises(ValueError):
        begin_run(conn, "bad", "Bad", "not_a_category")


def test_list_status_filters_by_category(conn):
    begin_run(conn, "census_states", "States", "geometry")
    begin_run(conn, "opm_gs_pay", "GS pay", "pay")
    geometry_only = list_status(conn, category="geometry")
    assert {row["source_key"] for row in geometry_only} == {"census_states"}


def test_freshness_summary_counts_states(conn):
    begin_run(conn, "a", "A", "pay")
    complete_run(conn, "a", row_count=10)
    begin_run(conn, "b", "B", "pay")
    fail_run(conn, "b", "boom")
    begin_run(conn, "c", "C", "pay")  # no completion, no error -> "missing"

    summary = freshness_summary(conn)
    assert summary["total"] == 3
    assert summary["succeeded"] == 1
    assert summary["errored"] == 1
    assert summary["missing"] == 1
