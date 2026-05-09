"""Pure query functions for the public map (`thegrandpipeline.com/map`).

Reads the local SQLite database and returns plain Python dicts/lists ready
for JSON serialization. Has no Streamlit imports, no file I/O for the
marker queries — but the polygon emitters DO read polygon files referenced
by `state_polygons.polygon_path`, `counties.polygon_path`, etc., so they
take a ``repo_root`` argument that resolves repo-relative paths.

Per ADR-0016 the public map is fed by static snapshots; per ADR-0002 the
OPM overlay must be labeled "federal workforce, not postings" — that label
is part of the manifest emitted from this module. Per ADR-0017 the public
map's layered zoom model uses simplified polygon geometry (~10% of TIGER
detail) to keep the bundle small; ``simplify_geometry`` runs at export time.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.pay_calculator import calculate_job_pay_table
from src.reference_data import REST_OF_US_CODE

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2
GENERATOR = "scripts/export_public_map.py"

# Default Douglas-Peucker tolerances (degrees). Trade-off: lower = more detail,
# bigger bundle. ADR-0017 calls for ~10% of TIGER detail; these values produce
# polygons that look correct at the public map's maxzoom of 9.
DEFAULT_STATE_TOLERANCE = 0.05
DEFAULT_LOCALITY_TOLERANCE = 0.03
DEFAULT_COUNTY_TOLERANCE = 0.01
DEFAULT_METRO_TOLERANCE = 0.01


# ---------- Open postings (the map's primary feature) -----------------------


def _marker_dataset(
    conn: sqlite3.Connection, *, year: int, repo_root: Path | None = None
) -> list[dict[str, Any]]:
    """Return enriched marker rows used by both the GeoJSON and the polygon
    aggregations.

    Each row carries the public marker properties plus internal helpers
    (``county_fips``, ``cbsa_code``) needed to count postings per county or
    CBSA. The locality lookup is keyed by ``year`` because OPM redefines
    locality membership annually.
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
            jl.latitude       AS jl_lat,
            jl.longitude      AS jl_lon,
            COALESCE(jl.latitude, city_lookup.lat, state_lookup.lat) AS lat,
            COALESCE(jl.longitude, city_lookup.lon, state_lookup.lon) AS lon,
            CASE
                WHEN jl.latitude IS NOT NULL THEN 'source'
                WHEN city_lookup.lat IS NOT NULL THEN city_lookup.geo_quality
                WHEN state_lookup.lat IS NOT NULL THEN state_lookup.geo_quality
                ELSE NULL
            END AS geo_quality,
            city_lookup.county_fips AS county_fips,
            counties.cbsa_code      AS cbsa_code,
            lpc.locality_code       AS locality_code
        FROM jobs j
        JOIN job_locations jl ON jl.job_id = j.id
        LEFT JOIN locations_geocoded city_lookup
            ON city_lookup.city = LOWER(TRIM(COALESCE(jl.city, '')))
            AND city_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        LEFT JOIN locations_geocoded state_lookup
            ON state_lookup.city = ''
            AND state_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        LEFT JOIN counties ON counties.fips = city_lookup.county_fips
        LEFT JOIN locality_pay_counties lpc
            ON lpc.county_fips = city_lookup.county_fips
            AND lpc.year = ?
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
          AND COALESCE(j.url, '') <> ''
        """,
        (int(year),),
    ).fetchall()

    locality_lookup = _locality_point_lookup(conn, year=year, repo_root=repo_root)
    dataset: list[dict[str, Any]] = []
    for row in rows:
        if row["lat"] is None or row["lon"] is None:
            continue
        lat = float(row["lat"])
        lon = float(row["lon"])
        locality_code = row["locality_code"] or locality_lookup(lon, lat)
        dataset.append(
            {
                "job_id": int(row["job_id"]),
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
                "lat": lat,
                "lon": lon,
                "county_fips": row["county_fips"],
                "cbsa_code": row["cbsa_code"],
                "locality_code": locality_code,
            }
        )
    return dataset


def _feature_from_marker(marker: dict[str, Any]) -> dict[str, Any]:
    # Per-marker payload: only what the map needs at render time. Title,
    # salary_max, and geo_quality stay out (they live in jobs_detail.json,
    # lazy-loaded on JobCard mount). City and state are kept because the
    # JobCard's "Clicked location" row needs to remember which specific
    # marker the user clicked — `detail.locations[]` is the unordered full
    # list and can't tell us the click target. This keeps jobs.geojson
    # comfortably under Cloudflare Pages' 25 MiB per-file limit.
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [round(marker["lon"], 5), round(marker["lat"], 5)],
        },
        "properties": {
            "id": marker["job_id"],
            "agency_code": marker["agency_code"],
            "series": marker["series"],
            "grade_low": marker["grade_low"],
            "grade_high": marker["grade_high"],
            "pay_plan": marker["pay_plan"],
            "salary_min": marker["salary_min"],
            "remote_status": marker["remote_status"],
            "close_date": marker["close_date"],
            "city": marker["city"],
            "state": marker["state"],
            "locality_code": marker["locality_code"],
        },
    }


def open_postings_features(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return one GeoJSON-ready feature per (job, location) with a coordinate.

    Includes only USAJOBS postings whose close_date is in the future or null.
    Coordinate resolution per ADR-0019 / MAP_FEATURE_SPEC priority:

    1. ``job_locations.latitude/longitude`` — authoritative coords from the
       USAJOBS Search payload (added when the dashboard backfills coords).
    2. SimpleMaps city geocode in ``locations_geocoded`` (city-level).
    3. State centroid in ``locations_geocoded`` (low-confidence fallback).

    Postings with no coordinate at any level are omitted from the feature
    list and counted separately by ``geocoding_summary``.

    The ``locality_code`` property is the OPM locality area covering the
    marker's geocoded county for ``year`` (or the latest reference year if
    omitted). It is ``None`` when the city has no county FIPS or the
    county is not assigned to a locality area in that year.
    """
    resolved_year = year if year is not None else current_reference_year(conn)
    return [
        _feature_from_marker(marker)
        for marker in _marker_dataset(conn, year=resolved_year, repo_root=repo_root)
    ]


def recently_closed_features(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
    trailing_days: int = 90,
) -> list[dict[str, Any]]:
    """Return closed posting point features for the trailing review window."""
    resolved_year = year if year is not None else current_reference_year(conn)
    rows = conn.execute(
        """
        SELECT
            j.id              AS job_id,
            j.title           AS title,
            j.agency_code     AS agency_code,
            j.series          AS series,
            j.grade_low       AS grade_low,
            j.grade_high      AS grade_high,
            j.pay_plan        AS pay_plan,
            j.salary_min      AS salary_min,
            j.salary_max      AS salary_max,
            j.remote_status   AS remote_status,
            j.close_date      AS close_date,
            jl.city           AS jl_city,
            jl.state          AS jl_state,
            COALESCE(jl.latitude, city_lookup.lat, state_lookup.lat) AS lat,
            COALESCE(jl.longitude, city_lookup.lon, state_lookup.lon) AS lon,
            CASE
                WHEN jl.latitude IS NOT NULL THEN 'source'
                WHEN city_lookup.lat IS NOT NULL THEN city_lookup.geo_quality
                WHEN state_lookup.lat IS NOT NULL THEN state_lookup.geo_quality
                ELSE NULL
            END AS geo_quality,
            lpc.locality_code AS locality_code,
            CAST(julianday('now') - julianday(j.close_date) AS INTEGER) AS closed_within_days
        FROM jobs j
        JOIN job_locations jl ON jl.job_id = j.id
        LEFT JOIN locations_geocoded city_lookup
            ON city_lookup.city = LOWER(TRIM(COALESCE(jl.city, '')))
            AND city_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        LEFT JOIN locations_geocoded state_lookup
            ON state_lookup.city = ''
            AND state_lookup.state = UPPER(TRIM(COALESCE(jl.state, '')))
        LEFT JOIN locality_pay_counties lpc
            ON lpc.county_fips = city_lookup.county_fips
            AND lpc.year = ?
        WHERE j.source LIKE 'usajobs%'
          AND j.close_date IS NOT NULL
          AND j.close_date < date('now')
          AND j.close_date >= date('now', ?)
        """,
        (int(resolved_year), f"-{int(trailing_days)} days"),
    ).fetchall()

    features: list[dict[str, Any]] = []
    for row in rows:
        if row["lat"] is None or row["lon"] is None:
            continue
        feature = _feature_from_marker(
            {
                "job_id": int(row["job_id"]),
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
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "locality_code": row["locality_code"],
            }
        )
        feature["properties"]["status"] = "closed"
        feature["properties"]["closed_within_days"] = int(row["closed_within_days"] or 0)
        features.append(feature)
    return features


def jobs_geojson(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Wrap `open_postings_features` in a GeoJSON FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": open_postings_features(conn, year=year, repo_root=repo_root),
    }


def closed_jobs_geojson(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
    trailing_days: int = 90,
) -> dict[str, Any]:
    """Wrap `recently_closed_features` in a GeoJSON FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": recently_closed_features(conn, year=year, trailing_days=trailing_days),
    }


# ---------- Per-job detail panel --------------------------------------------


def _build_pay_grid(
    conn: sqlite3.Connection,
    *,
    pay_plan: str | None,
    year: int,
    city: str | None,
    state: str | None,
    grade_low: Any,
    grade_high: Any,
) -> dict[str, Any]:
    """Pre-compute the per-job locality-adjusted pay grid + status flag.

    Status semantics (D.5.11):
    - ``exact`` — every cell came from a locality-specific row in
      ``pay_scales`` (``method='locality_row'``). The bundled snapshot has
      OPM's published locality table for this (plan, year, locality).
    - ``approximated`` — at least one cell was derived as ``base × (1 + pct)``
      because no locality-specific row exists. Still useful, but operator
      should verify against the OPM PDF before relying on cents-precision.
    - ``unavailable`` — no rows at all for this (plan, year, grade range).
      JobCard renders the "Pay scale not yet ingested — see admin" message.
    """
    if not (pay_plan or "").strip() or grade_low is None or str(grade_low).strip() == "":
        return {
            "status": "unavailable",
            "year": int(year),
            "pay_plan": (pay_plan or "").upper() or None,
            "missing_reason": "Posting has no pay plan or grade.",
        }

    table = calculate_job_pay_table(
        conn,
        pay_plan_code=str(pay_plan).upper(),
        year=int(year),
        city=city,
        state=state,
        grade_low=grade_low,
        grade_high=grade_high if grade_high not in (None, "") else grade_low,
    )

    grades_payload: dict[str, dict[str, float]] = {}
    methods: set[str] = set()
    for grade, steps in (table.get("grades") or {}).items():
        cells: dict[str, float] = {}
        for step_key, cell in (steps or {}).items():
            rate = cell.get("rate")
            if rate is None:
                continue
            cells[str(step_key)] = round(float(rate), 2)
            methods.add(cell.get("method") or "")
        if cells:
            grades_payload[str(grade)] = cells

    if not grades_payload:
        return {
            "status": "unavailable",
            "year": int(year),
            "pay_plan": (pay_plan or "").upper() or None,
            "locality": table.get("locality"),
            "missing_reason": (
                f"pay_scales has no rows for plan {(pay_plan or '').upper()}, "
                f"year {year}, grade {grade_low}. See Public Map Admin to refresh "
                "OPM pay scales for this reference year."
            ),
            "notes": table.get("notes") or [],
        }

    if methods == {"locality_row"}:
        status = "exact"
    elif "locality_row" in methods:
        status = "exact"  # all filled cells were direct rows; mixed methods
    else:
        status = "approximated"

    return {
        "status": status,
        "year": int(year),
        "pay_plan": (pay_plan or "").upper() or None,
        "locality": table.get("locality"),
        "method": (
            "locality_row" if status == "exact" else "base_plus_adjustment"
        ),
        "grades": grades_payload,
        "notes": table.get("notes") or [],
    }


def job_details(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Return `{job_id: {detail fields}}` for every open posting.

    The map fetches this lazily when the user clicks a marker, so we keep
    each entry small but include enough context for a single-page card:
    title, agency, dates, salary, every duty location, the apply URL, and
    the pre-computed locality-adjusted pay grid (D.5.11). The pay grid is
    computed against the job's first listed duty location; JobCard shows the
    grid when ``status`` is ``exact``/``approximated`` and a "see admin"
    fallback when ``status`` is ``unavailable``.
    """
    resolved_year = int(year) if year is not None else current_reference_year(conn)
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
        locations = locations_by_job.get(job_id, [])
        first_loc = locations[0] if locations else {"city": None, "state": None}
        pay_grid = _build_pay_grid(
            conn,
            pay_plan=row["pay_plan"],
            year=resolved_year,
            city=first_loc.get("city"),
            state=first_loc.get("state"),
            grade_low=row["grade_low"],
            grade_high=row["grade_high"],
        )
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
            "locations": locations,
            "pay_grid": pay_grid,
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
    # Group by the strongest available identity: agency_code first (so
    # known codes collapse cleanly across name variants), agency name
    # otherwise (so unknown-code agencies still appear as distinct chips
    # instead of all collapsing into one mystery bucket — see the
    # 2026-05-09 agencies.json regression).
    rows = conn.execute(
        """
        SELECT
            j.agency_code AS code,
            COALESCE(ac.name, MAX(j.agency), '') AS name,
            COALESCE(ac.department_code, MAX(j.department_code), '') AS department_code,
            COALESCE(ac.department_name, MAX(j.department), '') AS department_name,
            COUNT(DISTINCT j.id) AS postings,
            CASE WHEN j.agency_code IS NOT NULL AND TRIM(j.agency_code) <> ''
                 THEN 'code' ELSE 'name' END AS group_key_type
        FROM jobs j
        LEFT JOIN agency_codes ac ON ac.code = j.agency_code
        WHERE j.source LIKE 'usajobs%'
          AND (j.close_date IS NULL OR j.close_date >= date('now'))
          AND COALESCE(j.agency_code, j.agency) IS NOT NULL
        GROUP BY
            CASE WHEN j.agency_code IS NOT NULL AND TRIM(j.agency_code) <> ''
                 THEN UPPER(TRIM(j.agency_code))
                 ELSE LOWER(TRIM(j.agency))
            END
        ORDER BY postings DESC, name
        """
    ).fetchall()
    aliases_by_code = _agency_aliases(conn)
    return [
        {
            "code": (row["code"] or None) if row["group_key_type"] == "code" else None,
            "name": row["name"] or row["code"] or "Unknown",
            # Keep `label` for older bundles/UI code; D.5.2's typeahead uses
            # `name` as the canonical display field.
            "label": row["name"] or row["code"] or "Unknown",
            "department_code": row["department_code"] or None,
            "department_name": row["department_name"] or None,
            "aliases": aliases_by_code.get((row["code"] or "").upper(), []) if row["code"] else [],
            "postings": int(row["postings"]),
        }
        for row in rows
    ]


def _agency_aliases(conn: sqlite3.Connection) -> dict[str, list[str]]:
    if not _table_exists(conn, "code_lists"):
        return {}
    rows = conn.execute(
        """
        SELECT UPPER(TRIM(code)) AS alias, UPPER(TRIM(label)) AS canonical_code
        FROM code_lists
        WHERE list_name='agency_aliases'
          AND TRIM(COALESCE(code, '')) <> ''
          AND TRIM(COALESCE(label, '')) <> ''
        ORDER BY alias
        """
    ).fetchall()
    aliases: dict[str, list[str]] = {}
    for row in rows:
        canonical = row["canonical_code"]
        alias = row["alias"]
        if canonical == alias:
            continue
        bucket = aliases.setdefault(canonical, [])
        if alias not in bucket:
            bucket.append(alias)
    return aliases


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
    """Counts of source-coord, city, state-centroid, and unmatched rows.

    Per ADR-0019 the public map prefers source-published coordinates
    (``job_locations.latitude/longitude`` from the USAJOBS Search payload)
    over geocoded fallbacks. ``source`` is the high-confidence count;
    ``city_matches`` and ``state_matches`` are SimpleMaps fallbacks.
    """
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN jl.latitude IS NOT NULL THEN 1 ELSE 0 END) AS source_coords,
            SUM(CASE WHEN jl.latitude IS NULL AND city_lookup.lat IS NOT NULL THEN 1 ELSE 0 END) AS city_matches,
            SUM(CASE
                    WHEN jl.latitude IS NULL
                     AND city_lookup.lat IS NULL
                     AND state_lookup.lat IS NOT NULL THEN 1 ELSE 0 END) AS state_matches,
            SUM(CASE
                    WHEN jl.latitude IS NULL
                     AND city_lookup.lat IS NULL
                     AND state_lookup.lat IS NULL THEN 1 ELSE 0 END) AS unmatched,
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
        "source_coords": int(row["source_coords"] or 0),
        "city_matches": int(row["city_matches"] or 0),
        "state_matches": int(row["state_matches"] or 0),
        "unmatched": int(row["unmatched"] or 0),
        "total": int(row["total"] or 0),
    }


def data_sources_freshness(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Per-source freshness map for the public site footer.

    Reads ``data_source_status`` (populated by ``src/data_source_registry``).
    Returns a dict keyed by ``source_key`` so the SvelteKit client can show
    a line like "Pay tables: refreshed 2026-01-15".
    """
    if not _table_exists(conn, "data_source_status"):
        return {}
    rows = conn.execute(
        """
        SELECT source_key, display_name, category, last_run_at, last_success_at,
               last_error, row_count, manual_override
        FROM data_source_status
        ORDER BY category, display_name
        """
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (row["source_key"] or "").strip()
        if not key:
            continue
        out[key] = {
            "display_name": row["display_name"],
            "category": row["category"],
            "last_run_at": row["last_run_at"],
            "last_success_at": row["last_success_at"],
            "row_count": row["row_count"],
            "manual_override": bool(row["manual_override"] or 0),
            "has_error": bool(row["last_error"]),
        }
    return out


def posting_coverage_summary(
    conn: sqlite3.Connection,
    *,
    job_count: int,
    feature_count: int,
) -> dict[str, Any]:
    """Return counts that explain public-map posting coverage.

    The public map is a static export of whatever USAJOBS rows are present in
    the local SQLite database. These diagnostics make that boundary explicit so
    a small seeded/sample corpus is not mistaken for the full live USAJOBS
    inventory.
    """
    counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_usajobs_jobs,
            SUM(CASE WHEN j.source = 'usajobs_search' THEN 1 ELSE 0 END) AS total_current_search_jobs,
            SUM(CASE WHEN j.source = 'usajobs_historic' THEN 1 ELSE 0 END) AS total_historic_jobs,
            SUM(CASE
                WHEN (j.close_date IS NULL OR j.close_date >= date('now'))
                 AND COALESCE(j.url, '') <> ''
                THEN 1 ELSE 0 END) AS open_usajobs_jobs,
            SUM(CASE
                WHEN j.source = 'usajobs_search'
                 AND (j.close_date IS NULL OR j.close_date >= date('now'))
                 AND COALESCE(j.url, '') <> ''
                THEN 1 ELSE 0 END) AS open_current_search_jobs,
            SUM(CASE
                WHEN j.source = 'usajobs_historic'
                 AND (j.close_date IS NULL OR j.close_date >= date('now'))
                 AND COALESCE(j.url, '') <> ''
                THEN 1 ELSE 0 END) AS open_historic_jobs
        FROM jobs j
        WHERE j.source LIKE 'usajobs%'
        """
    ).fetchone()
    latest_current = conn.execute(
        """
        SELECT completed_at, actual_records, pages_completed, filters_json
        FROM import_manifests
        WHERE source = 'usajobs_search'
          AND status = 'completed'
        ORDER BY completed_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    summary = {
        "scope": "local_static_snapshot",
        "live_usajobs_total": None,
        "job_count": int(job_count),
        "feature_count": int(feature_count),
        "total_usajobs_jobs_in_db": int(counts["total_usajobs_jobs"] or 0),
        "total_current_search_jobs_in_db": int(counts["total_current_search_jobs"] or 0),
        "total_historic_jobs_in_db": int(counts["total_historic_jobs"] or 0),
        "open_usajobs_jobs_in_db": int(counts["open_usajobs_jobs"] or 0),
        "open_current_search_jobs_in_db": int(counts["open_current_search_jobs"] or 0),
        "open_historic_jobs_in_db": int(counts["open_historic_jobs"] or 0),
        "last_current_import_completed_at": None,
        "last_current_import_records": None,
        "last_current_import_pages": None,
        "last_current_import_filters": None,
    }
    if latest_current is not None:
        summary.update(
            {
                "last_current_import_completed_at": latest_current["completed_at"],
                "last_current_import_records": latest_current["actual_records"],
                "last_current_import_pages": latest_current["pages_completed"],
                "last_current_import_filters": _safe_json(latest_current["filters_json"]),
            }
        )
    return summary


def _safe_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def manifest(
    conn: sqlite3.Connection,
    *,
    feature_count: int,
    job_count: int,
    opm_state_count: int,
    reference_year: int | None = None,
    layer_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_year": int(
            reference_year if reference_year is not None else current_reference_year(conn)
        ),
        "feature_count": feature_count,
        "job_count": job_count,
        "opm_state_count": opm_state_count,
        "opm_label": "federal workforce, not postings",
        "geocoding": geocoding_summary(conn),
        "layers": dict(layer_counts or {}),
        "data_sources": data_sources_freshness(conn),
        "posting_coverage": posting_coverage_summary(
            conn, job_count=job_count, feature_count=feature_count
        ),
    }


# ---------- Polygon emitters ------------------------------------------------


def states_geojson(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    year: int | None = None,
    tolerance: float | None = DEFAULT_STATE_TOLERANCE,
) -> dict[str, Any]:
    """FeatureCollection of US state polygons with joined dashboard metrics.

    Per-feature properties: ``state``, ``name``, ``postings`` (open USAJOBS
    count), ``workforce`` / ``accessions`` / ``separations`` (from
    ``opm_workforce_records``), ``gs13_step1_locality`` (illustrative pay for
    the state's most populated locality area — proxied as the locality with
    the most member counties in the state), ``rpp_overall`` from BEA, and
    ``pay_vs_col`` — a *purchasing-power index* where 100 = national-average
    purchasing power for a GS-13 step 1 employee. Values >100 mean the state's
    locality-adjusted pay outpaces its cost of living; <100 means it lags.
    """
    resolved_year = year if year is not None else current_reference_year(conn)
    markers = _marker_dataset(conn, year=resolved_year, repo_root=repo_root)
    postings_by_state = _count_by(markers, "state")
    opm_by_state = opm_state_aggregates(conn)
    rpp_by_state = _rpp_lookup(conn, geo_type="state")
    national_base_pay = _gs_base_step1_for_year(conn, resolved_year, grade="13")

    state_rows = conn.execute(
        "SELECT state, name, polygon_path FROM state_polygons ORDER BY state"
    ).fetchall()

    features: list[dict[str, Any]] = []
    for row in state_rows:
        state_code = (row["state"] or "").upper()
        if not state_code:
            continue
        geometry = _load_polygon(row["polygon_path"], repo_root)
        if geometry is None:
            continue
        if tolerance:
            geometry = simplify_geometry(geometry, tolerance)

        opm = opm_by_state.get(state_code, {})
        workforce = int(opm.get("employment", 0)) or None
        accessions = int(opm.get("accessions", 0)) or None
        separations = int(opm.get("separations", 0)) or None

        locality_code = _state_dominant_locality(conn, state=state_code, year=resolved_year)
        gs13_pay = _gs13_step1_for_locality(
            conn, locality_code=locality_code, year=resolved_year
        )
        rpp = rpp_by_state.get(state_code)
        pay_vs_col = _pay_vs_col(gs13_pay, rpp, national_pay=national_base_pay)

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "state": state_code,
                    "name": row["name"],
                    "postings": int(postings_by_state.get(state_code, 0)),
                    "workforce": workforce,
                    "accessions": accessions,
                    "separations": separations,
                    "locality_code": locality_code,
                    "gs13_step1_locality": gs13_pay,
                    "rpp_overall": rpp,
                    "pay_vs_col": pay_vs_col,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def localities_geojson(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    year: int | None = None,
    tolerance: float | None = DEFAULT_LOCALITY_TOLERANCE,
) -> dict[str, Any]:
    """FeatureCollection of OPM locality pay areas for ``year``.

    RPP is averaged across constituent metros and labeled approximate per
    `docs/PUBLIC_MAP_DATA_SOURCES.md` — BEA does not publish RPP at the
    locality-pay-area level.
    """
    resolved_year = year if year is not None else current_reference_year(conn)
    markers = _marker_dataset(conn, year=resolved_year, repo_root=repo_root)
    postings_by_locality = _count_by(markers, "locality_code")
    rpp_by_cbsa = _rpp_lookup(conn, geo_type="cbsa")

    locality_rows = conn.execute(
        """
        SELECT code, year, name, adjustment_pct, polygon_path
        FROM locality_pay_areas
        WHERE year = ?
        ORDER BY code
        """,
        (resolved_year,),
    ).fetchall()

    features: list[dict[str, Any]] = []
    for row in locality_rows:
        code = (row["code"] or "").upper()
        if not code:
            continue
        county_fips = _locality_county_fips(conn, locality_code=code, year=resolved_year)
        county_count = len(county_fips)
        cbsa_codes = _cbsa_codes_for_counties(conn, county_fips)
        rpp_values = [v for v in (rpp_by_cbsa.get(c) for c in cbsa_codes) if v is not None]
        rpp_avg = round(sum(rpp_values) / len(rpp_values), 2) if rpp_values else None

        gs13_pay = _gs13_step1_for_locality(
            conn, locality_code=code, year=resolved_year
        )

        geometry = _load_polygon(row["polygon_path"], repo_root)
        if geometry is None:
            # Localities without polygons (e.g. Rest of U.S.) still belong in
            # the bundle so the client can render their popup metadata when
            # the user clicks a county that maps to them; emit a null geom.
            continue
        if tolerance:
            geometry = simplify_geometry(geometry, tolerance)

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "code": code,
                    "name": row["name"],
                    "adjustment_pct": _round_or_none(row["adjustment_pct"]),
                    "county_count": county_count,
                    "gs13_step1_locality": gs13_pay,
                    "rpp_overall": rpp_avg,
                    "rpp_overall_approximate": rpp_avg is not None,
                    "postings": int(postings_by_locality.get(code, 0)),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def counties_geojson(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    year: int | None = None,
    tolerance: float | None = DEFAULT_COUNTY_TOLERANCE,
) -> dict[str, Any]:
    """FeatureCollection of US counties with locality + RPP context.

    ``locality_code`` is joined via ``locality_pay_counties`` for ``year``.
    ``rpp_overall`` is the state-level fallback (BEA does not publish county-
    level RPP). ``postings`` counts markers whose geocoded county matches.
    """
    resolved_year = year if year is not None else current_reference_year(conn)
    markers = _marker_dataset(conn, year=resolved_year)
    postings_by_county = _count_by(markers, "county_fips")
    rpp_by_state = _rpp_lookup(conn, geo_type="state")

    rows = conn.execute(
        """
        SELECT c.fips, c.name, c.state, c.cbsa_code, c.polygon_path,
               lpc.locality_code AS locality_code
        FROM counties c
        LEFT JOIN locality_pay_counties lpc
            ON lpc.county_fips = c.fips AND lpc.year = ?
        ORDER BY c.fips
        """,
        (resolved_year,),
    ).fetchall()

    features: list[dict[str, Any]] = []
    for row in rows:
        fips = (row["fips"] or "").strip()
        if not fips:
            continue
        geometry = _load_polygon(row["polygon_path"], repo_root)
        if geometry is None:
            continue
        if tolerance:
            geometry = simplify_geometry(geometry, tolerance)
        state_code = (row["state"] or "").upper() or None
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "fips": fips,
                    "name": row["name"],
                    "state": state_code,
                    "cbsa_code": row["cbsa_code"],
                    "locality_code": row["locality_code"],
                    "rpp_overall": rpp_by_state.get(state_code) if state_code else None,
                    "postings": int(postings_by_county.get(fips, 0)),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def metros_geojson(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    year: int | None = None,
    tolerance: float | None = DEFAULT_METRO_TOLERANCE,
) -> dict[str, Any]:
    """FeatureCollection of CBSA polygons with RPP and postings counts."""
    resolved_year = year if year is not None else current_reference_year(conn)
    markers = _marker_dataset(conn, year=resolved_year)
    postings_by_cbsa = _count_by(markers, "cbsa_code")
    rpp_by_cbsa = _rpp_lookup(conn, geo_type="cbsa")

    rows = conn.execute(
        """
        SELECT cbsa_code, name, cbsa_type, polygon_path
        FROM metro_areas
        ORDER BY cbsa_code
        """
    ).fetchall()

    features: list[dict[str, Any]] = []
    for row in rows:
        cbsa = (row["cbsa_code"] or "").strip()
        if not cbsa:
            continue
        geometry = _load_polygon(row["polygon_path"], repo_root)
        if geometry is None:
            continue
        if tolerance:
            geometry = simplify_geometry(geometry, tolerance)
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "cbsa_code": cbsa,
                    "name": row["name"],
                    "cbsa_type": row["cbsa_type"],
                    "rpp_overall": rpp_by_cbsa.get(cbsa),
                    "postings": int(postings_by_cbsa.get(cbsa, 0)),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


# ---------- Pay tables and cost of living -----------------------------------


def pay_tables(conn: sqlite3.Connection) -> dict[str, Any]:
    """Every ``pay_scales`` row organized for client-side lookup.

    Shape::

        {
            "GS": {
                "2026": {
                    "BASE": { "13": { "1": 96148.0, ... } },
                    "CHI":  { "13": { "1": 110803.0, ... } }
                }
            }
        }

    The ``BASE`` key collects rows where ``locality_code = ''`` (the no-
    locality sentinel used by the schema). Step ``0`` represents pay plans
    without steps (single-rate plans like ES).
    """
    rows = conn.execute(
        """
        SELECT pay_plan, year, grade, step, locality_code, annual_rate
        FROM pay_scales
        ORDER BY pay_plan, year, locality_code, grade, step
        """
    ).fetchall()
    out: dict[str, Any] = {}
    for row in rows:
        plan = (row["pay_plan"] or "").upper()
        if not plan:
            continue
        year = str(int(row["year"]))
        loc = (row["locality_code"] or "").upper() or "BASE"
        grade = str(row["grade"])
        step = str(int(row["step"]))
        plan_node = out.setdefault(plan, {})
        year_node = plan_node.setdefault(year, {})
        loc_node = year_node.setdefault(loc, {})
        grade_node = loc_node.setdefault(grade, {})
        try:
            grade_node[step] = round(float(row["annual_rate"]), 2)
        except (TypeError, ValueError):
            continue
    return out


def cost_of_living(conn: sqlite3.Connection) -> dict[str, Any]:
    """``{by_state, by_cbsa}`` keyed by code with the latest-year RPP row.

    Latest year is computed per geography so a state with stale data still
    surfaces alongside a cbsa with newer data; the returned row carries its
    ``year`` so the client can label it.
    """
    rows = conn.execute(
        """
        SELECT year, geo_type, geo_code, rpp_overall, rpp_goods, rpp_services,
               rpp_rents, source
        FROM cost_of_living_index
        ORDER BY geo_type, geo_code,
                 CASE source WHEN 'bea:rpp' THEN 0 ELSE 1 END,
                 year DESC
        """
    ).fetchall()
    by_state: dict[str, Any] = {}
    by_cbsa: dict[str, Any] = {}
    for row in rows:
        bucket = by_state if row["geo_type"] == "state" else by_cbsa
        code = (row["geo_code"] or "").strip()
        if not code or code in bucket:
            continue
        bucket[code] = {
            "year": int(row["year"]),
            "rpp_overall": _round_or_none(row["rpp_overall"]),
            "rpp_goods": _round_or_none(row["rpp_goods"]),
            "rpp_services": _round_or_none(row["rpp_services"]),
            "rpp_rents": _round_or_none(row["rpp_rents"]),
            "source": row["source"],
        }
    return {"by_state": by_state, "by_cbsa": by_cbsa}


def zip_centroids_payload(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return static ZIP/ZCTA centroids for offline ZIP search."""
    if not _table_exists(conn, "zip_centroids"):
        return []
    rows = conn.execute(
        """
        SELECT zip, lat, lon, city, state, county_fips
        FROM zip_centroids
        ORDER BY zip
        """
    ).fetchall()
    payload: list[dict[str, Any]] = []
    for row in rows:
        if row["lat"] is None or row["lon"] is None:
            continue
        payload.append(
            {
                "zip": str(row["zip"]).zfill(5),
                "lat": round(float(row["lat"]), 5),
                "lon": round(float(row["lon"]), 5),
                "city": row["city"] or None,
                "state": (row["state"] or "").upper() or None,
                "county_fips": row["county_fips"] or None,
            }
        )
    return payload


# ---------- Reference-year + lookup helpers ---------------------------------


def current_reference_year(conn: sqlite3.Connection) -> int:
    """Pick the most recent year present in any reference-data table.

    Order of preference: ``pay_scales`` (the table we care most about for
    pay tables), then ``locality_pay_areas``. Falls back to the current
    calendar year so the rest of the export still runs even before any
    ingest has populated reference data.
    """
    for table in ("pay_scales", "locality_pay_areas"):
        if not _table_exists(conn, table):
            continue
        row = conn.execute(f"SELECT MAX(year) AS y FROM {table}").fetchone()
        if row and row["y"] is not None:
            return int(row["y"])
    return datetime.now(timezone.utc).year


def _count_by(markers: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for marker in markers:
        value = marker.get(key)
        if value is None or value == "":
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _rpp_lookup(
    conn: sqlite3.Connection, *, geo_type: str
) -> dict[str, float]:
    """Latest BEA RPP overall by ``geo_code`` for the given ``geo_type``.

    Picks the highest year per code and prefers ``bea:rpp`` when multiple
    sources publish the same year.
    """
    rows = conn.execute(
        """
        SELECT year, geo_code, rpp_overall, source
        FROM cost_of_living_index
        WHERE geo_type = ? AND rpp_overall IS NOT NULL
        ORDER BY geo_code,
                 CASE source WHEN 'bea:rpp' THEN 0 ELSE 1 END,
                 year DESC
        """,
        (geo_type,),
    ).fetchall()
    out: dict[str, float] = {}
    for row in rows:
        code = (row["geo_code"] or "").strip()
        if not code or code in out:
            continue
        try:
            out[code] = round(float(row["rpp_overall"]), 2)
        except (TypeError, ValueError):
            continue
    return out


def _state_dominant_locality(
    conn: sqlite3.Connection, *, state: str, year: int
) -> str:
    """Pick the locality area covering the most counties in ``state``.

    Used as a proxy for "most populated locality" since we don't ship
    population data with the dashboard. Falls back to ``REST_OF_US_CODE``
    when no locality has any counties in the state.
    """
    state_code = (state or "").upper()
    if not state_code:
        return REST_OF_US_CODE
    row = conn.execute(
        """
        SELECT lpc.locality_code AS code, COUNT(*) AS cnt
        FROM locality_pay_counties lpc
        JOIN counties c ON c.fips = lpc.county_fips
        WHERE lpc.year = ? AND c.state = ? AND lpc.locality_code <> ?
        GROUP BY lpc.locality_code
        ORDER BY cnt DESC, lpc.locality_code
        LIMIT 1
        """,
        (year, state_code, REST_OF_US_CODE),
    ).fetchone()
    if row and row["code"]:
        return str(row["code"]).upper()
    return REST_OF_US_CODE


def _gs13_step1_for_locality(
    conn: sqlite3.Connection, *, locality_code: str, year: int
) -> float | None:
    """Locality-adjusted GS-13 step 1 rate for choropleth pay-vs-COL.

    Honors the same precedence as ``src.pay_calculator``:
    1. A locality-specific row in ``pay_scales`` for (GS, year, 13, 1, code).
    2. The base row × (1 + adjustment_pct) when only a base table is loaded.

    Working directly off ``locality_code`` (rather than reverse-resolving a
    city/state) lets us produce a pay number for every state at choropleth
    time without depending on each county name appearing in
    ``locations_geocoded``.
    """
    code = (locality_code or "").upper()
    locality_row = conn.execute(
        """
        SELECT annual_rate FROM pay_scales
        WHERE pay_plan='GS' AND year=? AND grade='13' AND step=1
              AND locality_code=?
        """,
        (year, code),
    ).fetchone()
    if locality_row and locality_row["annual_rate"] is not None:
        return _round_or_none(locality_row["annual_rate"])

    base_row = conn.execute(
        """
        SELECT annual_rate FROM pay_scales
        WHERE pay_plan='GS' AND year=? AND grade='13' AND step=1
              AND locality_code=''
        """,
        (year,),
    ).fetchone()
    if not base_row or base_row["annual_rate"] is None:
        return None

    adjustment_row = conn.execute(
        "SELECT adjustment_pct FROM locality_pay_areas WHERE code=? AND year=?",
        (code, year),
    ).fetchone()
    adjustment = (
        float(adjustment_row["adjustment_pct"])
        if adjustment_row and adjustment_row["adjustment_pct"] is not None
        else 0.0
    )
    rate = float(base_row["annual_rate"]) * (1 + adjustment / 100.0)
    return round(rate, 2)


def _pay_vs_col(
    pay: float | None,
    rpp: float | None,
    *,
    national_pay: float | None = None,
) -> float | None:
    """Return a purchasing-power index where 100 = national-average purchasing power.

    Formula: ``(pay / national_pay) / (rpp / 100) * 100``. Both numerator and
    denominator are normalized: pay is divided by the national reference (GS-13
    step 1 base for the same year); RPP is divided by 100 so 100 = US average.
    The product is multiplied by 100 to express the result as an index.

    >100 → locality pay outpaces COL relative to the national average.
    <100 → locality pay lags COL.

    When ``national_pay`` is not provided (legacy callers / tests), falls back
    to the previous formula ``pay / rpp * 100`` so existing tests keep passing.
    """
    if pay is None or rpp is None or rpp <= 0:
        return None
    if national_pay is None or national_pay <= 0:
        return round((pay / rpp) * 100.0, 2)
    return round((pay / national_pay) / (rpp / 100.0) * 100.0, 2)


def _gs_base_step1_for_year(
    conn: sqlite3.Connection, year: int, *, grade: str = "13"
) -> float | None:
    """National (locality_code='') GS step-1 base rate for ``grade`` in ``year``.

    Used as the reference pay when computing the pay-vs-COL index so each
    state's purchasing-power score is comparable across the country.
    """
    row = conn.execute(
        """
        SELECT annual_rate FROM pay_scales
        WHERE pay_plan='GS' AND year=? AND grade=? AND step=1
              AND locality_code=''
        """,
        (year, grade),
    ).fetchone()
    if row and row["annual_rate"] is not None:
        return _round_or_none(row["annual_rate"])
    return None


def _locality_county_fips(
    conn: sqlite3.Connection, *, locality_code: str, year: int
) -> list[str]:
    rows = conn.execute(
        """
        SELECT county_fips FROM locality_pay_counties
        WHERE locality_code = ? AND year = ?
        """,
        (locality_code, year),
    ).fetchall()
    return [row["county_fips"] for row in rows if row["county_fips"]]


def _cbsa_codes_for_counties(
    conn: sqlite3.Connection, county_fips: list[str]
) -> list[str]:
    if not county_fips:
        return []
    placeholders = ",".join("?" for _ in county_fips)
    rows = conn.execute(
        f"SELECT DISTINCT cbsa_code FROM counties WHERE fips IN ({placeholders})",
        county_fips,
    ).fetchall()
    return [row["cbsa_code"] for row in rows if row["cbsa_code"]]


# ---------- Polygon I/O + simplification -----------------------------------


def _resolve_polygon_path(polygon_path: str | None, repo_root: Path) -> Path | None:
    if not polygon_path:
        return None
    p = Path(polygon_path)
    if not p.is_absolute():
        p = repo_root / p
    return p


def _load_polygon(polygon_path: str | None, repo_root: Path) -> dict[str, Any] | None:
    """Read a stored polygon file and return its geometry dict.

    Returns ``None`` if the path is missing, the file does not exist, or the
    file is malformed. Logs a warning so the export still proceeds even when
    one polygon is broken.
    """
    resolved = _resolve_polygon_path(polygon_path, repo_root)
    if resolved is None or not resolved.exists():
        if polygon_path:
            logger.warning("polygon file not found: %s", polygon_path)
        return None
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read polygon %s: %s", resolved, exc)
        return None
    if isinstance(data, dict) and data.get("type") == "Feature":
        return data.get("geometry")
    if isinstance(data, dict) and data.get("type") in {"Polygon", "MultiPolygon"}:
        return data
    return None


def _locality_point_lookup(
    conn: sqlite3.Connection, *, year: int, repo_root: Path | None
) -> Callable[[float, float], str | None]:
    if repo_root is None:
        return lambda _lon, _lat: None

    rows = conn.execute(
        """
        SELECT code, polygon_path
        FROM locality_pay_areas
        WHERE year = ? AND COALESCE(code, '') <> ''
        ORDER BY code
        """,
        (int(year),),
    ).fetchall()
    candidates: list[tuple[str, dict[str, Any], tuple[float, float, float, float]]] = []
    for row in rows:
        geometry = _load_polygon(row["polygon_path"], repo_root)
        bounds = _geometry_bounds(geometry)
        if geometry is None or bounds is None:
            continue
        candidates.append((str(row["code"]).upper(), geometry, bounds))

    def lookup(lon: float, lat: float) -> str | None:
        for code, geometry, bounds in candidates:
            min_lon, min_lat, max_lon, max_lat = bounds
            if lon < min_lon or lon > max_lon or lat < min_lat or lat > max_lat:
                continue
            if _point_in_geometry(lon, lat, geometry):
                return code
        return None

    return lookup


def _geometry_bounds(geometry: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not geometry:
        return None
    points: list[list[float]] = []
    _collect_geometry_points(geometry.get("coordinates"), points)
    if not points:
        return None
    lons = [float(point[0]) for point in points]
    lats = [float(point[1]) for point in points]
    return min(lons), min(lats), max(lons), max(lats)


def _collect_geometry_points(value: Any, points: list[list[float]]) -> None:
    if not isinstance(value, list):
        return
    if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
        points.append(value)
        return
    for item in value:
        _collect_geometry_points(item, points)


def _point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    g_type = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if g_type == "Polygon":
        return _point_in_polygon(lon, lat, coords)
    if g_type == "MultiPolygon":
        return any(_point_in_polygon(lon, lat, poly) for poly in coords)
    return False


def _point_in_polygon(lon: float, lat: float, rings: list[list[list[float]]]) -> bool:
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    return not any(_point_in_ring(lon, lat, hole) for hole in rings[1:])


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    if len(ring) < 4:
        return inside
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        if (yi > lat) != (yj > lat):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_intersect:
                inside = not inside
        j = i
    return inside


def simplify_geometry(
    geometry: dict[str, Any] | None, tolerance: float
) -> dict[str, Any] | None:
    """Stdlib Douglas-Peucker simplification for Polygon / MultiPolygon.

    Tolerance is in degrees. Endpoints (and therefore closed-ring closure)
    are always preserved. ADR-0017 calls for simplified geometry at export
    time so the public bundle stays small even though the dashboard stores
    full TIGER detail on disk.
    """
    if not geometry or tolerance <= 0:
        return geometry
    g_type = geometry.get("type")
    if g_type == "Polygon":
        rings = geometry.get("coordinates") or []
        return {
            "type": "Polygon",
            "coordinates": [_simplify_ring(ring, tolerance) for ring in rings],
        }
    if g_type == "MultiPolygon":
        polys = geometry.get("coordinates") or []
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [_simplify_ring(ring, tolerance) for ring in poly]
                for poly in polys
            ],
        }
    return geometry


def _simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(ring) < 4:
        return ring
    simplified = _douglas_peucker(ring, tolerance)
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def _douglas_peucker(
    points: list[list[float]], tolerance: float
) -> list[list[float]]:
    if len(points) < 3:
        return list(points)
    # Iterative implementation to avoid recursion depth issues on long rings.
    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True
    stack: list[tuple[int, int]] = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        max_dist = 0.0
        max_idx = first
        for i in range(first + 1, last):
            d = _perpendicular_distance(points[i], points[first], points[last])
            if d > max_dist:
                max_dist = d
                max_idx = i
        if max_dist > tolerance:
            keep[max_idx] = True
            stack.append((first, max_idx))
            stack.append((max_idx, last))
    return [points[i] for i in range(len(points)) if keep[i]]


def _perpendicular_distance(
    point: list[float], start: list[float], end: list[float]
) -> float:
    sx, sy = start[0], start[1]
    ex, ey = end[0], end[1]
    px, py = point[0], point[1]
    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
    num = abs(dy * px - dx * py + ex * sy - ey * sx)
    den = (dx * dx + dy * dy) ** 0.5
    return num / den


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
