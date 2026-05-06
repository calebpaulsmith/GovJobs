"""SQLite persistence layer for the local federal-jobs database.

The functions in this module are intentionally small and boring: Streamlit
pages and importers should call these helpers instead of writing SQL inline.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JOB_COLUMNS = (
    "source",
    "usajobs_control_number",
    "position_id",
    "announcement_number",
    "title",
    "department",
    "agency",
    "sub_agency",
    "agency_code",
    "department_code",
    "series",
    "grade_low",
    "grade_high",
    "pay_plan",
    "salary_min",
    "salary_max",
    "salary_type",
    "location_text",
    "state",
    "city",
    "remote_status",
    "telework_status",
    "open_date",
    "close_date",
    "hiring_paths",
    "appointment_type",
    "work_schedule",
    "supervisory_status",
    "travel_required",
    "security_clearance",
    "promotion_potential",
    "url",
    "source_endpoint",
    "source_query_hash",
    "raw_json_path",
)

JOB_TEXT_COLUMNS = (
    "summary",
    "duties",
    "qualifications",
    "specialized_experience",
    "education",
    "required_documents",
    "how_to_apply",
    "evaluation_criteria",
    "conditions_of_employment",
    "raw_text",
    "raw_json_path",
)

MANIFEST_UPDATE_COLUMNS = {
    "date_range_start",
    "date_range_end",
    "filters_json",
    "estimated_records",
    "actual_records",
    "pages_requested",
    "pages_completed",
    "status",
    "completed_at",
    "notes",
}

FEEDBACK_TYPES = {"liked", "disliked", "more_like_this", "less_like_this"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(target: sqlite3.Connection | str | Path) -> sqlite3.Connection:
    conn = target if isinstance(target, sqlite3.Connection) else connect(target)
    conn.executescript(
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            usajobs_control_number TEXT,
            position_id TEXT,
            announcement_number TEXT,
            title TEXT,
            department TEXT,
            agency TEXT,
            sub_agency TEXT,
            agency_code TEXT,
            department_code TEXT,
            series TEXT,
            grade_low TEXT,
            grade_high TEXT,
            pay_plan TEXT,
            salary_min REAL,
            salary_max REAL,
            salary_type TEXT,
            location_text TEXT,
            state TEXT,
            city TEXT,
            remote_status TEXT DEFAULT 'unknown',
            telework_status TEXT,
            open_date TEXT,
            close_date TEXT,
            hiring_paths TEXT,
            appointment_type TEXT,
            work_schedule TEXT,
            supervisory_status TEXT,
            travel_required TEXT,
            security_clearance TEXT,
            promotion_potential TEXT,
            url TEXT,
            source_endpoint TEXT,
            source_query_hash TEXT,
            raw_json_path TEXT,
            imported_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source, position_id, announcement_number)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_control_number
            ON jobs(source, usajobs_control_number)
            WHERE usajobs_control_number IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
        CREATE INDEX IF NOT EXISTS idx_jobs_agency ON jobs(agency);
        CREATE INDEX IF NOT EXISTS idx_jobs_series ON jobs(series);
        CREATE INDEX IF NOT EXISTS idx_jobs_close_date ON jobs(close_date);
        CREATE INDEX IF NOT EXISTS idx_jobs_open_date ON jobs(open_date);

        CREATE TABLE IF NOT EXISTS agency_codes (
            code TEXT PRIMARY KEY,
            name TEXT,
            department_code TEXT,
            department_name TEXT,
            active INTEGER,
            source TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS code_lists (
            list_name TEXT NOT NULL,
            code TEXT NOT NULL,
            label TEXT,
            description TEXT,
            source TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(list_name, code)
        );

        CREATE TABLE IF NOT EXISTS job_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            location_text TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            location_code TEXT,
            remote_indicator TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_locations_job_id ON job_locations(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_locations_state ON job_locations(state);

        CREATE TABLE IF NOT EXISTS job_categories (
            job_id INTEGER NOT NULL,
            series TEXT NOT NULL,
            name TEXT,
            is_primary INTEGER DEFAULT 0,
            PRIMARY KEY(job_id, series),
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_hiring_paths (
            job_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            label TEXT,
            PRIMARY KEY(job_id, code),
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_required_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            code TEXT,
            label TEXT,
            description TEXT,
            required INTEGER,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_required_documents_job_id
            ON job_required_documents(job_id);

        CREATE TABLE IF NOT EXISTS job_import_scopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            download_mode TEXT,
            agency_codes TEXT,
            department_codes TEXT,
            series TEXT,
            grade_low TEXT,
            grade_high TEXT,
            pay_plan TEXT,
            location_query TEXT,
            state TEXT,
            remote_status TEXT,
            hiring_paths TEXT,
            start_open_date TEXT,
            end_open_date TEXT,
            start_close_date TEXT,
            end_close_date TEXT,
            query_params_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS job_grades (
            job_id INTEGER NOT NULL,
            pay_plan TEXT,
            grade_low TEXT,
            grade_high TEXT,
            promotion_potential TEXT,
            is_primary INTEGER DEFAULT 1,
            PRIMARY KEY(job_id, pay_plan, grade_low, grade_high),
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_grades_grade_high ON job_grades(grade_high);

        CREATE TABLE IF NOT EXISTS job_salary_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            minimum REAL,
            maximum REAL,
            salary_type TEXT,
            currency TEXT DEFAULT 'USD',
            location_text TEXT,
            is_primary INTEGER DEFAULT 1,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_salary_ranges_job_id ON job_salary_ranges(job_id);

        CREATE TABLE IF NOT EXISTS job_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            requirement_type TEXT,
            code TEXT,
            label TEXT,
            description TEXT,
            required INTEGER,
            source_field TEXT,
            sequence INTEGER DEFAULT 0,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_requirements_job_id ON job_requirements(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_requirements_type ON job_requirements(requirement_type);

        CREATE TABLE IF NOT EXISTS job_qualification_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            grade TEXT,
            requirement_type TEXT,
            text TEXT NOT NULL,
            source_field TEXT,
            sequence INTEGER DEFAULT 0,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_qualification_requirements_job_id
            ON job_qualification_requirements(job_id);

        CREATE TABLE IF NOT EXISTS job_duties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            duty_text TEXT NOT NULL,
            sequence INTEGER DEFAULT 0,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_duties_job_id ON job_duties(job_id);

        CREATE TABLE IF NOT EXISTS job_evaluation_factors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            factor_text TEXT NOT NULL,
            sequence INTEGER DEFAULT 0,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_evaluation_factors_job_id
            ON job_evaluation_factors(job_id);

        CREATE TABLE IF NOT EXISTS job_openings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            location_text TEXT,
            openings INTEGER,
            total_openings INTEGER,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_openings_job_id ON job_openings(job_id);

        CREATE TABLE IF NOT EXISTS job_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            contact_type TEXT,
            name TEXT,
            email TEXT,
            phone TEXT,
            url TEXT,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_contacts_job_id ON job_contacts(job_id);

        CREATE TABLE IF NOT EXISTS job_security_clearances (
            job_id INTEGER PRIMARY KEY,
            clearance TEXT,
            position_sensitivity TEXT,
            adjudication_type TEXT,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_travel_requirements (
            job_id INTEGER PRIMARY KEY,
            travel_required TEXT,
            travel_percentage TEXT,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_application_options (
            job_id INTEGER PRIMARY KEY,
            apply_online_url TEXT,
            disable_apply_online INTEGER,
            accepts_uploaded_resumes INTEGER,
            accepts_attached_documents INTEGER,
            show_application_count INTEGER,
            source_field TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_text (
            job_id INTEGER PRIMARY KEY,
            summary TEXT,
            duties TEXT,
            qualifications TEXT,
            specialized_experience TEXT,
            education TEXT,
            required_documents TEXT,
            how_to_apply TEXT,
            evaluation_criteria TEXT,
            conditions_of_employment TEXT,
            raw_text TEXT,
            raw_json_path TEXT,
            imported_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS saved_jobs (
            job_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            priority INTEGER,
            saved_at TEXT NOT NULL,
            last_reviewed_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_tags (
            job_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY(job_id, tag),
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            query_params_json TEXT NOT NULL,
            alert_enabled INTEGER DEFAULT 0,
            alert_frequency TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS match_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            explanation TEXT,
            positive_factors_json TEXT,
            negative_factors_json TEXT,
            missing_info_json TEXT,
            scoring_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            feedback_type TEXT NOT NULL,
            explanation TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_feedback_job_id
            ON job_feedback(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_feedback_type
            ON job_feedback(feedback_type);

        CREATE TABLE IF NOT EXISTS recommendation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL,
            seed_job_id INTEGER,
            params_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(seed_job_id) REFERENCES jobs(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_recommendation_runs_seed
            ON recommendation_runs(seed_job_id);

        CREATE TABLE IF NOT EXISTS job_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            explanation TEXT,
            factors_json TEXT NOT NULL DEFAULT '[]',
            dismissed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES recommendation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_job_recommendations_run_score
            ON job_recommendations(run_id, score DESC);
        CREATE INDEX IF NOT EXISTS idx_job_recommendations_job_id
            ON job_recommendations(job_id);

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT,
            details_json TEXT NOT NULL DEFAULT '{}',
            source_search_id INTEGER,
            dedupe_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            dismissed_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(source_search_id) REFERENCES saved_searches(id) ON DELETE SET NULL,
            UNIQUE(alert_type, dedupe_key)
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_status_created
            ON alerts(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_alerts_job_id ON alerts(job_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_source_search_id ON alerts(source_search_id);

        CREATE TABLE IF NOT EXISTS alert_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            alerts_created INTEGER DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS raw_api_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            query_params_json TEXT NOT NULL,
            response_path TEXT,
            status_code INTEGER,
            record_count INTEGER,
            page_number INTEGER,
            request_time TEXT NOT NULL,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS import_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            download_mode TEXT NOT NULL,
            date_range_start TEXT,
            date_range_end TEXT,
            filters_json TEXT,
            estimated_records INTEGER,
            actual_records INTEGER,
            pages_requested INTEGER,
            pages_completed INTEGER,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS opm_workforce_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset TEXT,
            period_year INTEGER,
            period_quarter INTEGER,
            agency TEXT,
            sub_agency TEXT,
            occupation_series TEXT,
            grade TEXT,
            pay_plan TEXT,
            location_state TEXT,
            location_metro TEXT,
            employment_count INTEGER,
            accessions_count INTEGER,
            separations_count INTEGER,
            salary_avg REAL,
            raw_row_path TEXT,
            imported_at TEXT
        );
        """
    )
    _ensure_column(conn, "jobs", "agency_code", "TEXT")
    _ensure_column(conn, "jobs", "department_code", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_agency_code ON jobs(agency_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_department_code ON jobs(department_code)")
    _seed_core_codes(conn)
    _backfill_child_tables_from_jobs(conn)
    _set_meta(conn, "schema_version", "6")
    conn.commit()
    return conn


def upsert_job(conn: sqlite3.Connection, job: Mapping[str, Any]) -> int:
    if not job.get("source"):
        raise ValueError("job['source'] is required")

    now = utc_now()
    values = {column: _json_or_value(job.get(column)) for column in JOB_COLUMNS}
    existing_id = _find_existing_job_id(conn, values)

    if existing_id is not None:
        assignments = ", ".join(f"{column}=?" for column in JOB_COLUMNS)
        params = [values[column] for column in JOB_COLUMNS] + [now, existing_id]
        conn.execute(
            f"UPDATE jobs SET {assignments}, updated_at=? WHERE id=?",
            params,
        )
        _replace_job_children(conn, existing_id, job)
        conn.commit()
        return existing_id

    columns = (*JOB_COLUMNS, "imported_at", "updated_at")
    placeholders = ", ".join("?" for _ in columns)
    params = [values[column] for column in JOB_COLUMNS] + [now, now]
    cur = conn.execute(
        f"INSERT INTO jobs ({', '.join(columns)}) VALUES ({placeholders})",
        params,
    )
    job_id = int(cur.lastrowid)
    _replace_job_children(conn, job_id, job)
    conn.commit()
    return job_id


def upsert_job_text(conn: sqlite3.Connection, job_id: int, text_fields: Mapping[str, Any]) -> None:
    _require_job(conn, job_id)
    now = utc_now()
    values = {column: _json_or_value(text_fields.get(column)) for column in JOB_TEXT_COLUMNS}
    if not values.get("raw_text"):
        values["raw_text"] = build_raw_job_text(values)

    columns = ("job_id", *JOB_TEXT_COLUMNS, "imported_at", "updated_at")
    placeholders = ", ".join("?" for _ in columns)
    update_columns = ", ".join(
        f"{column}=excluded.{column}" for column in (*JOB_TEXT_COLUMNS, "updated_at")
    )
    params = [job_id] + [values[column] for column in JOB_TEXT_COLUMNS] + [now, now]
    conn.execute(
        f"""
        INSERT INTO job_text ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(job_id) DO UPDATE SET {update_columns}
        """,
        params,
    )
    if "required_document_rows" in text_fields:
        replace_job_required_documents(conn, job_id, text_fields.get("required_document_rows") or [])
    if "requirement_rows" in text_fields:
        replace_job_requirements(conn, job_id, text_fields.get("requirement_rows") or [])
    if "qualification_requirement_rows" in text_fields:
        replace_job_qualification_requirements(
            conn,
            job_id,
            text_fields.get("qualification_requirement_rows") or [],
        )
    if "duty_rows" in text_fields:
        replace_job_duties(conn, job_id, text_fields.get("duty_rows") or [])
    if "evaluation_factor_rows" in text_fields:
        replace_job_evaluation_factors(
            conn,
            job_id,
            text_fields.get("evaluation_factor_rows") or [],
        )
    conn.commit()


def replace_job_locations(
    conn: sqlite3.Connection,
    job_id: int,
    locations: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_locations WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_locations (
            job_id, location_text, city, state, country, location_code, remote_indicator
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("location_text")),
                _clean(row.get("city")),
                _clean(row.get("state")),
                _clean(row.get("country")),
                _clean(row.get("location_code")),
                _clean(row.get("remote_indicator")),
            )
            for row in locations
            if any(row.get(key) for key in ("location_text", "city", "state", "country", "location_code"))
        ],
    )


def replace_job_categories(
    conn: sqlite3.Connection,
    job_id: int,
    categories: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_categories WHERE job_id=?", (job_id,))
    rows: list[tuple[int, str, str | None, int]] = []
    seen: set[str] = set()
    for idx, category in enumerate(categories):
        series = _series_text(category.get("series"))
        if not series or series in seen:
            continue
        seen.add(series)
        rows.append((job_id, series, _clean(category.get("name")), 1 if idx == 0 else 0))
    conn.executemany(
        """
        INSERT INTO job_categories (job_id, series, name, is_primary)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def replace_job_hiring_paths(
    conn: sqlite3.Connection,
    job_id: int,
    hiring_paths: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_hiring_paths WHERE job_id=?", (job_id,))
    rows: list[tuple[int, str, str | None]] = []
    seen: set[str] = set()
    for item in hiring_paths:
        code = _clean(item.get("code") or item.get("label"))
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append((job_id, code, _clean(item.get("label"))))
    conn.executemany(
        """
        INSERT INTO job_hiring_paths (job_id, code, label)
        VALUES (?, ?, ?)
        """,
        rows,
    )


def replace_job_required_documents(
    conn: sqlite3.Connection,
    job_id: int,
    documents: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_required_documents WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_required_documents (job_id, code, label, description, required)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("code")),
                _clean(row.get("label")),
                _clean(row.get("description")),
                _bool_int(row.get("required")),
            )
            for row in documents
            if any(row.get(key) for key in ("code", "label", "description"))
        ],
    )


def replace_job_grades(
    conn: sqlite3.Connection,
    job_id: int,
    grades: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_grades WHERE job_id=?", (job_id,))
    rows: list[tuple[int, str | None, str | None, str | None, str | None, int]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for idx, row in enumerate(grades):
        pay_plan = _clean(row.get("pay_plan"))
        grade_low = _clean(row.get("grade_low"))
        grade_high = _clean(row.get("grade_high"))
        key = (pay_plan, grade_low, grade_high)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        rows.append(
            (
                job_id,
                pay_plan,
                grade_low,
                grade_high,
                _clean(row.get("promotion_potential")),
                _bool_int(row.get("is_primary")) if row.get("is_primary") is not None else (1 if idx == 0 else 0),
            )
        )
    conn.executemany(
        """
        INSERT INTO job_grades (
            job_id, pay_plan, grade_low, grade_high, promotion_potential, is_primary
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def replace_job_salary_ranges(
    conn: sqlite3.Connection,
    job_id: int,
    salary_ranges: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_salary_ranges WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_salary_ranges (
            job_id, minimum, maximum, salary_type, currency, location_text, is_primary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _float_or_none(row.get("minimum")),
                _float_or_none(row.get("maximum")),
                _clean(row.get("salary_type")),
                _clean(row.get("currency")) or "USD",
                _clean(row.get("location_text")),
                _bool_int(row.get("is_primary")) if row.get("is_primary") is not None else (1 if idx == 0 else 0),
            )
            for idx, row in enumerate(salary_ranges)
            if row.get("minimum") is not None or row.get("maximum") is not None
        ],
    )


def replace_job_requirements(
    conn: sqlite3.Connection,
    job_id: int,
    requirements: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_requirements WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_requirements (
            job_id, requirement_type, code, label, description, required, source_field, sequence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("requirement_type")) or "condition",
                _clean(row.get("code")),
                _clean(row.get("label")),
                _clean(row.get("description")),
                _bool_int(row.get("required")),
                _clean(row.get("source_field")),
                int(row.get("sequence") or idx),
            )
            for idx, row in enumerate(requirements)
            if any(row.get(key) for key in ("code", "label", "description"))
        ],
    )


def replace_job_qualification_requirements(
    conn: sqlite3.Connection,
    job_id: int,
    qualifications: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_qualification_requirements WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_qualification_requirements (
            job_id, grade, requirement_type, text, source_field, sequence
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("grade")),
                _clean(row.get("requirement_type")) or "qualification",
                _clean(row.get("text")),
                _clean(row.get("source_field")),
                int(row.get("sequence") or idx),
            )
            for idx, row in enumerate(qualifications)
            if _clean(row.get("text"))
        ],
    )


def replace_job_duties(
    conn: sqlite3.Connection,
    job_id: int,
    duties: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_duties WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_duties (job_id, duty_text, sequence, source_field)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("text")),
                int(row.get("sequence") or idx),
                _clean(row.get("source_field")) or "duties",
            )
            for idx, row in enumerate(duties)
            if _clean(row.get("text"))
        ],
    )


def replace_job_evaluation_factors(
    conn: sqlite3.Connection,
    job_id: int,
    factors: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_evaluation_factors WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_evaluation_factors (job_id, factor_text, sequence, source_field)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("text")),
                int(row.get("sequence") or idx),
                _clean(row.get("source_field")) or "evaluation_criteria",
            )
            for idx, row in enumerate(factors)
            if _clean(row.get("text"))
        ],
    )


def replace_job_openings(
    conn: sqlite3.Connection,
    job_id: int,
    openings: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_openings WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_openings (
            job_id, location_text, openings, total_openings, source_field
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("location_text")),
                _int_or_none(row.get("openings")),
                _int_or_none(row.get("total_openings")),
                _clean(row.get("source_field")),
            )
            for row in openings
            if row.get("openings") is not None or row.get("total_openings") is not None
        ],
    )


def replace_job_contacts(
    conn: sqlite3.Connection,
    job_id: int,
    contacts: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_contacts WHERE job_id=?", (job_id,))
    conn.executemany(
        """
        INSERT INTO job_contacts (
            job_id, contact_type, name, email, phone, url, source_field
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("contact_type")) or "public",
                _clean(row.get("name")),
                _clean(row.get("email")),
                _clean(row.get("phone")),
                _clean(row.get("url")),
                _clean(row.get("source_field")),
            )
            for row in contacts
            if any(row.get(key) for key in ("name", "email", "phone", "url"))
        ],
    )


def replace_job_security_clearances(
    conn: sqlite3.Connection,
    job_id: int,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_security_clearances WHERE job_id=?", (job_id,))
    row = next(iter(rows), None)
    if not row or not any(row.get(key) for key in ("clearance", "position_sensitivity", "adjudication_type")):
        return
    conn.execute(
        """
        INSERT INTO job_security_clearances (
            job_id, clearance, position_sensitivity, adjudication_type, source_field
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            job_id,
            _clean(row.get("clearance")),
            _clean(row.get("position_sensitivity")),
            _clean(row.get("adjudication_type")),
            _clean(row.get("source_field")),
        ),
    )


def replace_job_travel_requirements(
    conn: sqlite3.Connection,
    job_id: int,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_travel_requirements WHERE job_id=?", (job_id,))
    row = next(iter(rows), None)
    if not row or not any(row.get(key) for key in ("travel_required", "travel_percentage")):
        return
    conn.execute(
        """
        INSERT INTO job_travel_requirements (
            job_id, travel_required, travel_percentage, source_field
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            job_id,
            _clean(row.get("travel_required")),
            _clean(row.get("travel_percentage")),
            _clean(row.get("source_field")),
        ),
    )


def replace_job_application_options(
    conn: sqlite3.Connection,
    job_id: int,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    _require_job(conn, job_id)
    conn.execute("DELETE FROM job_application_options WHERE job_id=?", (job_id,))
    row = next(iter(rows), None)
    if not row or not any(
        row.get(key)
        for key in (
            "apply_online_url",
            "disable_apply_online",
            "accepts_uploaded_resumes",
            "accepts_attached_documents",
            "show_application_count",
        )
    ):
        return
    conn.execute(
        """
        INSERT INTO job_application_options (
            job_id, apply_online_url, disable_apply_online, accepts_uploaded_resumes,
            accepts_attached_documents, show_application_count, source_field
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            _clean(row.get("apply_online_url")),
            _bool_int(row.get("disable_apply_online")),
            _bool_int(row.get("accepts_uploaded_resumes")),
            _bool_int(row.get("accepts_attached_documents")),
            _bool_int(row.get("show_application_count")),
            _clean(row.get("source_field")),
        ),
    )


def create_job_import_scope(
    conn: sqlite3.Connection,
    *,
    name: str,
    source: str,
    endpoint: str,
    query_params: Mapping[str, Any],
    download_mode: str | None = None,
) -> int:
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO job_import_scopes (
            name, source, endpoint, download_mode, agency_codes, department_codes,
            series, grade_low, grade_high, pay_plan, location_query, state,
            remote_status, hiring_paths, start_open_date, end_open_date,
            start_close_date, end_close_date, query_params_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            source,
            endpoint,
            download_mode,
            _scope_value(query_params, "HiringAgencyCodes", "Organization"),
            _scope_value(query_params, "HiringDepartmentCodes"),
            _scope_value(query_params, "PositionSeries", "JobCategoryCode"),
            _scope_value(query_params, "PayGradeLow"),
            _scope_value(query_params, "PayGradeHigh"),
            _scope_value(query_params, "PayPlan"),
            _scope_value(query_params, "LocationName"),
            _scope_value(query_params, "State"),
            _scope_value(query_params, "RemoteIndicator", "remote_status"),
            _scope_value(query_params, "HiringPath", "hiring_paths"),
            _scope_value(query_params, "StartPositionOpenDate"),
            _scope_value(query_params, "EndPositionOpenDate"),
            _scope_value(query_params, "StartPositionCloseDate"),
            _scope_value(query_params, "EndPositionCloseDate"),
            json.dumps(query_params, sort_keys=True, default=str),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def upsert_agency_code(
    conn: sqlite3.Connection,
    *,
    code: str,
    name: str | None = None,
    department_code: str | None = None,
    department_name: str | None = None,
    active: bool | None = None,
    source: str | None = None,
) -> None:
    normalized_code = code.strip().upper()
    if not normalized_code:
        return
    conn.execute(
        """
        INSERT INTO agency_codes (
            code, name, department_code, department_name, active, source, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name=COALESCE(excluded.name, agency_codes.name),
            department_code=COALESCE(excluded.department_code, agency_codes.department_code),
            department_name=COALESCE(excluded.department_name, agency_codes.department_name),
            active=COALESCE(excluded.active, agency_codes.active),
            source=COALESCE(excluded.source, agency_codes.source),
            updated_at=excluded.updated_at
        """,
        (
            normalized_code,
            name,
            department_code,
            department_name,
            _bool_int(active),
            source,
            utc_now(),
        ),
    )


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def get_job_text(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM job_text WHERE job_id=?", (job_id,)).fetchone()


def record_raw_response(
    conn: sqlite3.Connection,
    *,
    source: str,
    endpoint: str,
    query_params: Mapping[str, Any] | None = None,
    response_path: str | None = None,
    status_code: int | None = None,
    record_count: int | None = None,
    page_number: int | None = None,
    error_message: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO raw_api_responses (
            source, endpoint, query_params_json, response_path, status_code,
            record_count, page_number, request_time, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            endpoint,
            json.dumps(query_params or {}, sort_keys=True),
            response_path,
            status_code,
            record_count,
            page_number,
            utc_now(),
            error_message,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def start_manifest(
    conn: sqlite3.Connection,
    *,
    source: str,
    endpoint: str,
    download_mode: str,
    date_range_start: str | None = None,
    date_range_end: str | None = None,
    filters: Mapping[str, Any] | None = None,
    estimated_records: int | None = None,
    pages_requested: int | None = None,
    notes: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO import_manifests (
            source, endpoint, download_mode, date_range_start, date_range_end,
            filters_json, estimated_records, pages_requested, pages_completed,
            status, started_at, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
        """,
        (
            source,
            endpoint,
            download_mode,
            date_range_start,
            date_range_end,
            json.dumps(filters or {}, sort_keys=True),
            estimated_records,
            pages_requested,
            0,
            utc_now(),
            notes,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_manifest(conn: sqlite3.Connection, manifest_id: int, **updates: Any) -> None:
    bad_keys = set(updates) - MANIFEST_UPDATE_COLUMNS
    if bad_keys:
        raise ValueError(f"Unsupported manifest columns: {sorted(bad_keys)}")
    if not updates:
        return
    assignments = ", ".join(f"{key}=?" for key in updates)
    params = [_json_or_value(value) for value in updates.values()] + [manifest_id]
    conn.execute(f"UPDATE import_manifests SET {assignments} WHERE id=?", params)
    conn.commit()


def complete_manifest(
    conn: sqlite3.Connection,
    manifest_id: int,
    *,
    status: str = "completed",
    actual_records: int | None = None,
    notes: str | None = None,
) -> None:
    updates: dict[str, Any] = {"status": status, "completed_at": utc_now()}
    if actual_records is not None:
        updates["actual_records"] = actual_records
    if notes is not None:
        updates["notes"] = notes
    update_manifest(conn, manifest_id, **updates)


def save_job(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    status: str = "New",
    priority: int | None = None,
) -> None:
    _require_job(conn, job_id)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO saved_jobs (job_id, status, priority, saved_at, last_reviewed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            status=excluded.status,
            priority=excluded.priority,
            last_reviewed_at=excluded.last_reviewed_at
        """,
        (job_id, status, priority, now, now),
    )
    conn.commit()


def add_job_note(conn: sqlite3.Connection, job_id: int, note: str) -> int:
    _require_job(conn, job_id)
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO job_notes (job_id, note, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (job_id, note, now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_job_tag(conn: sqlite3.Connection, job_id: int, tag: str) -> None:
    _require_job(conn, job_id)
    conn.execute(
        "INSERT OR IGNORE INTO job_tags (job_id, tag) VALUES (?, ?)",
        (job_id, tag.strip().lower()),
    )
    conn.commit()


def remove_job_tag(conn: sqlite3.Connection, job_id: int, tag: str) -> None:
    conn.execute("DELETE FROM job_tags WHERE job_id=? AND tag=?", (job_id, tag.strip().lower()))
    conn.commit()


def record_match_score(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    score: int,
    scoring_version: str,
    explanation: str | None = None,
    positive_factors: list[dict[str, Any]] | None = None,
    negative_factors: list[dict[str, Any]] | None = None,
    missing_info: list[dict[str, Any]] | None = None,
) -> int:
    _require_job(conn, job_id)
    cur = conn.execute(
        """
        INSERT INTO match_scores (
            job_id, score, explanation, positive_factors_json,
            negative_factors_json, missing_info_json, scoring_version, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            int(score),
            explanation,
            json.dumps(positive_factors or [], sort_keys=True),
            json.dumps(negative_factors or [], sort_keys=True),
            json.dumps(missing_info or [], sort_keys=True),
            scoring_version,
            utc_now(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def record_job_feedback(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    feedback_type: str,
    explanation: str | None = None,
) -> int:
    _require_job(conn, job_id)
    normalized_type = feedback_type.strip().lower()
    if normalized_type not in FEEDBACK_TYPES:
        raise ValueError(f"Unsupported feedback_type: {feedback_type}")
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO job_feedback (
            job_id, feedback_type, explanation, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (job_id, normalized_type, _clean(explanation), now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def create_recommendation_run(
    conn: sqlite3.Connection,
    *,
    run_type: str,
    seed_job_id: int | None = None,
    params: Mapping[str, Any] | None = None,
) -> int:
    if seed_job_id is not None:
        _require_job(conn, seed_job_id)
    cur = conn.execute(
        """
        INSERT INTO recommendation_runs (run_type, seed_job_id, params_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            run_type,
            seed_job_id,
            json.dumps(params or {}, sort_keys=True, default=str),
            utc_now(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def record_job_recommendation(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    job_id: int,
    score: int,
    explanation: str,
    factors: list[dict[str, Any]] | None = None,
    dismissed: bool = False,
) -> int:
    _require_job(conn, job_id)
    run = conn.execute("SELECT id FROM recommendation_runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"recommendation run does not exist: {run_id}")
    cur = conn.execute(
        """
        INSERT INTO job_recommendations (
            run_id, job_id, score, explanation, factors_json, dismissed, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            job_id,
            int(score),
            explanation,
            json.dumps(factors or [], sort_keys=True),
            1 if dismissed else 0,
            utc_now(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def replace_opm_workforce_records(
    conn: sqlite3.Connection,
    *,
    dataset: str,
    rows: Iterable[Mapping[str, Any]],
    clear_existing: bool = False,
) -> int:
    if clear_existing:
        conn.execute("DELETE FROM opm_workforce_records WHERE dataset=?", (dataset,))
    prepared = [
        (
            dataset,
            _int_or_none(row.get("period_year")),
            _int_or_none(row.get("period_quarter")),
            _clean(row.get("agency")),
            _clean(row.get("sub_agency")),
            _series_text(row.get("occupation_series")),
            _clean(row.get("grade")),
            _clean(row.get("pay_plan")),
            _clean(row.get("location_state")),
            _clean(row.get("location_metro")),
            _int_or_none(row.get("employment_count")),
            _int_or_none(row.get("accessions_count")),
            _int_or_none(row.get("separations_count")),
            _float_or_none(row.get("salary_avg")),
            _clean(row.get("raw_row_path")),
            utc_now(),
        )
        for row in rows
    ]
    conn.executemany(
        """
        INSERT INTO opm_workforce_records (
            dataset, period_year, period_quarter, agency, sub_agency,
            occupation_series, grade, pay_plan, location_state, location_metro,
            employment_count, accessions_count, separations_count, salary_avg,
            raw_row_path, imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        prepared,
    )
    conn.commit()
    return len(prepared)


def dismiss_job_recommendation(conn: sqlite3.Connection, recommendation_id: int) -> None:
    conn.execute(
        "UPDATE job_recommendations SET dismissed=1 WHERE id=?",
        (recommendation_id,),
    )
    conn.commit()


def build_raw_job_text(values: Mapping[str, Any]) -> str:
    ordered_keys = (
        "summary",
        "duties",
        "qualifications",
        "specialized_experience",
        "education",
        "conditions_of_employment",
        "evaluation_criteria",
        "required_documents",
        "how_to_apply",
    )
    parts = [str(values[key]).strip() for key in ordered_keys if values.get(key)]
    return "\n\n".join(parts)


def _find_existing_job_id(conn: sqlite3.Connection, values: Mapping[str, Any]) -> int | None:
    source = values.get("source")
    position_id = values.get("position_id")
    announcement_number = values.get("announcement_number")
    control_number = values.get("usajobs_control_number")

    if source and position_id and announcement_number:
        row = conn.execute(
            """
            SELECT id FROM jobs
            WHERE source=? AND position_id=? AND announcement_number=?
            """,
            (source, position_id, announcement_number),
        ).fetchone()
        if row:
            return int(row["id"])

    if source and control_number:
        row = conn.execute(
            "SELECT id FROM jobs WHERE source=? AND usajobs_control_number=?",
            (source, control_number),
        ).fetchone()
        if row:
            return int(row["id"])

    return None


def _require_job(conn: sqlite3.Connection, job_id: int) -> None:
    if get_job(conn, job_id) is None:
        raise ValueError(f"job_id does not exist: {job_id}")


def _json_or_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return value


def _replace_job_children(conn: sqlite3.Connection, job_id: int, job: Mapping[str, Any]) -> None:
    if "locations" in job:
        replace_job_locations(conn, job_id, _mapping_rows(job.get("locations")))
    if "categories" in job:
        replace_job_categories(conn, job_id, _mapping_rows(job.get("categories")))
    if "hiring_path_rows" in job:
        replace_job_hiring_paths(conn, job_id, _mapping_rows(job.get("hiring_path_rows")))
    if "required_document_rows" in job:
        replace_job_required_documents(
            conn,
            job_id,
            _mapping_rows(job.get("required_document_rows")),
        )
    if "grade_rows" in job:
        replace_job_grades(conn, job_id, _mapping_rows(job.get("grade_rows")))
    if "salary_range_rows" in job:
        replace_job_salary_ranges(conn, job_id, _mapping_rows(job.get("salary_range_rows")))
    if "opening_rows" in job:
        replace_job_openings(conn, job_id, _mapping_rows(job.get("opening_rows")))
    if "contact_rows" in job:
        replace_job_contacts(conn, job_id, _mapping_rows(job.get("contact_rows")))
    if "security_clearance_rows" in job:
        replace_job_security_clearances(
            conn,
            job_id,
            _mapping_rows(job.get("security_clearance_rows")),
        )
    if "travel_requirement_rows" in job:
        replace_job_travel_requirements(
            conn,
            job_id,
            _mapping_rows(job.get("travel_requirement_rows")),
        )
    if "application_option_rows" in job:
        replace_job_application_options(
            conn,
            job_id,
            _mapping_rows(job.get("application_option_rows")),
        )
    agency_code = _clean(job.get("agency_code"))
    if agency_code:
        upsert_agency_code(
            conn,
            code=agency_code,
            name=_clean(job.get("agency")),
            department_code=_clean(job.get("department_code")),
            department_name=_clean(job.get("department")),
            active=True,
            source="observed_import",
        )


def _mapping_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _series_text(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(4) if digits else text


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "active"}:
        return 1
    if text in {"false", "f", "no", "n", "0", "inactive"}:
        return 0
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def _scope_value(params: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = params.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple)):
            return ",".join(str(item) for item in value)
        return str(value)
    return None


def _split_text_items(text: str | None) -> list[str]:
    if not text:
        return []
    pieces = re.split(r"(?:\r?\n)+|(?:^|\s)[*-]\s+", str(text))
    cleaned = [re.sub(r"\s+", " ", piece).strip(" ;") for piece in pieces]
    return [piece for piece in cleaned if len(piece) >= 5]


def _first_grade(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"\bGS[-\s]?(\d{1,2})\b", text, flags=re.I)
    return match.group(1).zfill(2) if match else None


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _seed_core_codes(conn: sqlite3.Connection) -> None:
    upsert_agency_code(
        conn,
        code="HSCB",
        name="Federal Emergency Management Agency",
        department_code="HS",
        department_name="Department of Homeland Security",
        active=True,
        source="manual_seed",
    )
    now = utc_now()
    code_rows = [
        ("priority_series", "0089", "Emergency Management Specialist", None, "manual_seed", now),
        ("priority_series", "0301", "Miscellaneous Administration and Program", None, "manual_seed", now),
        ("priority_series", "0343", "Management and Program Analysis", None, "manual_seed", now),
        ("priority_series", "1109", "Grants Management", None, "manual_seed", now),
        ("department", "HS", "Department of Homeland Security", None, "manual_seed", now),
    ]
    conn.executemany(
        """
        INSERT INTO code_lists (list_name, code, label, description, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(list_name, code) DO UPDATE SET
            label=excluded.label,
            description=excluded.description,
            source=excluded.source,
            updated_at=excluded.updated_at
        """,
        code_rows,
    )


def _backfill_child_tables_from_jobs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO job_locations (job_id, location_text, city, state, remote_indicator)
        SELECT id, location_text, city, state, remote_status
        FROM jobs j
        WHERE NOT EXISTS (
            SELECT 1 FROM job_locations jl WHERE jl.job_id = j.id
        )
          AND (location_text IS NOT NULL OR city IS NOT NULL OR state IS NOT NULL)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO job_categories (job_id, series, is_primary)
        SELECT id, series, 1
        FROM jobs j
        WHERE series IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM job_categories jc WHERE jc.job_id = j.id
          )
        """
    )

    rows = conn.execute(
        """
        SELECT id, hiring_paths
        FROM jobs j
        WHERE hiring_paths IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM job_hiring_paths hp WHERE hp.job_id = j.id
          )
        """
    ).fetchall()
    for row in rows:
        try:
            values = json.loads(row["hiring_paths"])
        except (TypeError, json.JSONDecodeError):
            values = [row["hiring_paths"]]
        paths = []
        for item in values if isinstance(values, list) else [values]:
            if isinstance(item, Mapping):
                label = _clean(item.get("hiringPath") or item.get("label") or item.get("code"))
                code = _clean(item.get("code") or item.get("hiringPathCode") or label)
            else:
                label = _clean(item)
                code = label
            if code:
                paths.append({"code": code, "label": label})
        replace_job_hiring_paths(conn, int(row["id"]), paths)

    text_rows = conn.execute(
        """
        SELECT jt.job_id, jt.required_documents
        FROM job_text jt
        WHERE jt.required_documents IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM job_required_documents rd WHERE rd.job_id = jt.job_id
          )
        """
    ).fetchall()
    for row in text_rows:
        replace_job_required_documents(
            conn,
            int(row["job_id"]),
            [
                {
                    "label": str(row["required_documents"])[:120],
                    "description": row["required_documents"],
                }
            ],
        )

    conn.execute(
        """
        INSERT OR IGNORE INTO job_grades (
            job_id, pay_plan, grade_low, grade_high, promotion_potential, is_primary
        )
        SELECT id, pay_plan, grade_low, grade_high, promotion_potential, 1
        FROM jobs j
        WHERE NOT EXISTS (
            SELECT 1 FROM job_grades g WHERE g.job_id = j.id
        )
          AND (pay_plan IS NOT NULL OR grade_low IS NOT NULL OR grade_high IS NOT NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO job_salary_ranges (
            job_id, minimum, maximum, salary_type, currency, location_text, is_primary
        )
        SELECT id, salary_min, salary_max, salary_type, 'USD', location_text, 1
        FROM jobs j
        WHERE NOT EXISTS (
            SELECT 1 FROM job_salary_ranges s WHERE s.job_id = j.id
        )
          AND (salary_min IS NOT NULL OR salary_max IS NOT NULL)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO job_security_clearances (
            job_id, clearance, source_field
        )
        SELECT id, security_clearance, 'jobs.security_clearance'
        FROM jobs j
        WHERE security_clearance IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM job_security_clearances sc WHERE sc.job_id = j.id
          )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO job_travel_requirements (
            job_id, travel_required, source_field
        )
        SELECT id, travel_required, 'jobs.travel_required'
        FROM jobs j
        WHERE travel_required IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM job_travel_requirements tr WHERE tr.job_id = j.id
          )
        """
    )

    text_rows = conn.execute(
        """
        SELECT job_id, duties, qualifications, specialized_experience,
               evaluation_criteria, conditions_of_employment
        FROM job_text
        """
    ).fetchall()
    for row in text_rows:
        job_id = int(row["job_id"])
        if row["duties"] and not conn.execute(
            "SELECT 1 FROM job_duties WHERE job_id=? LIMIT 1", (job_id,)
        ).fetchone():
            replace_job_duties(
                conn,
                job_id,
                [
                    {"text": part, "sequence": idx, "source_field": "duties"}
                    for idx, part in enumerate(_split_text_items(row["duties"]))
                ],
            )
        if row["evaluation_criteria"] and not conn.execute(
            "SELECT 1 FROM job_evaluation_factors WHERE job_id=? LIMIT 1", (job_id,)
        ).fetchone():
            replace_job_evaluation_factors(
                conn,
                job_id,
                [
                    {"text": part, "sequence": idx, "source_field": "evaluation_criteria"}
                    for idx, part in enumerate(_split_text_items(row["evaluation_criteria"]))
                ],
            )
        if row["conditions_of_employment"] and not conn.execute(
            "SELECT 1 FROM job_requirements WHERE job_id=? LIMIT 1", (job_id,)
        ).fetchone():
            replace_job_requirements(
                conn,
                job_id,
                [
                    {
                        "requirement_type": "condition",
                        "description": part,
                        "source_field": "conditions_of_employment",
                        "sequence": idx,
                    }
                    for idx, part in enumerate(_split_text_items(row["conditions_of_employment"]))
                ],
            )
        if (row["qualifications"] or row["specialized_experience"]) and not conn.execute(
            "SELECT 1 FROM job_qualification_requirements WHERE job_id=? LIMIT 1", (job_id,)
        ).fetchone():
            text = row["specialized_experience"] or row["qualifications"]
            replace_job_qualification_requirements(
                conn,
                job_id,
                [
                    {
                        "grade": _first_grade(part),
                        "requirement_type": (
                            "specialized_experience"
                            if "specialized experience" in part.lower()
                            else "qualification"
                        ),
                        "text": part,
                        "source_field": "specialized_experience"
                        if row["specialized_experience"]
                        else "qualifications",
                        "sequence": idx,
                    }
                    for idx, part in enumerate(_split_text_items(text))
                ],
            )


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO meta (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, now),
    )
