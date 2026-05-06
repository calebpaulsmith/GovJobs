from __future__ import annotations

import json
import sqlite3

import pytest

from src.database import connect, init_schema, record_job_feedback, record_match_score, upsert_job, upsert_job_text
from src.recommendations import generate_similar_jobs
from src.ui_data import (
    feedback_dataframe,
    recommendations_dataframe,
    record_feedback_workflow,
    run_similar_jobs,
)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "recommendations.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _seed_jobs(conn: sqlite3.Connection) -> tuple[int, int, int]:
    seed_id = upsert_job(
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
            "remote_status": "hybrid",
            "locations": [{"state": "IL", "city": "Chicago"}],
            "categories": [{"series": "0089"}],
            "grade_rows": [{"pay_plan": "GS", "grade_low": "13", "grade_high": "13"}],
            "hiring_path_rows": [{"code": "public", "label": "The public"}],
        },
    )
    upsert_job_text(
        conn,
        seed_id,
        {
            "summary": "Leads hazard mitigation and disaster recovery work.",
            "duties": "Coordinate public assistance and resilience programs.",
        },
    )
    record_match_score(conn, job_id=seed_id, score=91, scoring_version="v1.0")

    similar_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "2",
            "position_id": "2",
            "announcement_number": "FEMA-2",
            "title": "Mitigation Program Analyst",
            "department": "Department of Homeland Security",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "department_code": "HS",
            "series": "0343",
            "grade_high": "13",
            "state": "WI",
            "remote_status": "hybrid",
            "locations": [{"state": "WI", "city": "Madison"}],
            "categories": [{"series": "0343"}, {"series": "0089"}],
            "grade_rows": [{"pay_plan": "GS", "grade_low": "13", "grade_high": "13"}],
            "hiring_path_rows": [{"code": "public", "label": "The public"}],
        },
    )
    upsert_job_text(
        conn,
        similar_id,
        {
            "summary": "Supports mitigation, public assistance, and resilience policy.",
            "duties": "Analyze disaster recovery program performance.",
        },
    )
    record_match_score(conn, job_id=similar_id, score=87, scoring_version="v1.0")

    weak_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "3",
            "position_id": "3",
            "announcement_number": "OTHER-3",
            "title": "Accountant",
            "agency": "Other Agency",
            "agency_code": "OTHR",
            "series": "0510",
            "grade_high": "9",
            "state": "CA",
            "remote_status": "onsite",
            "locations": [{"state": "CA"}],
            "categories": [{"series": "0510"}],
            "grade_rows": [{"pay_plan": "GS", "grade_low": "9", "grade_high": "9"}],
        },
    )
    record_match_score(conn, job_id=weak_id, score=12, scoring_version="v1.0")
    return seed_id, similar_id, weak_id


def test_generate_similar_jobs_records_explainable_factors(conn):
    seed_id, similar_id, weak_id = _seed_jobs(conn)
    record_job_feedback(
        conn,
        job_id=seed_id,
        feedback_type="more_like_this",
        explanation="More mitigation and public assistance roles.",
    )

    result = generate_similar_jobs(conn, seed_job_id=seed_id, limit=10)
    rows = conn.execute(
        """
        SELECT * FROM job_recommendations
        WHERE run_id=?
        ORDER BY score DESC
        """,
        (result.run_id,),
    ).fetchall()

    assert result.recommendations_created >= 1
    assert int(rows[0]["job_id"]) == similar_id
    assert int(rows[0]["job_id"]) != weak_id
    factors = json.loads(rows[0]["factors_json"])
    assert {factor["factor"] for factor in factors} >= {"same agency code", "shared grade"}
    assert rows[0]["explanation"].startswith("Recommendation score")


def test_negative_feedback_can_suppress_matching_jobs(conn):
    seed_id, similar_id, _ = _seed_jobs(conn)
    record_job_feedback(conn, job_id=similar_id, feedback_type="less_like_this", explanation="Not this travel profile.")

    result = generate_similar_jobs(conn, seed_job_id=seed_id, limit=10)
    row = conn.execute(
        """
        SELECT factors_json
        FROM job_recommendations
        WHERE run_id=? AND job_id=?
        """,
        (result.run_id, similar_id),
    ).fetchone()

    assert row is None


def test_ui_helpers_record_feedback_and_return_recommendations(conn):
    seed_id, similar_id, _ = _seed_jobs(conn)
    feedback_id = record_feedback_workflow(
        conn,
        job_id=seed_id,
        feedback_type="liked",
        explanation="Good emergency management target.",
    )
    run_id = run_similar_jobs(conn, seed_job_id=seed_id, limit=5)

    feedback = feedback_dataframe(conn, seed_id)
    recommendations = recommendations_dataframe(conn, run_id=run_id)

    assert int(feedback.iloc[0]["id"]) == feedback_id
    assert similar_id in set(recommendations["job_id"])
    assert "factors_json" in recommendations.columns
