"""Pure query functions for the public map (`thegrandpipeline.com/map`).

Reads the local SQLite database and returns plain Python dicts/lists ready
for JSON serialization. Has no Streamlit imports, no file I/O, and no
side effects on the database — the CLI entry in
`scripts/export_public_map.py` orchestrates writing files.

Per ADR-0016 the public map is fed by static snapshots; per ADR-0002 the
OPM overlay must be labeled "federal workforce, not postings" — that label
is part of the manifest emitted from this module.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
GENERATOR = "scripts/export_public_map.py"


# ---------- Open postings (the map's primary feature) -----------------------


def open_postings_features(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return one GeoJSON-ready feature per (job, location) with a coordinate.

    Includes only USAJOBS postings whose close_date is in the future or null.
    Postings without a city-level or state-centroid match are omitted from
    the feature list (counted separately by `geocoding_summary`).
    """
    rows = conn.execute(
        """
        SELECT
            j.id              AS job_id,
            j.title           AS title,
            j.agency          AS agency,
            j.agency_code     AS agency_code,
            j.series          AS series,
            j.grade_low       AS grade_low,
            j.grade_high      AS grade_high,
            j.pay_plan        AS pay_plan,
            j.salary_min      AS salary_min,
            j.salary_max      AS salary_max,
            j.remote_status   AS remote_status,
            j.close_date      AS close_date,
            j.url             AS url,
            jl.city           AS jl_city,
            jl.state          AS jl_state,
            jl.location_text  AS jl_location_text,
            jl.remote_indicator AS jl_remote_indicator,
            COALESCE(city_lookup.lat, state_lookup.lat) AS lat,
            COALESCE(city_lookup.lon, state_lookup.lon) AS lon,
            CASE
                WHEN city_lookup.lat IS NOT NULL THEN city_lookup.geo_quality
                WHEN state_lookup.lat IS NOT NULL THEN state_lookup.geo_quality
                ELSE NULL
            END AS geo_quality
        FROM jobs j
        JOIN job_locations jl ON jl.job_id = j.id
        LEFT JOIN locations_geocoded city_lookup
            ON city_lookup.city = LOWER(TRIM(COALESCE(jl.city, '')))
            AND city_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        LEFT JOIN locations_geocoded state_lookup
            ON state_lookup.city = ''
            AND state_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
          AND COALESCE(j.url, '') <> ''
        """
    ).fetchall()

    features: list[dict[str, Any]] = []
    for row in rows:
        if row["lat"] is None or row["lon"] is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(row["lon"], 5), round(row["lat"], 5)],
                },
                "properties": {
                    "id": int(row["job_id"]),
                    "title": row["title"],
                    "agency_code": row["agency_code"],
                    "series": row["series"],
                    "grade_low": row["grade_low"],
                    "grade_high": row["grade_high"],
                    "pay_plan": row["pay_plan"],
                    "salary_min": _round_or_none(row["salary_min"]),
                    "salary_max": _round_or_none(row["salary_max"]),
                    "remote_status": row["remote_status"],
                    "close_date": row["close_date"],
                    "city": row["jl_city"],
                    "state": (row["jl_state"] or "").upper() or None,
                    "geo_quality": row["geo_quality"],
                },
            }
        )
    return features


def jobs_geojson(conn: sqlite3.Connection) -> dict[str, Any]:
    """Wrap `open_postings_features` in a GeoJSON FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": open_postings_features(conn),
    }


# ---------- Per-job detail panel --------------------------------------------


def job_details(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Return `{job_id: {detail fields}}` for every open posting.

    The map fetches this lazily when the user clicks a marker, so we keep
    each entry small but include enough context for a single-page card:
    title, agency, dates, salary, every duty location, and the apply URL.
    """
    job_rows = conn.execute(
        """
        SELECT
            j.id            AS job_id,
            j.title         AS title,
            j.agency        AS agency,
            j.department    AS department,
            j.agency_code   AS agency_code,
            j.series        AS series,
            j.pay_plan      AS pay_plan,
            j.grade_low     AS grade_low,
            j.grade_high    AS grade_high,
            j.salary_min    AS salary_min,
            j.salary_max    AS salary_max,
            j.salary_type   AS salary_type,
            j.remote_status AS remote_status,
            j.open_date     AS open_date,
            j.close_date    AS close_date,
            j.hiring_paths  AS hiring_paths,
            j.url           AS url
        FROM jobs j
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
          AND COALESCE(j.url, '') <> ''
        """
    ).fetchall()

    location_rows = conn.execute(
        """
        SELECT j.id AS job_id, jl.city AS city, jl.state AS state,
               jl.location_text AS location_text
        FROM jobs j
        JOIN job_locations jl ON jl.job_id = j.id
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
        """
    ).fetchall()

    locations_by_job: dict[int, list[dict[str, Any]]] = {}
    for row in location_rows:
        locations_by_job.setdefault(int(row["job_id"]), []).append(
            {
                "city": row["city"],
                "state": (row["state"] or "").upper() or None,
                "location_text": row["location_text"],
            }
        )

    details: dict[str, dict[str, Any]] = {}
    for row in job_rows:
        job_id = int(row["job_id"])
        details[str(job_id)] = {
            "id": job_id,
            "title": row["title"],
            "agency": row["agency"],
            "department": row["department"],
            "agency_code": row["agency_code"],
            "series": row["series"],
            "pay_plan": row["pay_plan"],
            "grade_low": row["grade_low"],
            "grade_high": row["grade_high"],
            "salary_min": _round_or_none(row["salary_min"]),
            "salary_max": _round_or_none(row["salary_max"]),
            "salary_type": row["salary_type"],
            "remote_status": row["remote_status"],
            "open_date": row["open_date"],
            "close_date": row["close_date"],
            "hiring_paths": row["hiring_paths"],
            "url": row["url"],
            "locations": locations_by_job.get(job_id, []),
        }
    return details


# ---------- OPM overlay -----------------------------------------------------


def opm_state_aggregates(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Return `{state: {employment, accessions, separations}}` for the overlay."""
    if not _table_exists(conn, "opm_workforce_records"):
        return {}
    rows = conn.execute(
        """
        SELECT
            UPPER(TRIM(location_state)) AS state,
            SUM(COALESCE(employment_count, 0))  AS employment,
            SUM(COALESCE(accessions_count, 0))  AS accessions,
            SUM(COALESCE(separations_count, 0)) AS separations
        FROM opm_workforce_records
        WHERE location_state IS NOT NULL
          AND length(TRIM(location_state)) = 2
        GROUP BY UPPER(TRIM(location_state))
        """
    ).fetchall()
    return {
        row["state"]: {
            "employment": int(row["employment"] or 0),
            "accessions": int(row["accessions"] or 0),
            "separations": int(row["separations"] or 0),
        }
        for row in rows
        if row["state"]
    }


# ---------- Filter option lists --------------------------------------------


def agency_options(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(j.agency_code, '') AS code,
            COALESCE(MAX(j.agency), '') AS label,
            COUNT(DISTINCT j.id) AS postings
        FROM jobs j
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
          AND COALESCE(j.agency_code, j.agency) IS NOT NULL
        GROUP BY COALESCE(j.agency_code, '')
        ORDER BY postings DESC, label
        """
    ).fetchall()
    return [
        {
            "code": row["code"] or None,
            "label": row["label"] or row["code"] or "Unknown",
            "postings": int(row["postings"]),
        }
        for row in rows
    ]


def series_options(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT j.series AS series, COUNT(DISTINCT j.id) AS postings
        FROM jobs j
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
          AND j.series IS NOT NULL
          AND TRIM(j.series) <> ''
        GROUP BY j.series
        ORDER BY postings DESC, j.series
        """
    ).fetchall()
    series_codes = [row["series"] for row in rows]
    labels = _series_labels(conn, series_codes)
    return [
        {
            "code": row["series"],
            "label": labels.get(row["series"]) or row["series"],
            "postings": int(row["postings"]),
        }
        for row in rows
    ]


# ---------- Manifest --------------------------------------------------------


def geocoding_summary(conn: sqlite3.Connection) -> dict[str, int]:
    """Counts of city, state-centroid, and unmatched location rows for open postings."""
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN city_lookup.lat IS NOT NULL THEN 1 ELSE 0 END) AS city_matches,
            SUM(CASE WHEN city_lookup.lat IS NULL AND state_lookup.lat IS NOT NULL THEN 1 ELSE 0 END) AS state_matches,
            SUM(CASE WHEN city_lookup.lat IS NULL AND state_lookup.lat IS NULL THEN 1 ELSE 0 END) AS unmatched,
            COUNT(*) AS total
        FROM jobs j
        JOIN job_locations jl ON jl.job_id = j.id
        LEFT JOIN locations_geocoded city_lookup
            ON city_lookup.city = LOWER(TRIM(COALESCE(jl.city, '')))
            AND city_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        LEFT JOIN locations_geocoded state_lookup
            ON state_lookup.city = ''
            AND state_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
        """
    ).fetchone()
    return {
        "city_matches": int(row["city_matches"] or 0),
        "state_matches": int(row["state_matches"] or 0),
        "unmatched": int(row["unmatched"] or 0),
        "total": int(row["total"] or 0),
    }


def manifest(
    conn: sqlite3.Connection,
    *,
    feature_count: int,
    job_count: int,
    opm_state_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feature_count": feature_count,
        "job_count": job_count,
        "opm_state_count": opm_state_count,
        "opm_label": "federal workforce, not postings",
        "geocoding": geocoding_summary(conn),
    }


# ---------- Helpers ---------------------------------------------------------


def _round_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _series_labels(conn: sqlite3.Connection, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    placeholders = ",".join("?" for _ in codes)
    rows = conn.execute(
        f"""
        SELECT code, label FROM code_lists
        WHERE list_name='priority_series' AND code IN ({placeholders})
        """,
        codes,
    ).fetchall()
    return {row["code"]: row["label"] for row in rows if row["label"]}
