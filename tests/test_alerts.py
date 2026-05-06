from __future__ import annotations

from datetime import date
import sqlite3

import pytest

from src.alerts import dismiss_alert, generate_alerts
from src.database import connect, init_schema, record_match_score, upsert_job, upsert_job_text
from src.ui_data import alerts_dataframe, create_saved_search, database_status, run_alerts


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "alerts.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _seed_alert_jobs(conn: sqlite3.Connection) -> tuple[int, int, int]:
    fema_id = upsert_job(
        conn,
        {
            "source": "usajobs_historic",
            "usajobs_control_number": "100",
            "position_id": "100",
            "announcement_number": "FEMA-100",
            "title": "Emergency Management Specialist",
            "department": "Department of Homeland Security",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "department_code": "HS",
            "series": "0089",
            "grade_low": "13",
            "grade_high": "13",
            "state": "IL",
            "city": "Chicago",
            "remote_status": "hybrid",
            "open_date": "2026-05-01",
            "close_date": "2026-05-07",
            "categories": [{"series": "0089"}],
            "locations": [{"city": "Chicago", "state": "IL"}],
            "hiring_path_rows": [{"code": "public", "label": "The public"}],
        },
    )
    upsert_job_text(
        conn,
        fema_id,
        {
            "summary": "Leads disaster recovery and public assistance programs.",
            "qualifications": "Applicants must meet GS-13 specialized experience.",
        },
    )
    other_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "200",
            "position_id": "200",
            "announcement_number": "OTHER-200",
            "title": "Accountant",
            "agency": "Other Agency",
            "agency_code": "OTHR",
            "series": "0510",
            "grade_high": "11",
            "state": "CA",
            "remote_status": "onsite",
            "open_date": "2026-05-01",
            "close_date": "2026-06-01",
        },
    )
    repost_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "101",
            "position_id": "101",
            "announcement_number": "FEMA-101",
            "title": "Emergency Management Specialist",
            "department": "Department of Homeland Security",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "department_code": "HS",
            "series": "0089",
            "grade_high": "13",
            "state": "WI",
            "remote_status": "hybrid",
            "open_date": "2026-05-02",
            "close_date": "2026-05-30",
        },
    )
    return fema_id, other_id, repost_id


def test_generate_alerts_creates_high_score_closing_and_dedupes(conn):
    fema_id, other_id, _ = _seed_alert_jobs(conn)
    record_match_score(
        conn,
        job_id=fema_id,
        score=86,
        scoring_version="v1.0",
        explanation="Strong FEMA match.",
    )
    record_match_score(
        conn,
        job_id=other_id,
        score=20,
        scoring_version="v1.0",
        explanation="Weak match.",
    )

    created = generate_alerts(conn, today=date(2026, 5, 5), high_score_threshold=75)
    assert created >= 2
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='high_score'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE alert_type='closing_soon'").fetchone()[0] == 1

    assert generate_alerts(conn, today=date(2026, 5, 5), high_score_threshold=75) == 0


def test_saved_search_alerts_match_structured_fields_and_keyword(conn):
    fema_id, _, _ = _seed_alert_jobs(conn)
    record_match_score(
        conn,
        job_id=fema_id,
        score=80,
        scoring_version="v1.0",
        explanation="Strong match.",
    )
    create_saved_search(
        conn,
        name="FEMA disaster work",
        query_params={
            "HiringAgencyCodes": "HSCB",
            "JobCategoryCode": "0089",
            "LocationName": "Chicago",
            "Keyword": "disaster recovery",
        },
        alert_enabled=True,
    )

    created = generate_alerts(conn, today=date(2026, 5, 5))
    assert created >= 1
    row = conn.execute(
        "SELECT details_json FROM alerts WHERE alert_type='saved_search_match'"
    ).fetchone()
    assert row is not None
    details = row["details_json"]
    assert "HiringAgencyCodes" in details
    assert "JobCategoryCode" in details
    assert "Keyword" in details


def test_reposted_alert_and_ui_helpers(conn):
    _seed_alert_jobs(conn)
    created = run_alerts(conn)
    assert created >= 1

    alerts = alerts_dataframe(conn)
    assert "reposted" in set(alerts["alert_type"])

    alert_id = int(alerts.iloc[0]["id"])
    dismiss_alert(conn, alert_id)
    after = alerts_dataframe(conn)
    assert alert_id not in set(after["id"])

    status = database_status(conn)
    assert status["alerts"] >= 1
    assert status["last_alert_run"] is not None
