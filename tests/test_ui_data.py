from __future__ import annotations

import sqlite3

import pytest

from src.database import connect, init_schema, upsert_job
from src.ui_data import (
    database_status,
    grouped_counts,
    jobs_dataframe,
    run_match_scores,
    save_job_workflow,
    saved_jobs_dataframe,
    scorecard_dataframe,
    state_counts,
)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "ui.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _seed(conn):
    fema_id = upsert_job(
        conn,
        {
            "source": "usajobs_historic",
            "usajobs_control_number": "1",
            "position_id": "1",
            "announcement_number": "FEMA-1",
            "title": "Emergency Management Specialist",
            "department": "Department of Homeland Security",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "department_code": "HS",
            "series": "0089",
            "grade_high": "13",
            "state": "IL",
            "city": "Chicago",
            "remote_status": "hybrid",
            "salary_min": 98000,
            "salary_max": 153000,
            "open_date": "2026-01-01",
            "close_date": "2026-01-15",
            "locations": [{"city": "Chicago", "state": "IL"}, {"city": "Madison", "state": "WI"}],
            "categories": [{"series": "0089"}],
            "grade_rows": [{"pay_plan": "GS", "grade_low": "13", "grade_high": "13"}],
            "salary_range_rows": [{"minimum": 98000, "maximum": 153000}],
            "hiring_path_rows": [{"code": "public", "label": "The public"}],
        },
    )
    other_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "2",
            "position_id": "2",
            "announcement_number": "OTHER-1",
            "title": "Accountant",
            "agency": "Other Agency",
            "agency_code": "OTHR",
            "series": "0510",
            "grade_high": "11",
            "state": "CA",
            "remote_status": "onsite",
            "salary_min": 65000,
            "salary_max": 90000,
            "open_date": "2026-01-01",
            "close_date": "2026-02-01",
            "locations": [{"state": "CA"}],
            "categories": [{"series": "0510"}],
            "grade_rows": [{"pay_plan": "GS", "grade_low": "11", "grade_high": "11"}],
            "salary_range_rows": [{"minimum": 65000, "maximum": 90000}],
            "hiring_path_rows": [{"code": "status", "label": "Federal employees"}],
        },
    )
    return fema_id, other_id


def test_jobs_dataframe_filters_by_priority_fields(conn):
    _seed(conn)
    df = jobs_dataframe(
        conn,
        {
            "agency": "Emergency",
            "agency_code": "HSCB",
            "series": "0089",
            "state": "IL",
            "pay_plan": "GS",
            "grade_low": "13",
            "grade_high": "13",
            "salary_min": 100000,
            "salary_max": 160000,
            "hiring_path": "public",
        },
    )
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Emergency Management Specialist"


def test_saved_job_workflow_records_status_note_and_tag(conn):
    fema_id, _ = _seed(conn)
    save_job_workflow(
        conn,
        job_id=fema_id,
        status="Interested",
        priority=2,
        note="Worth a close look.",
        tag="fema-region-5",
    )
    saved = saved_jobs_dataframe(conn)
    assert saved.iloc[0]["status"] == "Interested"
    assert conn.execute("SELECT COUNT(*) FROM job_notes").fetchone()[0] == 1
    assert conn.execute("SELECT tag FROM job_tags").fetchone()[0] == "fema-region-5"


def test_status_and_grouped_counts(conn):
    _seed(conn)
    status = database_status(conn)
    assert status["jobs"] == 2
    assert status["historic_jobs"] == 1
    grouped = grouped_counts(conn, "series")
    assert set(grouped["label"]) == {"0089", "0510"}
    states = state_counts(conn)
    assert set(states["state"]) == {"IL", "WI", "CA"}


def test_match_scores_feed_scorecard(conn):
    _seed(conn)
    created = run_match_scores(conn)
    assert created == 2
    card = scorecard_dataframe(conn)
    assert len(card) == 2
    assert card.iloc[0]["score"] > card.iloc[1]["score"]
    assert card.iloc[0]["agency"] == "Federal Emergency Management Agency"
