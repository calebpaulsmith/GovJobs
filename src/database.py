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


STATE_NAME_TO_CODE = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Puerto Rico": "PR",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


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
            latitude REAL,
            longitude REAL,
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

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            application_status TEXT NOT NULL DEFAULT 'Draft',
            resume_version TEXT,
            usajobs_application_id TEXT,
            application_url TEXT,
            submitted_at TEXT,
            referred_at TEXT,
            interview_at TEXT,
            outcome TEXT,
            next_action TEXT,
            next_action_due TEXT,
            contact_name TEXT,
            contact_email TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_applications_status
            ON applications(application_status);
        CREATE INDEX IF NOT EXISTS idx_applications_next_action_due
            ON applications(next_action_due);

        CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_application_events_application_id
            ON application_events(application_id);

        CREATE TABLE IF NOT EXISTS resume_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE,
            file_name TEXT,
            file_path TEXT,
            version_date TEXT,
            target_series TEXT,
            target_grade TEXT,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_resume_versions_active
            ON resume_versions(active);

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

        CREATE TABLE IF NOT EXISTS repost_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            groups_created INTEGER DEFAULT 0,
            members_created INTEGER DEFAULT 0,
            params_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS repost_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            group_signature TEXT NOT NULL,
            group_title TEXT,
            agency_key TEXT,
            series_key TEXT,
            member_count INTEGER NOT NULL,
            confidence_score REAL NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES repost_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_repost_groups_run_id
            ON repost_groups(run_id);
        CREATE INDEX IF NOT EXISTS idx_repost_groups_signature
            ON repost_groups(group_signature);

        CREATE TABLE IF NOT EXISTS repost_group_members (
            group_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            title_similarity REAL,
            text_hash TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(group_id, job_id),
            FOREIGN KEY(group_id) REFERENCES repost_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_repost_group_members_job_id
            ON repost_group_members(job_id);

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

        CREATE TABLE IF NOT EXISTS locations_geocoded (
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            lat REAL,
            lon REAL,
            county_fips TEXT,
            geo_quality TEXT,
            source TEXT,
            geocoded_at TEXT NOT NULL,
            PRIMARY KEY(city, state)
        );

        CREATE INDEX IF NOT EXISTS idx_locations_geocoded_state
            ON locations_geocoded(state);

        CREATE TABLE IF NOT EXISTS geocoding_misses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            state TEXT,
            location_text TEXT,
            seen_count INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(city, state, location_text)
        );

        CREATE TABLE IF NOT EXISTS zip_centroids (
            zip TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            city TEXT,
            state TEXT,
            county_fips TEXT,
            source TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_zip_centroids_state
            ON zip_centroids(state);
        CREATE INDEX IF NOT EXISTS idx_zip_centroids_county
            ON zip_centroids(county_fips);

        CREATE TABLE IF NOT EXISTS pay_plans (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            has_locality_adjustment INTEGER NOT NULL DEFAULT 0,
            has_steps INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pay_scales (
            pay_plan TEXT NOT NULL,
            year INTEGER NOT NULL,
            grade TEXT NOT NULL,
            step INTEGER NOT NULL DEFAULT 0,
            locality_code TEXT NOT NULL DEFAULT '',
            annual_rate REAL NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            imported_at TEXT NOT NULL,
            PRIMARY KEY(pay_plan, year, grade, step, locality_code)
        );

        CREATE INDEX IF NOT EXISTS idx_pay_scales_lookup
            ON pay_scales(pay_plan, year, locality_code);

        CREATE TABLE IF NOT EXISTS locality_pay_areas (
            code TEXT NOT NULL,
            year INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            adjustment_pct REAL NOT NULL,
            polygon_path TEXT,
            source TEXT NOT NULL,
            source_url TEXT,
            imported_at TEXT NOT NULL,
            PRIMARY KEY(code, year)
        );

        CREATE TABLE IF NOT EXISTS locality_pay_counties (
            locality_code TEXT NOT NULL,
            year INTEGER NOT NULL,
            county_fips TEXT NOT NULL,
            inclusion_type TEXT NOT NULL DEFAULT 'core',
            PRIMARY KEY(locality_code, year, county_fips)
        );

        CREATE INDEX IF NOT EXISTS idx_locality_pay_counties_fips
            ON locality_pay_counties(year, county_fips);

        CREATE TABLE IF NOT EXISTS counties (
            fips TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            state TEXT NOT NULL,
            cbsa_code TEXT,
            polygon_path TEXT,
            source TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_counties_state ON counties(state);
        CREATE INDEX IF NOT EXISTS idx_counties_cbsa ON counties(cbsa_code);

        CREATE TABLE IF NOT EXISTS metro_areas (
            cbsa_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            cbsa_type TEXT,
            polygon_path TEXT,
            source TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS state_polygons (
            state TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            polygon_path TEXT,
            source TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS federal_properties (
            frpp_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            property_type TEXT,
            agency TEXT,
            agency_code TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            county_fips TEXT,
            latitude REAL,
            longitude REAL,
            building_status TEXT,
            source TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_federal_properties_state
            ON federal_properties(state);
        CREATE INDEX IF NOT EXISTS idx_federal_properties_agency_code
            ON federal_properties(agency_code);

        CREATE TABLE IF NOT EXISTS cost_of_living_index (
            year INTEGER NOT NULL,
            geo_type TEXT NOT NULL,
            geo_code TEXT NOT NULL,
            rpp_overall REAL,
            rpp_goods REAL,
            rpp_services REAL,
            rpp_rents REAL,
            source TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY(year, geo_type, geo_code, source)
        );

        CREATE INDEX IF NOT EXISTS idx_cost_of_living_geo
            ON cost_of_living_index(geo_type, geo_code);

        CREATE TABLE IF NOT EXISTS data_source_status (
            source_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL,
            last_run_at TEXT,
            last_success_at TEXT,
            last_error TEXT,
            row_count INTEGER,
            manual_override INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_data_source_status_category
            ON data_source_status(category);
        """
    )
    _ensure_column(conn, "jobs", "agency_code", "TEXT")
    _ensure_column(conn, "jobs", "department_code", "TEXT")
    _ensure_column(conn, "job_locations", "latitude", "REAL")
    _ensure_column(conn, "job_locations", "longitude", "REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_agency_code ON jobs(agency_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_department_code ON jobs(department_code)")
    _seed_core_codes(conn)
    _seed_state_centroids(conn)
    _seed_pay_plans(conn)
    _backfill_child_tables_from_jobs(conn)
    _backfill_search_locations_from_raw(conn)
    _set_meta(conn, "schema_version", "11")
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
            job_id, location_text, city, state, country, location_code, latitude, longitude,
            remote_indicator
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                job_id,
                _clean(row.get("location_text")),
                _clean(row.get("city")),
                _clean(row.get("state")),
                _clean(row.get("country")),
                _clean(row.get("location_code")),
                _float_or_none(row.get("latitude")),
                _float_or_none(row.get("longitude")),
                _clean(row.get("remote_indicator")),
            )
            for row in locations
            if any(
                row.get(key)
                for key in (
                    "location_text",
                    "city",
                    "state",
                    "country",
                    "location_code",
                    "latitude",
                    "longitude",
                )
            )
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


def upsert_application(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    application_status: str = "Draft",
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
) -> int:
    _require_job(conn, job_id)
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO applications (
            job_id, application_status, resume_version, usajobs_application_id,
            application_url, submitted_at, referred_at, interview_at, outcome,
            next_action, next_action_due, contact_name, contact_email, notes,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            application_status=excluded.application_status,
            resume_version=excluded.resume_version,
            usajobs_application_id=excluded.usajobs_application_id,
            application_url=excluded.application_url,
            submitted_at=excluded.submitted_at,
            referred_at=excluded.referred_at,
            interview_at=excluded.interview_at,
            outcome=excluded.outcome,
            next_action=excluded.next_action,
            next_action_due=excluded.next_action_due,
            contact_name=excluded.contact_name,
            contact_email=excluded.contact_email,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        RETURNING id
        """,
        (
            job_id,
            _clean(application_status) or "Draft",
            _clean(resume_version),
            _clean(usajobs_application_id),
            _clean(application_url),
            _clean(submitted_at),
            _clean(referred_at),
            _clean(interview_at),
            _clean(outcome),
            _clean(next_action),
            _clean(next_action_due),
            _clean(contact_name),
            _clean(contact_email),
            _clean(notes),
            now,
            now,
        ),
    )
    application_id = int(cur.fetchone()["id"])
    conn.commit()
    return application_id


def add_application_event(
    conn: sqlite3.Connection,
    *,
    application_id: int,
    event_type: str,
    event_date: str | None = None,
    notes: str | None = None,
) -> int:
    row = conn.execute("SELECT id FROM applications WHERE id=?", (application_id,)).fetchone()
    if row is None:
        raise ValueError(f"application_id does not exist: {application_id}")
    cur = conn.execute(
        """
        INSERT INTO application_events (application_id, event_type, event_date, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            application_id,
            _clean(event_type) or "note",
            _clean(event_date),
            _clean(notes),
            utc_now(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def upsert_resume_version(
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
    clean_label = _clean(label)
    if not clean_label:
        raise ValueError("resume version label is required")
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO resume_versions (
            label, file_name, file_path, version_date, target_series,
            target_grade, notes, active, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(label) DO UPDATE SET
            file_name=excluded.file_name,
            file_path=excluded.file_path,
            version_date=excluded.version_date,
            target_series=excluded.target_series,
            target_grade=excluded.target_grade,
            notes=excluded.notes,
            active=excluded.active,
            updated_at=excluded.updated_at
        RETURNING id
        """,
        (
            clean_label,
            _clean(file_name),
            _clean(file_path),
            _clean(version_date),
            _clean(target_series),
            _clean(target_grade),
            _clean(notes),
            1 if active else 0,
            now,
            now,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return int(row["id"])


def set_resume_version_active(conn: sqlite3.Connection, resume_version_id: int, active: bool) -> None:
    conn.execute(
        "UPDATE resume_versions SET active=?, updated_at=? WHERE id=?",
        (1 if active else 0, utc_now(), resume_version_id),
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


STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.7794, -86.8287), "AK": (64.0685, -152.2782), "AZ": (34.2744, -111.6602),
    "AR": (34.8938, -92.4426), "CA": (37.1841, -119.4696), "CO": (38.9972, -105.5478),
    "CT": (41.6219, -72.7273), "DE": (38.9896, -75.5050), "DC": (38.9101, -77.0147),
    "FL": (28.6305, -82.4497), "GA": (32.6415, -83.4426), "HI": (20.2927, -156.3737),
    "ID": (44.3509, -114.6130), "IL": (40.0417, -89.1965), "IN": (39.8942, -86.2816),
    "IA": (42.0751, -93.4960), "KS": (38.4937, -98.3804), "KY": (37.5347, -85.3021),
    "LA": (31.0689, -91.9968), "ME": (45.3695, -69.2428), "MD": (39.0550, -76.7909),
    "MA": (42.2596, -71.8083), "MI": (44.3467, -85.4102), "MN": (46.2807, -94.3053),
    "MS": (32.7364, -89.6678), "MO": (38.3566, -92.4580), "MT": (47.0527, -109.6333),
    "NE": (41.5378, -99.7951), "NV": (39.3289, -116.6312), "NH": (43.6805, -71.5811),
    "NJ": (40.1907, -74.6728), "NM": (34.4071, -106.1126), "NY": (42.9538, -75.5268),
    "NC": (35.5557, -79.3877), "ND": (47.4501, -100.4659), "OH": (40.2862, -82.7937),
    "OK": (35.5889, -97.4943), "OR": (43.9336, -120.5583), "PA": (40.8781, -77.7996),
    "RI": (41.6762, -71.5562), "SC": (33.9169, -80.8964), "SD": (44.4443, -100.2263),
    "TN": (35.8580, -86.3505), "TX": (31.4757, -99.3312), "UT": (39.3055, -111.6703),
    "VT": (44.0687, -72.6658), "VA": (37.5215, -78.8537), "WA": (47.3826, -120.4472),
    "WV": (38.6409, -80.6227), "WI": (44.6243, -89.9941), "WY": (42.9957, -107.5512),
    "PR": (18.2208, -66.5901), "VI": (18.3358, -64.8963), "GU": (13.4443, 144.7937),
    "AS": (-14.2710, -170.1322), "MP": (17.3308, 145.3847),
}


def _seed_state_centroids(conn: sqlite3.Connection) -> None:
    now = utc_now()
    rows = [
        ("", state, lat, lon, None, "state_centroid", "manual_seed", now)
        for state, (lat, lon) in STATE_CENTROIDS.items()
    ]
    conn.executemany(
        """
        INSERT INTO locations_geocoded (
            city, state, lat, lon, county_fips, geo_quality, source, geocoded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(city, state) DO UPDATE SET
            lat=excluded.lat,
            lon=excluded.lon,
            geo_quality=excluded.geo_quality,
            source=excluded.source,
            geocoded_at=excluded.geocoded_at
        """,
        rows,
    )


def upsert_geocoded_location(
    conn: sqlite3.Connection,
    city: str,
    state: str,
    lat: float | None,
    lon: float | None,
    county_fips: str | None = None,
    geo_quality: str = "city",
    source: str = "simplemaps",
) -> None:
    """Insert or update one (city, state) -> coordinate row.

    `city` is normalized to lowercase/stripped; `state` is uppercased. The
    state centroids seeded by `_seed_state_centroids` use an empty-string city
    as the sentinel and `geo_quality='state_centroid'`.
    """
    normalized_city = (city or "").strip().lower()
    normalized_state = (state or "").strip().upper()
    if not normalized_state:
        raise ValueError("state is required for geocoded location")
    conn.execute(
        """
        INSERT INTO locations_geocoded (
            city, state, lat, lon, county_fips, geo_quality, source, geocoded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(city, state) DO UPDATE SET
            lat=excluded.lat,
            lon=excluded.lon,
            county_fips=excluded.county_fips,
            geo_quality=excluded.geo_quality,
            source=excluded.source,
            geocoded_at=excluded.geocoded_at
        """,
        (
            normalized_city,
            normalized_state,
            lat,
            lon,
            county_fips,
            geo_quality,
            source,
            utc_now(),
        ),
    )


def upsert_zip_centroid(
    conn: sqlite3.Connection,
    zip_code: str,
    lat: float,
    lon: float,
    city: str | None = None,
    state: str | None = None,
    county_fips: str | None = None,
    source: str = "census_zcta",
) -> None:
    """Insert or update one 5-digit ZIP/ZCTA centroid row."""
    normalized_zip = re.sub(r"\D", "", zip_code or "")[:5]
    if len(normalized_zip) != 5:
        raise ValueError("zip_code must contain a 5-digit ZIP")
    conn.execute(
        """
        INSERT INTO zip_centroids (
            zip, lat, lon, city, state, county_fips, source, imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zip) DO UPDATE SET
            lat=excluded.lat,
            lon=excluded.lon,
            city=excluded.city,
            state=excluded.state,
            county_fips=excluded.county_fips,
            source=excluded.source,
            imported_at=excluded.imported_at
        """,
        (
            normalized_zip,
            float(lat),
            float(lon),
            (city or "").strip() or None,
            (state or "").strip().upper() or None,
            (county_fips or "").strip() or None,
            source,
            utc_now(),
        ),
    )


def lookup_geocoded_location(
    conn: sqlite3.Connection,
    city: str | None,
    state: str | None,
) -> dict[str, Any] | None:
    """Return `{lat, lon, county_fips, geo_quality}` for (city, state).

    Tries an exact city match first, then falls back to the state centroid.
    Returns None when no state centroid is seeded either (e.g., overseas).
    """
    normalized_state = (state or "").strip().upper()
    if not normalized_state:
        return None
    normalized_city = (city or "").strip().lower()
    if normalized_city:
        row = conn.execute(
            "SELECT lat, lon, county_fips, geo_quality FROM locations_geocoded "
            "WHERE city=? AND state=?",
            (normalized_city, normalized_state),
        ).fetchone()
        if row and row["lat"] is not None and row["lon"] is not None:
            return {
                "lat": row["lat"],
                "lon": row["lon"],
                "county_fips": row["county_fips"],
                "geo_quality": row["geo_quality"],
            }
    row = conn.execute(
        "SELECT lat, lon, county_fips, geo_quality FROM locations_geocoded "
        "WHERE city='' AND state=?",
        (normalized_state,),
    ).fetchone()
    if row and row["lat"] is not None and row["lon"] is not None:
        return {
            "lat": row["lat"],
            "lon": row["lon"],
            "county_fips": row["county_fips"],
            "geo_quality": row["geo_quality"],
        }
    return None


def record_geocoding_miss(
    conn: sqlite3.Connection,
    city: str | None,
    state: str | None,
    location_text: str | None = None,
) -> None:
    """Log an unmatched (city, state) pair so misses can be reviewed.

    Empty strings (rather than NULL) are stored for missing fields so the
    UNIQUE constraint can deduplicate via ON CONFLICT.
    """
    now = utc_now()
    conn.execute(
        """
        INSERT INTO geocoding_misses (
            city, state, location_text, seen_count, first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(city, state, location_text) DO UPDATE SET
            seen_count = seen_count + 1,
            last_seen_at = excluded.last_seen_at
        """,
        (
            (city or "").strip().lower(),
            (state or "").strip().upper(),
            (location_text or "").strip(),
            now,
            now,
        ),
    )


PAY_PLAN_SEED: list[dict[str, Any]] = [
    {
        "code": "GS",
        "name": "General Schedule",
        "description": "The white-collar pay system covering most professional, administrative, technical, and clerical federal positions.",
        "has_locality_adjustment": 1,
        "has_steps": 1,
        "notes": "15 grades, 10 steps each. Locality-adjusted in 58 areas plus 'Rest of US'.",
    },
    {
        "code": "FW",
        "name": "Federal Wage System",
        "description": "Hourly wage schedule for federal blue-collar (trades, crafts, labor) workers.",
        "has_locality_adjustment": 1,
        "has_steps": 1,
        "notes": "Wage areas defined by locality; steps vary.",
    },
    {
        "code": "ES",
        "name": "Senior Executive Service",
        "description": "Performance-based pay for senior executives.",
        "has_locality_adjustment": 1,
        "has_steps": 0,
        "notes": "Single rate within a band; no steps.",
    },
    {
        "code": "AD",
        "name": "Administratively Determined",
        "description": "Pay set by agency under specific statutory authority.",
        "has_locality_adjustment": 0,
        "has_steps": 0,
        "notes": "Highly variable; treat as opaque unless agency-specific table is loaded.",
    },
    {
        "code": "FP",
        "name": "TSA Pay Bands",
        "description": "Transportation Security Administration broadbanded pay system.",
        "has_locality_adjustment": 1,
        "has_steps": 0,
        "notes": "Bands instead of steps.",
    },
    {
        "code": "LE",
        "name": "Law Enforcement",
        "description": "Special pay tables for law enforcement officers.",
        "has_locality_adjustment": 1,
        "has_steps": 1,
        "notes": "GS-equivalent grades 3-10 only.",
    },
    {
        "code": "VN",
        "name": "Veterans Affairs Nurses",
        "description": "Title 38 nurse pay schedule administered by VA.",
        "has_locality_adjustment": 1,
        "has_steps": 1,
        "notes": "Local pay panel adjustments per facility.",
    },
    {
        "code": "EX",
        "name": "Executive Schedule",
        "description": "Pay for top federal officials (Levels I-V).",
        "has_locality_adjustment": 0,
        "has_steps": 0,
        "notes": "5 levels; flat rate.",
    },
    {
        "code": "SL",
        "name": "Senior Level",
        "description": "Senior-level non-executive professional positions.",
        "has_locality_adjustment": 1,
        "has_steps": 0,
        "notes": "Pay range, not steps.",
    },
    {
        "code": "ST",
        "name": "Scientific & Professional",
        "description": "Senior scientific and technical positions.",
        "has_locality_adjustment": 1,
        "has_steps": 0,
        "notes": "Pay range, not steps.",
    },
]


def _seed_pay_plans(conn: sqlite3.Connection) -> None:
    now = utc_now()
    rows = [
        (
            plan["code"],
            plan["name"],
            plan.get("description"),
            int(plan.get("has_locality_adjustment", 0)),
            int(plan.get("has_steps", 1)),
            plan.get("notes"),
            now,
        )
        for plan in PAY_PLAN_SEED
    ]
    conn.executemany(
        """
        INSERT INTO pay_plans (
            code, name, description, has_locality_adjustment, has_steps, notes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            has_locality_adjustment=excluded.has_locality_adjustment,
            has_steps=excluded.has_steps,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """,
        rows,
    )


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
        ("agency_aliases", "FEMA", "HSCB", "Federal Emergency Management Agency", "manual_seed", now),
        ("agency_aliases", "FEDERAL EMERGENCY MANAGEMENT AGENCY", "HSCB", None, "manual_seed", now),
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


def _backfill_search_locations_from_raw(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, position_id, usajobs_control_number, raw_json_path
        FROM jobs
        WHERE source = 'usajobs_search'
          AND raw_json_path IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM job_locations jl
              WHERE jl.job_id = jobs.id
                AND jl.latitude IS NOT NULL
                AND jl.longitude IS NOT NULL
          )
        """
    ).fetchall()
    for row in rows:
        raw_path = Path(row["raw_json_path"])
        if not raw_path.exists():
            continue
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        descriptor = _find_search_descriptor(
            payload,
            position_id=row["position_id"],
            control_number=row["usajobs_control_number"],
        )
        if not descriptor:
            continue
        locations = _search_descriptor_locations(descriptor)
        if locations:
            replace_job_locations(conn, int(row["id"]), locations)


def _find_search_descriptor(
    payload: Mapping[str, Any],
    *,
    position_id: str | None,
    control_number: str | None,
) -> Mapping[str, Any] | None:
    items = payload.get("SearchResult", {}).get("SearchResultItems") or payload.get("SearchResultItems") or []
    for item in _listify(items):
        descriptor = item.get("MatchedObjectDescriptor") if isinstance(item, Mapping) else None
        if not isinstance(descriptor, Mapping):
            continue
        if position_id and _clean(descriptor.get("PositionID")) == position_id:
            return descriptor
        if control_number and _position_uri_control_number(descriptor.get("PositionURI")) == control_number:
            return descriptor
    return None


def _search_descriptor_locations(descriptor: Mapping[str, Any]) -> list[dict[str, Any]]:
    details = descriptor.get("UserArea", {}).get("Details", {})
    rows: list[dict[str, Any]] = []
    for location in _listify(descriptor.get("PositionLocation")):
        if not isinstance(location, Mapping):
            continue
        rows.append(
            {
                "location_text": _clean(
                    location.get("LocationName")
                    or location.get("CityName")
                    or descriptor.get("PositionLocationDisplay")
                ),
                "city": _clean(location.get("CityName") or location.get("LocationName")),
                "state": _state_code(location.get("CountrySubDivisionCode")),
                "country": _clean(location.get("CountryCode")),
                "latitude": location.get("Latitude") or location.get("PositionLocationLatitude"),
                "longitude": location.get("Longitude") or location.get("PositionLocationLongitude"),
                "remote_indicator": _search_remote_status(
                    details.get("RemoteIndicator"),
                    details.get("TeleworkEligible"),
                ),
            }
        )
    return rows


def _position_uri_control_number(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    match = re.search(r"/job/(\d+)", text)
    return match.group(1) if match else None


def _state_code(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    if len(text) == 2:
        return text.upper()
    return STATE_NAME_TO_CODE.get(text)


def _search_remote_status(remote_indicator: Any, telework_eligible: Any) -> str:
    if str(remote_indicator).strip().lower() in {"true", "1", "yes", "y"}:
        return "remote"
    if str(telework_eligible).strip().lower() in {"true", "1", "yes", "y"}:
        return "hybrid"
    return "onsite"


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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
