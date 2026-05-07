from __future__ import annotations

import json
import sqlite3

import pytest

from src.database import (
    add_job_note,
    add_job_tag,
    add_application_event,
    complete_manifest,
    connect,
    create_recommendation_run,
    get_job,
    get_job_text,
    init_schema,
    record_job_feedback,
    record_job_recommendation,
    record_match_score,
    record_raw_response,
    remove_job_tag,
    create_job_import_scope,
    save_job,
    start_manifest,
    update_manifest,
    upsert_application,
    upsert_job,
    upsert_job_text,
    upsert_resume_version,
)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "federal_jobs.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _job(**overrides):
    base = {
        "source": "usajobs_historic",
        "usajobs_control_number": "123456789",
        "position_id": "FEMA-24-001",
        "announcement_number": "FEMA-24-001",
        "title": "Emergency Management Specialist",
        "department": "Department of Homeland Security",
        "agency": "Federal Emergency Management Agency",
        "series": "0089",
        "grade_low": "12",
        "grade_high": "13",
        "pay_plan": "GS",
        "salary_min": 98000,
        "salary_max": 153000,
        "location_text": "Chicago, Illinois",
        "state": "IL",
        "city": "Chicago",
        "remote_status": "hybrid",
        "open_date": "2026-05-01",
        "close_date": "2026-05-15",
        "hiring_paths": ["public", "fed-competitive"],
        "source_endpoint": "/api/historicjoa",
    }
    base.update(overrides)
    return base


def test_init_schema_creates_core_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {
        "jobs",
        "job_text",
        "saved_jobs",
        "job_notes",
        "job_tags",
        "raw_api_responses",
        "import_manifests",
        "match_scores",
        "agency_codes",
        "code_lists",
        "job_locations",
        "job_categories",
        "job_hiring_paths",
        "job_required_documents",
        "job_import_scopes",
        "job_grades",
        "job_salary_ranges",
        "job_requirements",
        "job_qualification_requirements",
        "job_duties",
        "job_evaluation_factors",
        "job_openings",
        "job_contacts",
        "job_security_clearances",
        "job_travel_requirements",
        "job_application_options",
        "job_feedback",
        "recommendation_runs",
        "job_recommendations",
        "repost_runs",
        "repost_groups",
        "repost_group_members",
        "applications",
        "application_events",
        "resume_versions",
    }.issubset(tables)
    assert conn.execute("SELECT name FROM agency_codes WHERE code='HSCB'").fetchone()[0]


def test_upsert_job_inserts_and_updates_by_dedup_key(conn):
    job_id = upsert_job(conn, _job())
    same_id = upsert_job(conn, _job(title="Emergency Management Specialist (Mitigation)"))

    assert same_id == job_id
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "Emergency Management Specialist (Mitigation)"
    assert json.loads(rows[0]["hiring_paths"]) == ["public", "fed-competitive"]


def test_upsert_job_populates_repeated_structure_tables(conn):
    job_id = upsert_job(
        conn,
        _job(
            agency_code="HSCB",
            department_code="HS",
            locations=[
                {
                    "location_text": "Chicago, Illinois",
                    "city": "Chicago",
                    "state": "IL",
                    "country": "United States",
                    "latitude": 41.8781,
                    "longitude": -87.6298,
                },
                {
                    "location_text": "Denton, Texas",
                    "city": "Denton",
                    "state": "TX",
                    "country": "United States",
                },
            ],
            categories=[{"series": "0089"}, {"series": "0343", "name": "Program Analysis"}],
            hiring_path_rows=[
                {"code": "public", "label": "The public"},
                {"code": "fed-competitive", "label": "Federal employees"},
            ],
            grade_rows=[
                {
                    "pay_plan": "GS",
                    "grade_low": "12",
                    "grade_high": "13",
                    "promotion_potential": "13",
                }
            ],
            salary_range_rows=[
                {"minimum": 98000, "maximum": 153000, "salary_type": "per_year"}
            ],
            opening_rows=[{"location_text": "Chicago, Illinois", "openings": 2, "total_openings": 3}],
            contact_rows=[{"name": "HR Desk", "email": "hr@example.test"}],
            security_clearance_rows=[{"clearance": "Not Required", "position_sensitivity": "Low Risk"}],
            travel_requirement_rows=[{"travel_required": "Occasional travel", "travel_percentage": "25%"}],
            application_option_rows=[
                {"apply_online_url": "https://www.usajobs.gov/job/123456789", "accepts_uploaded_resumes": True}
            ],
        ),
    )

    assert conn.execute("SELECT agency_code FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "HSCB"
    assert conn.execute("SELECT COUNT(*) FROM job_locations WHERE job_id=?", (job_id,)).fetchone()[0] == 2
    location = conn.execute("SELECT latitude, longitude FROM job_locations WHERE job_id=? AND state='IL'", (job_id,)).fetchone()
    assert location["latitude"] == 41.8781
    assert location["longitude"] == -87.6298
    assert conn.execute("SELECT COUNT(*) FROM job_categories WHERE job_id=?", (job_id,)).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM job_hiring_paths WHERE job_id=?", (job_id,)).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM job_grades WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_salary_ranges WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_openings WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_contacts WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_security_clearances WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_travel_requirements WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_application_options WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    agency = conn.execute("SELECT * FROM agency_codes WHERE code='HSCB'").fetchone()
    assert agency["department_code"] == "HS"


def test_init_schema_backfills_search_coordinates_from_raw_json(conn, tmp_path):
    raw_path = tmp_path / "search.json"
    raw_path.write_text(
        json.dumps(
            {
                "SearchResult": {
                    "SearchResultItems": [
                        {
                            "MatchedObjectDescriptor": {
                                "PositionID": "FEMA-JD-1",
                                "PositionURI": "https://www.usajobs.gov/job/867603000",
                                "PositionLocation": [
                                    {
                                        "CityName": "Round Hill, Virginia",
                                        "CountryCode": "United States",
                                        "CountrySubDivisionCode": "Virginia",
                                        "Latitude": 39.135,
                                        "LocationName": "Round Hill, Virginia",
                                        "Longitude": -77.7689,
                                    }
                                ],
                                "UserArea": {"Details": {"RemoteIndicator": False, "TeleworkEligible": False}},
                            }
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    job_id = upsert_job(
        conn,
        _job(
            source="usajobs_search",
            position_id="FEMA-JD-1",
            announcement_number="FEMA-JD-1",
            usajobs_control_number="867603000",
            raw_json_path=str(raw_path),
            locations=[{"city": "Round Hill, Virginia", "state": "VA"}],
        ),
    )

    init_schema(conn)

    locations = conn.execute(
        "SELECT city, state, latitude, longitude FROM job_locations WHERE job_id=?",
        (job_id,),
    ).fetchall()
    assert len(locations) == 1
    assert locations[0]["state"] == "VA"
    assert locations[0]["latitude"] == 39.135
    assert locations[0]["longitude"] == -77.7689


def test_upsert_job_can_dedupe_by_control_number_when_ids_are_missing(conn):
    job_id = upsert_job(conn, _job(position_id=None, announcement_number=None))
    same_id = upsert_job(
        conn,
        _job(
            position_id=None,
            announcement_number=None,
            title="Updated from AnnouncementText",
        ),
    )

    assert same_id == job_id
    assert get_job(conn, job_id)["title"] == "Updated from AnnouncementText"


def test_upsert_job_requires_source(conn):
    with pytest.raises(ValueError, match="source"):
        upsert_job(conn, {"title": "Missing source"})


def test_upsert_job_text_preserves_summary_and_qualification_language(conn):
    job_id = upsert_job(conn, _job())
    upsert_job_text(
        conn,
        job_id,
        {
            "summary": "This is the top-of-announcement description.",
            "duties": "Lead mitigation planning work.",
            "qualifications": (
                "Applicants must have one year of specialized experience "
                "equivalent to the GS-12 level for this GS-13 position."
            ),
            "specialized_experience": "One year equivalent to GS-12.",
            "education": "No substitution of education for this grade.",
            "raw_json_path": "data/raw/usajobs_announcement_text/sample.json",
            "required_document_rows": [{"code": "resume", "label": "Resume", "required": True}],
            "requirement_rows": [
                {
                    "requirement_type": "condition",
                    "description": "Must be a U.S. citizen.",
                    "source_field": "conditions_of_employment",
                }
            ],
            "qualification_requirement_rows": [
                {
                    "grade": "13",
                    "requirement_type": "specialized_experience",
                    "text": "One year specialized experience equivalent to GS-12.",
                }
            ],
            "duty_rows": [{"text": "Lead mitigation planning work."}],
            "evaluation_factor_rows": [{"text": "Technical expertise."}],
        },
    )

    row = get_job_text(conn, job_id)
    assert row is not None
    assert row["summary"].startswith("This is the top")
    assert "GS-12" in row["qualifications"]
    assert "GS-13" in row["qualifications"]
    assert "Lead mitigation" in row["raw_text"]
    assert "One year equivalent" in row["raw_text"]
    assert (
        conn.execute("SELECT code FROM job_required_documents WHERE job_id=?", (job_id,)).fetchone()[0]
        == "resume"
    )
    assert conn.execute("SELECT COUNT(*) FROM job_requirements WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM job_qualification_requirements WHERE job_id=?", (job_id,)
    ).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_duties WHERE job_id=?", (job_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_evaluation_factors WHERE job_id=?", (job_id,)).fetchone()[0] == 1


def test_create_job_import_scope_projects_structured_filters(conn):
    scope_id = create_job_import_scope(
        conn,
        name="FEMA historic",
        source="usajobs_historic",
        endpoint="/api/historicjoa",
        download_mode="SAMPLE_ONLY",
        query_params={
            "HiringAgencyCodes": "HSCB",
            "HiringDepartmentCodes": "HS",
            "PositionSeries": "0089",
            "StartPositionOpenDate": "2026-01-01",
            "EndPositionOpenDate": "2026-01-31",
        },
    )

    row = conn.execute("SELECT * FROM job_import_scopes WHERE id=?", (scope_id,)).fetchone()
    assert row["agency_codes"] == "HSCB"
    assert row["department_codes"] == "HS"
    assert row["series"] == "0089"
    assert json.loads(row["query_params_json"])["HiringAgencyCodes"] == "HSCB"


def test_raw_api_response_logging(conn):
    response_id = record_raw_response(
        conn,
        source="usajobs_historic",
        endpoint="/api/historicjoa",
        query_params={"StartPositionOpenDate": "2026-01-01"},
        response_path="data/raw/usajobs_historic/page_1.json",
        status_code=200,
        record_count=500,
        page_number=1,
    )

    row = conn.execute("SELECT * FROM raw_api_responses WHERE id=?", (response_id,)).fetchone()
    assert row["status_code"] == 200
    assert json.loads(row["query_params_json"])["StartPositionOpenDate"] == "2026-01-01"


def test_manifest_lifecycle(conn):
    manifest_id = start_manifest(
        conn,
        source="usajobs_historic",
        endpoint="/api/historicjoa",
        download_mode="FULL_DOWNLOAD",
        filters={"year": 2026},
        estimated_records=84000,
        pages_requested=168,
    )
    update_manifest(conn, manifest_id, pages_completed=7, actual_records=3500)
    complete_manifest(conn, manifest_id, actual_records=3500, notes="Stopped test batch.")

    row = conn.execute("SELECT * FROM import_manifests WHERE id=?", (manifest_id,)).fetchone()
    assert row["status"] == "completed"
    assert row["pages_completed"] == 7
    assert row["actual_records"] == 3500
    assert json.loads(row["filters_json"]) == {"year": 2026}


def test_manifest_rejects_unknown_update_columns(conn):
    manifest_id = start_manifest(
        conn,
        source="usajobs_historic",
        endpoint="/api/historicjoa",
        download_mode="FULL_DOWNLOAD",
    )
    with pytest.raises(ValueError, match="Unsupported"):
        update_manifest(conn, manifest_id, made_up_column=True)


def test_saved_job_notes_tags_and_match_scores(conn):
    job_id = upsert_job(conn, _job())
    save_job(conn, job_id, status="Interested", priority=2)
    note_id = add_job_note(conn, job_id, "Looks like a strong mitigation fit.")
    add_job_tag(conn, job_id, "FEMA-Region-5")
    add_job_tag(conn, job_id, "fema-region-5")
    score_id = record_match_score(
        conn,
        job_id=job_id,
        score=91,
        scoring_version="v1.0",
        explanation="Strong FEMA and GS-13 match.",
        positive_factors=[{"factor": "agency", "weight": 20, "evidence": "FEMA"}],
        missing_info=[{"field": "announcement text"}],
    )

    saved = conn.execute("SELECT * FROM saved_jobs WHERE job_id=?", (job_id,)).fetchone()
    notes = conn.execute("SELECT * FROM job_notes WHERE id=?", (note_id,)).fetchone()
    tags = conn.execute("SELECT tag FROM job_tags WHERE job_id=?", (job_id,)).fetchall()
    score = conn.execute("SELECT * FROM match_scores WHERE id=?", (score_id,)).fetchone()

    assert saved["status"] == "Interested"
    assert notes["note"].startswith("Looks like")
    assert [row["tag"] for row in tags] == ["fema-region-5"]
    assert score["score"] == 91
    assert json.loads(score["positive_factors_json"])[0]["factor"] == "agency"

    remove_job_tag(conn, job_id, "fema-region-5")
    assert conn.execute("SELECT COUNT(*) FROM job_tags").fetchone()[0] == 0


def test_feedback_and_recommendation_tables(conn):
    job_id = upsert_job(conn, _job())
    feedback_id = record_job_feedback(
        conn,
        job_id=job_id,
        feedback_type="more_like_this",
        explanation="Strong FEMA mitigation fit.",
    )
    run_id = create_recommendation_run(
        conn,
        run_type="similar_jobs",
        seed_job_id=job_id,
        params={"limit": 5},
    )
    recommendation_id = record_job_recommendation(
        conn,
        run_id=run_id,
        job_id=job_id,
        score=88,
        explanation="Same agency and series.",
        factors=[{"factor": "same agency code", "weight": 20, "evidence": "HSCB"}],
    )

    feedback = conn.execute("SELECT * FROM job_feedback WHERE id=?", (feedback_id,)).fetchone()
    recommendation = conn.execute(
        "SELECT * FROM job_recommendations WHERE id=?",
        (recommendation_id,),
    ).fetchone()

    assert feedback["feedback_type"] == "more_like_this"
    assert recommendation["score"] == 88
    assert json.loads(recommendation["factors_json"])[0]["factor"] == "same agency code"

    with pytest.raises(ValueError, match="Unsupported"):
        record_job_feedback(conn, job_id=job_id, feedback_type="maybe", explanation="")


def test_application_tracker_tables(conn):
    job_id = upsert_job(conn, _job())
    application_id = upsert_application(
        conn,
        job_id=job_id,
        application_status="Submitted",
        resume_version="fema-gs13-v2",
        usajobs_application_id="APP-123",
        submitted_at="2026-05-06",
        next_action="Check referral status",
        next_action_due="2026-05-20",
        notes="Submitted with mitigation resume.",
    )
    same_id = upsert_application(
        conn,
        job_id=job_id,
        application_status="Referred",
        resume_version="fema-gs13-v2",
        usajobs_application_id="APP-123",
        submitted_at="2026-05-06",
        referred_at="2026-05-12",
    )
    event_id = add_application_event(
        conn,
        application_id=application_id,
        event_type="Referred",
        event_date="2026-05-12",
        notes="Best qualified referral.",
    )

    assert same_id == application_id
    app = conn.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
    event = conn.execute("SELECT * FROM application_events WHERE id=?", (event_id,)).fetchone()
    assert app["application_status"] == "Referred"
    assert app["referred_at"] == "2026-05-12"
    assert event["event_type"] == "Referred"
    assert event["notes"] == "Best qualified referral."


def test_resume_version_manager_table(conn):
    version_id = upsert_resume_version(
        conn,
        label="fema-gs13-v1",
        file_name="Caleb_FEMA_GS13_v1.pdf",
        file_path="C:/Users/caleb/resumes/Caleb_FEMA_GS13_v1.pdf",
        version_date="2026-05-06",
        target_series="0089",
        target_grade="GS-13",
        notes="Mitigation-heavy version.",
    )
    same_id = upsert_resume_version(
        conn,
        label="fema-gs13-v1",
        file_name="Caleb_FEMA_GS13_v1b.pdf",
        active=False,
    )

    row = conn.execute("SELECT * FROM resume_versions WHERE id=?", (version_id,)).fetchone()
    assert same_id == version_id
    assert row["file_name"] == "Caleb_FEMA_GS13_v1b.pdf"
    assert row["active"] == 0

    with pytest.raises(ValueError, match="label"):
        upsert_resume_version(conn, label="")


def test_child_rows_cascade_when_job_is_deleted(conn):
    job_id = upsert_job(
        conn,
        _job(
            locations=[{"city": "Chicago", "state": "IL"}],
            categories=[{"series": "0089"}],
            hiring_path_rows=[{"code": "public"}],
            grade_rows=[{"pay_plan": "GS", "grade_low": "13", "grade_high": "13"}],
            salary_range_rows=[{"minimum": 100000, "maximum": 150000}],
            opening_rows=[{"openings": 1}],
            contact_rows=[{"email": "hr@example.test"}],
            security_clearance_rows=[{"clearance": "Other"}],
            travel_requirement_rows=[{"travel_required": "Occasional"}],
            application_option_rows=[{"apply_online_url": "https://www.usajobs.gov/job/123"}],
        ),
    )
    upsert_job_text(
        conn,
        job_id,
        {
            "summary": "A job.",
            "requirement_rows": [{"description": "Must be a U.S. citizen."}],
            "qualification_requirement_rows": [{"text": "Equivalent to GS-12."}],
            "duty_rows": [{"text": "Coordinate planning."}],
            "evaluation_factor_rows": [{"text": "Technical expertise."}],
        },
    )
    save_job(conn, job_id)
    add_job_note(conn, job_id, "Note")
    add_job_tag(conn, job_id, "tag")
    conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM job_text").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_locations").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_categories").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_hiring_paths").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_grades").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_salary_ranges").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_requirements").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_qualification_requirements").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_duties").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_evaluation_factors").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_openings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_contacts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_security_clearances").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_travel_requirements").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_application_options").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_feedback").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM recommendation_runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_recommendations").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM repost_group_members").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM application_events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM saved_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_notes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM job_tags").fetchone()[0] == 0
