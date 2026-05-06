from __future__ import annotations

import json
import sqlite3

import pytest

from src.database import connect, init_schema, upsert_job, upsert_job_text
from src.scoring import SCORING_VERSION, score_all_jobs, score_job, scoring_context


def _factor_names(result) -> set[str]:
    return {factor["factor"] for factor in result.positive_factors + result.negative_factors}


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "scoring.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def test_score_job_prioritizes_target_fema_remote_midwest_work():
    result = score_job(
        {
            "title": "Emergency Management Specialist",
            "department": "Department of Homeland Security",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "series": "0089",
            "series_values": ["0089"],
            "grade_high": "13",
            "grades": [{"pay_plan": "GS", "grade_low": "13", "grade_high": "13"}],
            "city": "Chicago",
            "state": "IL",
            "remote_status": "remote",
            "summary": "Lead emergency management, hazard mitigation, grants, resilience, and disaster recovery programs.",
            "duty_rows": ["Coordinate Public Assistance and infrastructure recovery policy."],
        }
    )

    assert result.score >= 80
    assert result.scoring_version == SCORING_VERSION
    assert any(factor["factor"] == "FEMA" for factor in result.positive_factors)
    assert any(factor["factor"] == "target grade" for factor in result.positive_factors)
    assert not result.negative_factors


def test_score_job_marks_non_target_and_missing_info():
    result = score_job(
        {
            "title": "Accountant",
            "agency": "Other Agency",
            "series": "0510",
            "grade_high": "9",
            "state": "CA",
            "remote_status": "unknown",
        }
    )

    assert result.score < 25
    assert any(factor["factor"] == "below target grade" for factor in result.negative_factors)
    assert any(item["field"] == "job_text" for item in result.missing_info)


@pytest.mark.parametrize(
    ("text", "expected_factor"),
    [
        ("This role supports emergency management operations.", "emergency management"),
        ("This role supports hazard mitigation planning.", "mitigation"),
        ("This role manages Public Assistance delivery.", "public assistance"),
        ("This role handles grants management.", "grants management"),
        ("This role supports disaster recovery programs.", "disaster recovery"),
        ("This role performs policy analysis and program analysis.", "policy/program analysis"),
        ("This role supports infrastructure recovery.", "infrastructure"),
        ("This role advances community resilience.", "resilience"),
    ],
)
def test_score_job_covers_each_topic_rule(text, expected_factor):
    result = score_job(
        {
            "agency": "Other Agency",
            "series": "0510",
            "grade_high": "12",
            "state": "IL",
            "remote_status": "onsite",
            "summary": text,
        }
    )

    assert expected_factor in _factor_names(result)


@pytest.mark.parametrize(
    ("series", "expected_weight"),
    [
        ("0089", 10),
        ("0343", 8),
        ("0301", 8),
        ("1109", 8),
        ("0020", 5),
        ("0101", 5),
        ("0110", 5),
        ("0300", 5),
        ("0501", 5),
        ("0560", 5),
    ],
)
def test_score_job_covers_priority_series_weights(series, expected_weight):
    result = score_job(
        {
            "agency": "Other Agency",
            "series": series,
            "grade_high": "12",
            "state": "IL",
            "remote_status": "onsite",
            "summary": "General program work.",
        }
    )

    factor = next(item for item in result.positive_factors if item["factor"] == "priority series")
    assert factor["weight"] == expected_weight


@pytest.mark.parametrize(
    ("grade", "expected_weight"),
    [("13", 10), ("14", 12), ("15", 12), ("12", 4)],
)
def test_score_job_covers_grade_rules(grade, expected_weight):
    result = score_job(
        {
            "agency": "Other Agency",
            "series": "0510",
            "grade_high": grade,
            "state": "IL",
            "remote_status": "onsite",
            "summary": "General program work.",
        }
    )

    factor_name = "near target grade" if grade == "12" else "target grade"
    factor = next(item for item in result.positive_factors if item["factor"] == factor_name)
    assert factor["weight"] == expected_weight


def test_score_job_covers_agency_location_workstyle_and_supervisory_rules():
    dhs = score_job(
        {
            "department": "Department of Homeland Security",
            "department_code": "HS",
            "series": "0510",
            "grade_high": "12",
            "state": "WI",
            "remote_status": "hybrid",
            "summary": "Supervisory program work.",
        }
    )
    fema = score_job(
        {
            "agency_code": "HSCB",
            "series": "0510",
            "grade_high": "12",
            "city": "Chicago",
            "state": "IL",
            "remote_status": "remote",
            "summary": "General program work.",
        }
    )

    assert {"DHS", "Midwest", "telework/hybrid", "supervisory"} <= _factor_names(dhs)
    assert {"FEMA", "Chicago", "remote"} <= _factor_names(fema)


def test_score_all_jobs_stores_v1_scores(conn):
    job_id = upsert_job(
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
            "series": "0089",
            "grade_high": "13",
            "state": "IL",
            "city": "Chicago",
            "remote_status": "hybrid",
            "categories": [{"series": "0089"}],
            "grade_rows": [{"pay_plan": "GS", "grade_low": "13", "grade_high": "13"}],
            "locations": [{"city": "Chicago", "state": "IL"}],
        },
    )
    upsert_job_text(
        conn,
        job_id,
        {
            "summary": "This role manages mitigation and disaster recovery programs.",
            "duties": "Coordinate grants management and infrastructure resilience policy.",
            "qualifications": "One year specialized experience equivalent to GS-12.",
            "qualification_requirement_rows": [
                {"text": "One year specialized experience equivalent to GS-12.", "grade": "12"}
            ],
            "duty_rows": [
                {"text": "Coordinate grants management and infrastructure resilience policy."}
            ],
        },
    )

    assert score_all_jobs(conn) == 1
    assert score_all_jobs(conn) == 0

    row = conn.execute("SELECT * FROM match_scores WHERE job_id=?", (job_id,)).fetchone()
    assert row["scoring_version"] == SCORING_VERSION
    assert row["score"] >= 60
    positives = json.loads(row["positive_factors_json"])
    assert any(item["factor"] == "FEMA" for item in positives)

    context = scoring_context(conn, job_id)
    assert context["series_values"] == ["0089"]
