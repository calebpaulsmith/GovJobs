from __future__ import annotations

import sqlite3

import pytest

from src.database import connect, init_schema, upsert_job
from src.ui_data import (
    database_status,
    add_application_event_workflow,
    application_events_dataframe,
    applications_dataframe,
    current_location_coverage,
    grouped_counts,
    jobs_dataframe,
    resume_versions_dataframe,
    run_match_scores,
    save_job_workflow,
    saved_jobs_dataframe,
    scorecard_dataframe,
    set_resume_version_active_workflow,
    state_counts,
    multi_location_jobs,
    non_mappable_current_postings,
    remote_anywhere_jobs,
    work_location_points,
    upsert_application_workflow,
    upsert_resume_version_workflow,
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
            "locations": [
                {"city": "Chicago", "state": "IL", "latitude": 41.8781, "longitude": -87.6298},
                {"city": "Madison", "state": "WI", "latitude": 43.0731, "longitude": -89.4012},
            ],
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
            "locations": [{"state": "CA", "latitude": 38.5816, "longitude": -121.4944}],
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


def test_application_tracker_workflow_syncs_saved_status(conn):
    fema_id, _ = _seed(conn)
    save_job_workflow(conn, job_id=fema_id, status="Interested", priority=2)

    application_id = upsert_application_workflow(
        conn,
        job_id=fema_id,
        application_status="Submitted",
        resume_version="fema-v1",
        usajobs_application_id="APP-1",
        submitted_at="2026-05-06",
        next_action="Check status",
        next_action_due="2026-05-20",
        event_note="Submitted package.",
    )
    add_application_event_workflow(
        conn,
        application_id=application_id,
        event_type="note",
        event_date="2026-05-07",
        notes="Confirmation email received.",
    )

    apps = applications_dataframe(conn)
    events = application_events_dataframe(conn, application_id)
    saved = saved_jobs_dataframe(conn)

    assert apps.iloc[0]["application_status"] == "Submitted"
    assert apps.iloc[0]["resume_version"] == "fema-v1"
    assert len(events) == 2
    assert saved.iloc[0]["status"] == "Applied"


def test_resume_version_workflow(conn):
    version_id = upsert_resume_version_workflow(
        conn,
        label="fema-gs13-v2",
        file_name="resume.pdf",
        version_date="2026-05-06",
        target_series="0089",
        target_grade="GS-13",
        notes="FEMA mitigation version.",
    )
    set_resume_version_active_workflow(conn, version_id, active=False)

    versions = resume_versions_dataframe(conn)
    active = resume_versions_dataframe(conn, active_only=True)

    assert versions.iloc[0]["label"] == "fema-gs13-v2"
    assert versions.iloc[0]["active"] == 0
    assert active.empty


def test_status_and_grouped_counts(conn):
    _seed(conn)
    status = database_status(conn)
    assert status["jobs"] == 2
    assert status["historic_jobs"] == 1
    grouped = grouped_counts(conn, "series")
    assert set(grouped["label"]) == {"0089", "0510"}
    states = state_counts(conn)
    assert set(states["state"]) == {"IL", "WI", "CA"}


def test_work_location_points_and_remote_anywhere_tables(conn):
    fema_id, other_id = _seed(conn)
    remote_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "3",
            "position_id": "3",
            "announcement_number": "REMOTE-1",
            "title": "Remote Program Analyst",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "series": "0343",
            "grade_high": "13",
            "remote_status": "remote",
            "locations": [
                {
                    "location_text": "Anywhere in the U.S. (remote job)",
                    "latitude": 39.8283,
                    "longitude": -98.5795,
                    "remote_indicator": "remote",
                }
            ],
        },
    )

    points = work_location_points(conn)
    assert set(points["job_id"]) == {fema_id, other_id}
    assert len(points[points["job_id"] == fema_id]) == 2
    assert "Chicago" in points[points["job_id"] == fema_id].iloc[0]["all_locations"]
    assert "Madison" in points[points["job_id"] == fema_id].iloc[0]["all_locations"]

    single_only = work_location_points(conn, include_multi_location=False)
    assert set(single_only["job_id"]) == {other_id}

    remote = remote_anywhere_jobs(conn)
    assert set(remote["id"]) == {remote_id}

    multi = multi_location_jobs(conn)
    assert set(multi["id"]) == {fema_id}

    coverage = current_location_coverage(conn)
    assert coverage["current_postings"] == 2
    assert coverage["mapped_postings"] == 1
    assert coverage["remote_postings"] == 1


def test_non_mappable_current_postings_are_filtered_by_map_bounds(conn):
    _seed(conn)
    chicago_id = upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "4",
            "position_id": "4",
            "announcement_number": "NOCOORD-1",
            "title": "Chicago Posting Without Coordinates",
            "agency": "Federal Emergency Management Agency",
            "agency_code": "HSCB",
            "series": "0343",
            "grade_high": "13",
            "state": "IL",
            "city": "Chicago",
            "remote_status": "onsite",
            "locations": [{"city": "Chicago", "state": "IL"}],
        },
    )
    upsert_job(
        conn,
        {
            "source": "usajobs_search",
            "usajobs_control_number": "5",
            "position_id": "5",
            "announcement_number": "NOCOORD-2",
            "title": "California Posting Without Coordinates",
            "agency": "Other Agency",
            "agency_code": "OTHR",
            "series": "0510",
            "grade_high": "11",
            "state": "CA",
            "remote_status": "onsite",
            "locations": [{"state": "CA"}],
        },
    )

    bounds = {"south": 36.0, "north": 44.0, "west": -92.0, "east": -84.0}
    unmapped = non_mappable_current_postings(conn, bounds=bounds)

    assert set(unmapped["id"]) == {chicago_id}
    assert unmapped.iloc[0]["all_locations"] == "Chicago, IL"


def test_match_scores_feed_scorecard(conn):
    _seed(conn)
    created = run_match_scores(conn)
    assert created == 2
    card = scorecard_dataframe(conn)
    assert len(card) == 2
    assert card.iloc[0]["score"] > card.iloc[1]["score"]
    assert card.iloc[0]["agency"] == "Federal Emergency Management Agency"
