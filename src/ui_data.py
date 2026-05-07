"""Read/write helpers for Streamlit pages."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from config import load_config
from src.database import (
    add_job_note,
    add_job_tag,
    add_application_event,
    connect,
    dismiss_job_recommendation,
    init_schema,
    record_job_feedback,
    save_job,
    set_resume_version_active,
    upsert_application,
    upsert_resume_version,
)
from src.alerts import dismiss_alert, generate_alerts
from src.recommendations import generate_similar_jobs
from src.reposts import detect_reposts
from src.scoring import score_all_jobs


JOB_DISPLAY_COLUMNS = [
    "jobs.id AS id",
    "jobs.source AS source",
    "jobs.title AS title",
    "jobs.agency AS agency",
    "jobs.agency_code AS agency_code",
    "jobs.department_code AS department_code",
    "jobs.series AS series",
    "jobs.grade_low AS grade_low",
    "jobs.grade_high AS grade_high",
    "jobs.state AS state",
    "jobs.city AS city",
    "jobs.remote_status AS remote_status",
    "jobs.salary_min AS salary_min",
    "jobs.salary_max AS salary_max",
    "jobs.open_date AS open_date",
    "jobs.close_date AS close_date",
    "latest_score.score AS score",
    "jobs.url AS url",
]

STATE_CENTERS = {
    "AL": (32.8067, -86.7911),
    "AK": (61.3707, -152.4044),
    "AZ": (33.7298, -111.4312),
    "AR": (34.9697, -92.3731),
    "CA": (36.1162, -119.6816),
    "CO": (39.0598, -105.3111),
    "CT": (41.5978, -72.7554),
    "DC": (38.9072, -77.0369),
    "DE": (39.3185, -75.5071),
    "FL": (27.7663, -81.6868),
    "GA": (33.0406, -83.6431),
    "HI": (21.0943, -157.4983),
    "IA": (42.0115, -93.2105),
    "ID": (44.2405, -114.4788),
    "IL": (40.3495, -88.9861),
    "IN": (39.8494, -86.2583),
    "KS": (38.5266, -96.7265),
    "KY": (37.6681, -84.6701),
    "LA": (31.1695, -91.8678),
    "MA": (42.2302, -71.5301),
    "MD": (39.0639, -76.8021),
    "ME": (44.6939, -69.3819),
    "MI": (43.3266, -84.5361),
    "MN": (45.6945, -93.9002),
    "MO": (38.4561, -92.2884),
    "MS": (32.7416, -89.6787),
    "MT": (46.9219, -110.4544),
    "NC": (35.6301, -79.8064),
    "ND": (47.5289, -99.7840),
    "NE": (41.1254, -98.2681),
    "NH": (43.4525, -71.5639),
    "NJ": (40.2989, -74.5210),
    "NM": (34.8405, -106.2485),
    "NV": (38.3135, -117.0554),
    "NY": (42.1657, -74.9481),
    "OH": (40.3888, -82.7649),
    "OK": (35.5653, -96.9289),
    "OR": (44.5720, -122.0709),
    "PA": (40.5908, -77.2098),
    "PR": (18.2208, -66.5901),
    "RI": (41.6809, -71.5118),
    "SC": (33.8569, -80.9450),
    "SD": (44.2998, -99.4388),
    "TN": (35.7478, -86.6923),
    "TX": (31.0545, -97.5635),
    "UT": (40.1500, -111.8624),
    "VA": (37.7693, -78.1700),
    "VT": (44.0459, -72.7107),
    "WA": (47.4009, -121.4905),
    "WI": (44.2685, -89.6165),
    "WV": (38.4912, -80.9545),
    "WY": (42.7560, -107.3025),
}


def app_connection() -> sqlite3.Connection:
    cfg = load_config()
    conn = connect(cfg.database_path)
    init_schema(conn)
    return conn


def database_status(conn: sqlite3.Connection) -> dict[str, Any]:
    cfg = load_config()
    raw_root = cfg.raw_data_path
    raw_bytes = _folder_size(raw_root)
    db_bytes = cfg.database_path.stat().st_size if cfg.database_path.exists() else 0
    return {
        "database_path": str(cfg.database_path),
        "database_exists": cfg.database_path.exists(),
        "database_mb": round(db_bytes / 1_000_000, 2),
        "raw_path": str(raw_root),
        "raw_mb": round(raw_bytes / 1_000_000, 2),
        "jobs": _count(conn, "jobs"),
        "current_jobs": _scalar(
            conn, "SELECT COUNT(*) FROM jobs WHERE source='usajobs_search'"
        ),
        "historic_jobs": _scalar(
            conn, "SELECT COUNT(*) FROM jobs WHERE source='usajobs_historic'"
        ),
        "job_text": _count(conn, "job_text"),
        "job_locations": _count(conn, "job_locations"),
        "job_categories": _count(conn, "job_categories"),
        "job_hiring_paths": _count(conn, "job_hiring_paths"),
        "job_required_documents": _count(conn, "job_required_documents"),
        "job_import_scopes": _count(conn, "job_import_scopes"),
        "job_grades": _count(conn, "job_grades"),
        "job_salary_ranges": _count(conn, "job_salary_ranges"),
        "job_requirements": _count(conn, "job_requirements"),
        "job_qualification_requirements": _count(conn, "job_qualification_requirements"),
        "job_duties": _count(conn, "job_duties"),
        "job_evaluation_factors": _count(conn, "job_evaluation_factors"),
        "job_openings": _count(conn, "job_openings"),
        "job_contacts": _count(conn, "job_contacts"),
        "job_security_clearances": _count(conn, "job_security_clearances"),
        "job_travel_requirements": _count(conn, "job_travel_requirements"),
        "job_application_options": _count(conn, "job_application_options"),
        "saved_jobs": _count(conn, "saved_jobs"),
        "applications": _count(conn, "applications"),
        "application_events": _count(conn, "application_events"),
        "resume_versions": _count(conn, "resume_versions"),
        "job_feedback": _count(conn, "job_feedback"),
        "recommendation_runs": _count(conn, "recommendation_runs"),
        "job_recommendations": _count(conn, "job_recommendations"),
        "repost_runs": _count(conn, "repost_runs"),
        "repost_groups": _count(conn, "repost_groups"),
        "repost_group_members": _count(conn, "repost_group_members"),
        "alerts": _count(conn, "alerts"),
        "open_alerts": _scalar(conn, "SELECT COUNT(*) FROM alerts WHERE status != 'dismissed'"),
        "opm_records": _count(conn, "opm_workforce_records"),
        "last_import": _scalar(conn, "SELECT MAX(completed_at) FROM import_manifests"),
        "last_api_request": _scalar(conn, "SELECT MAX(request_time) FROM raw_api_responses"),
        "last_alert_run": _scalar(conn, "SELECT MAX(completed_at) FROM alert_runs"),
        "last_repost_run": _scalar(conn, "SELECT MAX(completed_at) FROM repost_runs"),
    }


def jobs_dataframe(conn: sqlite3.Connection, filters: dict[str, Any] | None = None) -> pd.DataFrame:
    filters = filters or {}
    where: list[str] = []
    params: list[Any] = []

    if filters.get("source") and filters["source"] != "All":
        where.append("jobs.source = ?")
        params.append(filters["source"])
    if filters.get("agency"):
        where.append("jobs.agency LIKE ?")
        params.append(f"%{filters['agency']}%")
    if filters.get("agency_code"):
        where.append("jobs.agency_code = ?")
        params.append(str(filters["agency_code"]).upper())
    if filters.get("department_code"):
        where.append("jobs.department_code = ?")
        params.append(str(filters["department_code"]).upper())
    if filters.get("series"):
        where.append("jobs.series = ?")
        params.append(str(filters["series"]).zfill(4))
    if filters.get("pay_plan"):
        where.append(
            """
            EXISTS (
                SELECT 1 FROM job_grades g
                WHERE g.job_id = jobs.id AND g.pay_plan = ?
            )
            """
        )
        params.append(str(filters["pay_plan"]).upper())
    grade_low = _int_filter(filters.get("grade_low"))
    if grade_low is not None:
        where.append(
            """
            EXISTS (
                SELECT 1 FROM job_grades g
                WHERE g.job_id = jobs.id
                  AND CAST(COALESCE(g.grade_high, g.grade_low, '0') AS INTEGER) >= ?
            )
            """
        )
        params.append(grade_low)
    grade_high = _int_filter(filters.get("grade_high"))
    if grade_high is not None:
        where.append(
            """
            EXISTS (
                SELECT 1 FROM job_grades g
                WHERE g.job_id = jobs.id
                  AND CAST(COALESCE(g.grade_low, g.grade_high, '99') AS INTEGER) <= ?
            )
            """
        )
        params.append(grade_high)
    salary_min = _float_filter(filters.get("salary_min"))
    if salary_min is not None:
        where.append(
            """
            EXISTS (
                SELECT 1 FROM job_salary_ranges s
                WHERE s.job_id = jobs.id AND COALESCE(s.maximum, s.minimum, 0) >= ?
            )
            """
        )
        params.append(salary_min)
    salary_max = _float_filter(filters.get("salary_max"))
    if salary_max is not None:
        where.append(
            """
            EXISTS (
                SELECT 1 FROM job_salary_ranges s
                WHERE s.job_id = jobs.id AND COALESCE(s.minimum, s.maximum, 999999999) <= ?
            )
            """
        )
        params.append(salary_max)
    if filters.get("hiring_path"):
        where.append(
            """
            EXISTS (
                SELECT 1 FROM job_hiring_paths hp
                WHERE hp.job_id = jobs.id
                  AND (hp.code LIKE ? OR hp.label LIKE ?)
            )
            """
        )
        like = f"%{filters['hiring_path']}%"
        params.extend([like, like])
    if filters.get("state") and filters["state"] != "All":
        where.append("jobs.state = ?")
        params.append(filters["state"])
    if filters.get("remote_status") and filters["remote_status"] != "All":
        where.append("jobs.remote_status = ?")
        params.append(filters["remote_status"])
    if filters.get("keyword"):
        where.append(
            """
            (
                jobs.title LIKE ? OR jobs.agency LIKE ? OR jobs.department LIKE ?
                OR EXISTS (
                    SELECT 1 FROM job_requirements r
                    WHERE r.job_id = jobs.id AND r.description LIKE ?
                )
                OR EXISTS (
                    SELECT 1 FROM job_qualification_requirements q
                    WHERE q.job_id = jobs.id AND q.text LIKE ?
                )
                OR EXISTS (
                    SELECT 1 FROM job_duties d
                    WHERE d.job_id = jobs.id AND d.duty_text LIKE ?
                )
            )
            """
        )
        like = f"%{filters['keyword']}%"
        params.extend([like, like, like, like, like, like])

    sql = f"""
        SELECT {', '.join(JOB_DISPLAY_COLUMNS)}
        FROM jobs
        LEFT JOIN (
            SELECT ms.job_id, ms.score
            FROM match_scores ms
            JOIN (
                SELECT job_id, MAX(id) AS latest_score_id
                FROM match_scores
                GROUP BY job_id
            ) latest ON latest.latest_score_id = ms.id
        ) latest_score ON latest_score.job_id = jobs.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY jobs.close_date IS NULL, jobs.close_date ASC, jobs.updated_at DESC LIMIT 1000"
    return pd.read_sql_query(sql, conn, params=params)


def job_detail(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT j.*, jt.summary, jt.duties, jt.qualifications, jt.specialized_experience,
               jt.education, jt.required_documents, jt.how_to_apply, jt.evaluation_criteria,
               jt.conditions_of_employment, ms.score, ms.explanation AS score_explanation,
               ms.positive_factors_json, ms.negative_factors_json, ms.missing_info_json,
               ms.scoring_version
        FROM jobs j
        LEFT JOIN job_text jt ON jt.job_id = j.id
        LEFT JOIN (
            SELECT ms1.*
            FROM match_scores ms1
            JOIN (
                SELECT job_id, MAX(id) AS latest_score_id
                FROM match_scores
                GROUP BY job_id
            ) latest ON latest.latest_score_id = ms1.id
        ) ms ON ms.job_id = j.id
        WHERE j.id = ?
        """,
        (job_id,),
    ).fetchone()
    return dict(row) if row else None


def save_job_workflow(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    status: str,
    priority: int | None,
    note: str | None = None,
    tag: str | None = None,
) -> None:
    save_job(conn, job_id, status=status, priority=priority)
    if note:
        add_job_note(conn, job_id, note)
    if tag:
        add_job_tag(conn, job_id, tag)


def saved_jobs_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT j.id, sj.status, sj.priority, sj.saved_at, j.title, j.agency, j.series,
               j.grade_low, j.grade_high, j.state, j.remote_status, j.close_date, j.url
        FROM saved_jobs sj
        JOIN jobs j ON j.id = sj.job_id
        ORDER BY sj.saved_at DESC
        """,
        conn,
    )


def applications_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT a.id AS application_id, a.job_id, a.application_status,
               a.resume_version, a.usajobs_application_id, a.application_url, a.submitted_at,
               a.referred_at, a.interview_at, a.outcome, a.next_action,
               a.next_action_due, a.contact_name, a.contact_email, a.notes,
               j.title, j.agency, j.agency_code, j.series, j.grade_high,
               j.close_date, j.url
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        ORDER BY
            a.next_action_due IS NULL,
            a.next_action_due ASC,
            a.updated_at DESC
        """,
        conn,
    )


def resume_versions_dataframe(conn: sqlite3.Connection, *, active_only: bool = False) -> pd.DataFrame:
    where = "WHERE active = 1" if active_only else ""
    return pd.read_sql_query(
        f"""
        SELECT id, label, file_name, file_path, version_date, target_series,
               target_grade, notes, active, created_at, updated_at
        FROM resume_versions
        {where}
        ORDER BY active DESC, version_date DESC, updated_at DESC, label
        """,
        conn,
    )


def application_events_dataframe(conn: sqlite3.Connection, application_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT id, event_type, event_date, notes, created_at
        FROM application_events
        WHERE application_id=?
        ORDER BY COALESCE(event_date, created_at) DESC, id DESC
        """,
        conn,
        params=[application_id],
    )


def upsert_application_workflow(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    application_status: str,
    resume_version: str | None = None,
    usajobs_application_id: str | None = None,
    application_url: str | None = None,
    submitted_at: str | None = None,
    referred_at: str | None = None,
    interview_at: str | None = None,
    outcome: str | None = None,
    next_action: str | None = None,
    next_action_due: str | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    notes: str | None = None,
    event_note: str | None = None,
) -> int:
    application_id = upsert_application(
        conn,
        job_id=job_id,
        application_status=application_status,
        resume_version=resume_version,
        usajobs_application_id=usajobs_application_id,
        application_url=application_url,
        submitted_at=submitted_at,
        referred_at=referred_at,
        interview_at=interview_at,
        outcome=outcome,
        next_action=next_action,
        next_action_due=next_action_due,
        contact_name=contact_name,
        contact_email=contact_email,
        notes=notes,
    )
    if application_status == "Submitted":
        save_job(conn, job_id, status="Applied")
    elif application_status in {"Referred", "Interview", "Selected", "Not selected"}:
        save_job(conn, job_id, status=application_status)
    if event_note:
        add_application_event(
            conn,
            application_id=application_id,
            event_type=application_status,
            event_date=submitted_at or referred_at or interview_at,
            notes=event_note,
        )
    return application_id


def add_application_event_workflow(
    conn: sqlite3.Connection,
    *,
    application_id: int,
    event_type: str,
    event_date: str | None = None,
    notes: str | None = None,
) -> int:
    return add_application_event(
        conn,
        application_id=application_id,
        event_type=event_type,
        event_date=event_date,
        notes=notes,
    )


def upsert_resume_version_workflow(
    conn: sqlite3.Connection,
    *,
    label: str,
    file_name: str | None = None,
    file_path: str | None = None,
    version_date: str | None = None,
    target_series: str | None = None,
    target_grade: str | None = None,
    notes: str | None = None,
    active: bool = True,
) -> int:
    return upsert_resume_version(
        conn,
        label=label,
        file_name=file_name,
        file_path=file_path,
        version_date=version_date,
        target_series=target_series,
        target_grade=target_grade,
        notes=notes,
        active=active,
    )


def set_resume_version_active_workflow(
    conn: sqlite3.Connection,
    resume_version_id: int,
    active: bool,
) -> None:
    set_resume_version_active(conn, resume_version_id, active)


def notes_dataframe(conn: sqlite3.Connection, job_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT note, created_at FROM job_notes WHERE job_id=? ORDER BY created_at DESC",
        conn,
        params=[job_id],
    )


def tags_for_job(conn: sqlite3.Connection, job_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT tag FROM job_tags WHERE job_id=? ORDER BY tag",
        (job_id,),
    ).fetchall()
    return [row["tag"] for row in rows]


def record_feedback_workflow(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    feedback_type: str,
    explanation: str | None = None,
) -> int:
    return record_job_feedback(
        conn,
        job_id=job_id,
        feedback_type=feedback_type,
        explanation=explanation,
    )


def feedback_dataframe(conn: sqlite3.Connection, job_id: int | None = None) -> pd.DataFrame:
    where = ""
    params: list[Any] = []
    if job_id is not None:
        where = "WHERE jf.job_id = ?"
        params.append(job_id)
    return pd.read_sql_query(
        f"""
        SELECT jf.id, jf.job_id, j.title, j.agency, jf.feedback_type,
               jf.explanation, jf.created_at
        FROM job_feedback jf
        JOIN jobs j ON j.id = jf.job_id
        {where}
        ORDER BY jf.created_at DESC, jf.id DESC
        LIMIT 100
        """,
        conn,
        params=params,
    )


def run_similar_jobs(
    conn: sqlite3.Connection,
    *,
    seed_job_id: int | None = None,
    limit: int = 25,
) -> int:
    result = generate_similar_jobs(conn, seed_job_id=seed_job_id, limit=limit)
    return result.run_id


def recommendations_dataframe(
    conn: sqlite3.Connection,
    *,
    run_id: int | None = None,
    include_dismissed: bool = False,
) -> pd.DataFrame:
    where: list[str] = []
    params: list[Any] = []
    if run_id is not None:
        where.append("jr.run_id = ?")
        params.append(run_id)
    if not include_dismissed:
        where.append("jr.dismissed = 0")
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    return pd.read_sql_query(
        f"""
        SELECT jr.id AS recommendation_id, jr.run_id, rr.seed_job_id,
               jr.job_id, j.title, j.agency, j.agency_code, j.series,
               j.grade_high, j.state, j.remote_status, latest_score.score AS match_score,
               jr.score AS recommendation_score, jr.explanation,
               jr.factors_json, jr.dismissed, jr.created_at, j.url
        FROM job_recommendations jr
        JOIN recommendation_runs rr ON rr.id = jr.run_id
        JOIN jobs j ON j.id = jr.job_id
        LEFT JOIN (
            SELECT ms.job_id, ms.score
            FROM match_scores ms
            JOIN (
                SELECT job_id, MAX(id) AS latest_score_id
                FROM match_scores
                GROUP BY job_id
            ) latest ON latest.latest_score_id = ms.id
        ) latest_score ON latest_score.job_id = j.id
        {where_clause}
        ORDER BY jr.run_id DESC, jr.score DESC, latest_score.score DESC, jr.id
        LIMIT 200
        """,
        conn,
        params=params,
    )


def dismiss_recommendation_workflow(conn: sqlite3.Connection, recommendation_id: int) -> None:
    dismiss_job_recommendation(conn, recommendation_id)


def run_repost_detection(conn: sqlite3.Connection) -> int:
    result = detect_reposts(conn)
    return result.groups_created


def repost_groups_dataframe(conn: sqlite3.Connection, *, latest_only: bool = True) -> pd.DataFrame:
    where = ""
    params: list[Any] = []
    if latest_only:
        where = "WHERE rg.run_id = (SELECT MAX(id) FROM repost_runs WHERE completed_at IS NOT NULL)"
    return pd.read_sql_query(
        f"""
        SELECT rg.id AS group_id, rg.run_id, rg.group_title, rg.agency_key,
               rg.series_key, rg.member_count, rg.confidence_score,
               rg.group_signature, rg.evidence_json, rg.created_at
        FROM repost_groups rg
        {where}
        ORDER BY rg.confidence_score DESC, rg.member_count DESC, rg.group_title
        """,
        conn,
        params=params,
    )


def repost_group_members_dataframe(conn: sqlite3.Connection, group_id: int | None = None) -> pd.DataFrame:
    where = ""
    params: list[Any] = []
    if group_id is not None:
        where = "WHERE rgm.group_id = ?"
        params.append(group_id)
    return pd.read_sql_query(
        f"""
        SELECT rgm.group_id, rgm.job_id, rgm.role, rgm.title_similarity,
               rgm.text_hash, j.title, j.agency, j.agency_code, j.series,
               j.open_date, j.close_date, j.usajobs_control_number,
               j.announcement_number, j.position_id, j.url
        FROM repost_group_members rgm
        JOIN jobs j ON j.id = rgm.job_id
        {where}
        ORDER BY rgm.group_id, rgm.role, j.open_date, j.id
        """,
        conn,
        params=params,
    )


def trend_dataframe(conn: sqlite3.Connection, grain: str = "month") -> pd.DataFrame:
    date_expr = "substr(open_date, 1, 7)" if grain == "month" else "open_date"
    return pd.read_sql_query(
        f"""
        SELECT {date_expr} AS period, COUNT(*) AS postings
        FROM jobs
        WHERE open_date IS NOT NULL
        GROUP BY period
        ORDER BY period
        """,
        conn,
    )


def grouped_counts(conn: sqlite3.Connection, column: str, limit: int = 20) -> pd.DataFrame:
    allowed = {"agency", "series", "state", "grade_high", "remote_status", "source"}
    if column not in allowed:
        raise ValueError(f"Unsupported group column: {column}")
    if column == "series" and _count(conn, "job_categories"):
        return pd.read_sql_query(
            """
            WITH series_rows AS (
                SELECT job_id, series FROM job_categories
                UNION ALL
                SELECT id AS job_id, series FROM jobs
                WHERE series IS NOT NULL
                  AND id NOT IN (SELECT job_id FROM job_categories)
            )
            SELECT COALESCE(series, 'Unknown') AS label, COUNT(DISTINCT job_id) AS postings
            FROM series_rows
            GROUP BY label
            ORDER BY postings DESC, label
            LIMIT ?
            """,
            conn,
            params=[limit],
        )
    return pd.read_sql_query(
        f"""
        SELECT COALESCE({column}, 'Unknown') AS label, COUNT(*) AS postings
        FROM jobs
        GROUP BY label
        ORDER BY postings DESC, label
        LIMIT ?
        """,
        conn,
        params=[limit],
    )


def state_counts(conn: sqlite3.Connection) -> pd.DataFrame:
    if _count(conn, "job_locations"):
        return pd.read_sql_query(
            """
            WITH location_rows AS (
                SELECT jl.job_id, jl.state, COALESCE(jl.remote_indicator, j.remote_status, 'unknown') AS remote_status
                FROM job_locations jl
                JOIN jobs j ON j.id = jl.job_id
                UNION ALL
                SELECT id AS job_id, state, remote_status
                FROM jobs
                WHERE state IS NOT NULL
                  AND id NOT IN (SELECT job_id FROM job_locations)
            )
            SELECT state, COUNT(DISTINCT job_id) AS postings
            FROM location_rows
            WHERE state IS NOT NULL
              AND length(state) = 2
              AND remote_status != 'remote'
            GROUP BY state
            ORDER BY postings DESC
            """,
            conn,
        )
    return pd.read_sql_query(
        """
        SELECT state, COUNT(*) AS postings
        FROM jobs
        WHERE state IS NOT NULL AND length(state) = 2 AND remote_status != 'remote'
        GROUP BY state
        ORDER BY postings DESC
        """,
        conn,
    )


def work_location_points(
    conn: sqlite3.Connection,
    *,
    include_multi_location: bool = True,
    source: str | None = None,
) -> pd.DataFrame:
    where = [
        "jl.latitude IS NOT NULL",
        "jl.longitude IS NOT NULL",
        "COALESCE(jl.remote_indicator, j.remote_status, 'unknown') != 'remote'",
    ]
    params: list[Any] = []
    if source and source != "All":
        where.append("j.source = ?")
        params.append(source)
    if not include_multi_location:
        where.append(
            """
            j.id IN (
                SELECT job_id
                FROM job_locations
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                GROUP BY job_id
                HAVING COUNT(*) = 1
            )
            """
        )
    return pd.read_sql_query(
        f"""
        WITH location_counts AS (
            SELECT job_id, COUNT(*) AS location_count
            FROM job_locations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            GROUP BY job_id
        ),
        named_locations AS (
            SELECT job_id, group_concat(location_label, ' | ') AS all_locations
            FROM (
                SELECT DISTINCT job_id,
                    COALESCE(
                        NULLIF(location_text, ''),
                        NULLIF(TRIM(COALESCE(city, '') || ', ' || COALESCE(state, '')), ', '),
                        NULLIF(state, ''),
                        NULLIF(country, '')
                    ) AS location_label
                FROM job_locations
            )
            WHERE location_label IS NOT NULL
            GROUP BY job_id
        )
        SELECT j.id AS job_id, j.title, j.agency, j.agency_code, j.series,
               j.grade_high, j.remote_status, j.close_date, j.url,
               jl.location_text, jl.city, jl.state, jl.country, jl.latitude,
               jl.longitude, lc.location_count, jt.summary, jt.qualifications,
               jt.specialized_experience, nl.all_locations,
               CASE WHEN lc.location_count > 1 THEN 1 ELSE 0 END AS is_multi_location
        FROM job_locations jl
        JOIN jobs j ON j.id = jl.job_id
        JOIN location_counts lc ON lc.job_id = jl.job_id
        LEFT JOIN named_locations nl ON nl.job_id = j.id
        LEFT JOIN job_text jt ON jt.job_id = j.id
        WHERE {' AND '.join(where)}
        ORDER BY j.close_date IS NULL, j.close_date ASC, j.title
        LIMIT 5000
        """,
        conn,
        params=params,
    )


def current_location_coverage(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS current_postings,
            COUNT(
                CASE WHEN COALESCE(j.remote_status, 'unknown') != 'remote'
                      AND EXISTS (
                    SELECT 1 FROM job_locations jl
                    WHERE jl.job_id = j.id
                      AND jl.latitude IS NOT NULL
                      AND jl.longitude IS NOT NULL
                ) THEN 1 END
            ) AS mapped_postings,
            COUNT(
                CASE WHEN COALESCE(j.remote_status, 'unknown') != 'remote'
                      AND NOT EXISTS (
                          SELECT 1 FROM job_locations jl
                          WHERE jl.job_id = j.id
                            AND jl.latitude IS NOT NULL
                            AND jl.longitude IS NOT NULL
                      )
                THEN 1 END
            ) AS unmapped_non_remote_postings,
            COUNT(CASE WHEN COALESCE(j.remote_status, 'unknown') = 'remote' THEN 1 END) AS remote_postings
        FROM jobs j
        WHERE j.source = 'usajobs_search'
        """
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def remote_anywhere_jobs(conn: sqlite3.Connection, limit: int = 500) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT id, title, agency, agency_code, series, grade_high, close_date, url
        FROM jobs
        WHERE remote_status = 'remote'
        ORDER BY close_date IS NULL, close_date ASC, updated_at DESC
        LIMIT ?
        """,
        conn,
        params=[limit],
    )


def non_mappable_current_postings(
    conn: sqlite3.Connection,
    *,
    bounds: dict[str, float] | None,
    limit: int = 500,
) -> pd.DataFrame:
    if not bounds:
        return pd.DataFrame()
    rows = pd.read_sql_query(
        """
        WITH named_locations AS (
            SELECT job_id, group_concat(location_label, ' | ') AS all_locations
            FROM (
                SELECT DISTINCT job_id,
                    COALESCE(
                        NULLIF(location_text, ''),
                        NULLIF(TRIM(COALESCE(city, '') || ', ' || COALESCE(state, '')), ', '),
                        NULLIF(state, ''),
                        NULLIF(country, '')
                    ) AS location_label
                FROM job_locations
            )
            WHERE location_label IS NOT NULL
            GROUP BY job_id
        )
        SELECT j.id, j.title, j.agency, j.agency_code, j.series, j.grade_high,
               j.state, j.city, j.location_text, nl.all_locations, j.close_date, j.url
        FROM jobs j
        LEFT JOIN named_locations nl ON nl.job_id = j.id
        WHERE j.source = 'usajobs_search'
          AND COALESCE(j.remote_status, 'unknown') != 'remote'
          AND NOT EXISTS (
              SELECT 1 FROM job_locations jl
              WHERE jl.job_id = j.id
                AND jl.latitude IS NOT NULL
                AND jl.longitude IS NOT NULL
          )
        ORDER BY j.close_date IS NULL, j.close_date ASC, j.updated_at DESC
        LIMIT ?
        """,
        conn,
        params=[limit],
    )
    if rows.empty:
        return rows
    visible_states = {
        state
        for state, (lat, lon) in STATE_CENTERS.items()
        if _bounds_contains(bounds, lat, lon)
    }
    if not visible_states:
        return rows.iloc[0:0]
    return rows[rows["state"].isin(visible_states)]


def multi_location_jobs(conn: sqlite3.Connection, limit: int = 500) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        WITH location_counts AS (
            SELECT job_id, COUNT(*) AS location_count,
                   group_concat(COALESCE(location_text, city || ', ' || state), ' | ') AS locations
            FROM job_locations
            WHERE COALESCE(remote_indicator, 'unknown') != 'remote'
            GROUP BY job_id
            HAVING COUNT(*) > 1
        )
        SELECT j.id, j.title, j.agency, j.agency_code, j.series, j.grade_high,
               j.close_date, lc.location_count, lc.locations, j.url
        FROM location_counts lc
        JOIN jobs j ON j.id = lc.job_id
        ORDER BY lc.location_count DESC, j.close_date IS NULL, j.close_date ASC
        LIMIT ?
        """,
        conn,
        params=[limit],
    )


def opm_state_counts(conn: sqlite3.Connection, metric: str = "employment") -> pd.DataFrame:
    metric_columns = {
        "employment": ("employment_count", "workforce_count"),
        "accessions": ("accessions_count", "accessions"),
        "separations": ("separations_count", "separations"),
    }
    if metric not in metric_columns:
        raise ValueError(f"Unsupported OPM metric: {metric}")
    column, label = metric_columns[metric]
    return pd.read_sql_query(
        f"""
        SELECT location_state AS state, SUM(COALESCE({column}, 0)) AS {label}
        FROM opm_workforce_records
        WHERE location_state IS NOT NULL AND length(location_state) = 2
        GROUP BY location_state
        HAVING {label} > 0
        ORDER BY {label} DESC
        """,
        conn,
    )


def opm_datasets_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT dataset, COUNT(*) AS records, MIN(period_year) AS first_year,
               MAX(period_year) AS latest_year,
               SUM(COALESCE(employment_count, 0)) AS workforce_count,
               SUM(COALESCE(accessions_count, 0)) AS accessions,
               SUM(COALESCE(separations_count, 0)) AS separations
        FROM opm_workforce_records
        GROUP BY dataset
        ORDER BY dataset
        """,
        conn,
    )


def remote_counts(conn: sqlite3.Connection) -> pd.DataFrame:
    return grouped_counts(conn, "remote_status", limit=10)


def salary_by_series(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT series, COUNT(*) AS postings, AVG(salary_min) AS salary_min_avg,
               AVG(salary_max) AS salary_max_avg
        FROM jobs
        WHERE series IS NOT NULL
        GROUP BY series
        HAVING postings >= 1
        ORDER BY postings DESC, series
        LIMIT 25
        """,
        conn,
    )


def manifests_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT id, source, endpoint, download_mode, status, actual_records,
               pages_completed, started_at, completed_at, notes
        FROM import_manifests
        ORDER BY id DESC
        LIMIT 50
        """,
        conn,
    )


def raw_responses_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT source, endpoint, status_code, record_count, page_number,
               request_time, response_path
        FROM raw_api_responses
        ORDER BY request_time DESC
        LIMIT 100
        """,
        conn,
    )


def run_alerts(conn: sqlite3.Connection) -> int:
    return generate_alerts(conn)


def alerts_dataframe(conn: sqlite3.Connection, *, include_dismissed: bool = False) -> pd.DataFrame:
    where = "" if include_dismissed else "WHERE a.status != 'dismissed'"
    return pd.read_sql_query(
        f"""
        SELECT a.id, a.alert_type, a.severity, a.title, a.message, a.status,
               a.created_at, a.dismissed_at, a.source_search_id,
               ss.name AS saved_search_name,
               j.id AS job_id, j.title AS job_title, j.agency, j.agency_code,
               j.series, j.grade_high, j.state, j.remote_status, j.close_date,
               latest_score.score,
               a.details_json
        FROM alerts a
        LEFT JOIN jobs j ON j.id = a.job_id
        LEFT JOIN saved_searches ss ON ss.id = a.source_search_id
        LEFT JOIN (
            SELECT ms.job_id, ms.score
            FROM match_scores ms
            JOIN (
                SELECT job_id, MAX(id) AS latest_score_id
                FROM match_scores
                GROUP BY job_id
            ) latest ON latest.latest_score_id = ms.id
        ) latest_score ON latest_score.job_id = j.id
        {where}
        ORDER BY
            CASE a.severity
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            a.created_at DESC
        LIMIT 500
        """,
        conn,
    )


def dismiss_alert_workflow(conn: sqlite3.Connection, alert_id: int) -> None:
    dismiss_alert(conn, alert_id)


def run_match_scores(conn: sqlite3.Connection, *, force: bool = False) -> int:
    return score_all_jobs(conn, force=force)


def scorecard_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT j.id, j.title, j.agency, j.series, j.grade_high, j.state, j.remote_status,
               ms.score, ms.explanation, ms.created_at
        FROM jobs j
        JOIN (
            SELECT job_id, MAX(id) AS latest_score_id
            FROM match_scores
            GROUP BY job_id
        ) latest ON latest.job_id = j.id
        JOIN match_scores ms ON ms.id = latest.latest_score_id
        ORDER BY ms.score DESC, j.close_date ASC
        LIMIT 100
        """,
        conn,
    )


def saved_searches_dataframe(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT id, name, query_params_json, alert_enabled, alert_frequency, created_at
        FROM saved_searches
        ORDER BY created_at DESC
        """,
        conn,
    )


def create_saved_search(
    conn: sqlite3.Connection,
    *,
    name: str,
    query_params: dict[str, Any],
    alert_enabled: bool,
    alert_frequency: str = "manual",
) -> int:
    from src.database import utc_now

    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO saved_searches
            (name, query_params_json, alert_enabled, alert_frequency, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            json.dumps(query_params, sort_keys=True),
            1 if alert_enabled else 0,
            alert_frequency,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _scalar(conn: sqlite3.Connection, sql: str) -> Any:
    return conn.execute(sql).fetchone()[0]


def _int_filter(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_filter(value: Any) -> float | None:
    if value in (None, "", 0):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _bounds_contains(bounds: dict[str, float], lat: float, lon: float) -> bool:
    south = bounds["south"]
    north = bounds["north"]
    west = bounds["west"]
    east = bounds["east"]
    if lat < south or lat > north:
        return False
    if west <= east:
        return west <= lon <= east
    return lon >= west or lon <= east
