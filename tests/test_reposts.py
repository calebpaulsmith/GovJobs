from __future__ import annotations

import json
import sqlite3

import pytest

from src.alerts import generate_alerts
from src.database import connect, init_schema, upsert_job, upsert_job_text
from src.reposts import detect_reposts
from src.ui_data import repost_group_members_dataframe, repost_groups_dataframe, run_repost_detection


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "reposts.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _job(**overrides):
    base = {
        "source": "usajobs_historic",
        "title": "Emergency Management Specialist",
        "agency": "Federal Emergency Management Agency",
        "agency_code": "HSCB",
        "series": "0089",
        "grade_high": "13",
        "open_date": "2026-01-01",
        "close_date": "2026-01-15",
        "remote_status": "hybrid",
    }
    base.update(overrides)
    return base


def test_detect_reposts_persists_groups_members_and_evidence(conn):
    original_id = upsert_job(
        conn,
        _job(
            usajobs_control_number="100",
            position_id="FEMA-100",
            announcement_number="FEMA-100",
            open_date="2026-01-01",
        ),
    )
    repost_id = upsert_job(
        conn,
        _job(
            usajobs_control_number="101",
            position_id="FEMA-101",
            announcement_number="FEMA-101",
            title="Emergency Management Specialist",
            open_date="2026-02-01",
        ),
    )
    upsert_job(
        conn,
        _job(
            usajobs_control_number="200",
            position_id="OTHER-200",
            announcement_number="OTHER-200",
            title="Accountant",
            agency="Other Agency",
            agency_code="OTHR",
            series="0510",
        ),
    )
    shared_text = {
        "summary": "Leads emergency management and disaster recovery planning for a regional office.",
        "qualifications": "One year specialized experience coordinating emergency management programs.",
    }
    upsert_job_text(conn, original_id, shared_text)
    upsert_job_text(conn, repost_id, shared_text)

    result = detect_reposts(conn)

    assert result.groups_created == 1
    assert result.members_created == 2
    group = conn.execute("SELECT * FROM repost_groups").fetchone()
    assert group["member_count"] == 2
    evidence = json.loads(group["evidence_json"])
    assert set(evidence["member_job_ids"]) == {original_id, repost_id}


def test_repost_ui_helpers_and_alerts_use_latest_detector_run(conn):
    first_id = upsert_job(
        conn,
        _job(usajobs_control_number="300", position_id="FEMA-300", announcement_number="FEMA-300"),
    )
    second_id = upsert_job(
        conn,
        _job(usajobs_control_number="301", position_id="FEMA-301", announcement_number="FEMA-301"),
    )

    groups_created = run_repost_detection(conn)
    groups = repost_groups_dataframe(conn)
    members = repost_group_members_dataframe(conn, int(groups.iloc[0]["group_id"]))

    assert groups_created == 1
    assert len(groups) == 1
    assert set(members["job_id"]) == {first_id, second_id}

    created = generate_alerts(conn)
    alert = conn.execute("SELECT * FROM alerts WHERE alert_type='reposted'").fetchone()
    assert created >= 1
    assert alert is not None
    assert json.loads(alert["details_json"])["member_count"] == 2
