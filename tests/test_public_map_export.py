from __future__ import annotations

import sqlite3

import pytest

from src.database import (
    connect,
    init_schema,
    record_geocoding_miss,
    upsert_geocoded_location,
    upsert_job,
    upsert_zip_centroid,
    utc_now,
)
from src.public_map_export import (
    agency_options,
    closed_jobs_geojson,
    current_reference_year,
    geocoding_summary,
    job_details,
    jobs_geojson,
    manifest,
    opm_state_aggregates,
    posting_coverage_summary,
    series_options,
    zip_centroids_payload,
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
        "usajobs_control_number": "100000001",
        "position_id": "FEMA-OPEN-001",
        "announcement_number": "FEMA-OPEN-001",
        "title": "Emergency Management Specialist",
        "department": "Department of Homeland Security",
        "agency": "Federal Emergency Management Agency",
        "agency_code": "HSCB",
        "department_code": "HS",
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
        "open_date": "2026-04-01",
        "close_date": "2099-12-31",
        "url": "https://www.usajobs.gov/job/100000001",
        "source_endpoint": "/api/historicjoa",
        "locations": [{"city": "Chicago", "state": "IL", "location_text": "Chicago, Illinois"}],
    }
    base.update(overrides)
    return base


def _seed_chicago(conn):
    upsert_geocoded_location(
        conn,
        city="Chicago",
        state="IL",
        lat=41.8781,
        lon=-87.6298,
        county_fips="17031",
    )


def test_init_schema_seeds_state_centroids(conn):
    row = conn.execute(
        "SELECT lat, lon, geo_quality FROM locations_geocoded WHERE city='' AND state='IL'"
    ).fetchone()
    assert row is not None
    assert row["geo_quality"] == "state_centroid"
    assert row["lat"] is not None
    assert row["lon"] is not None


def test_jobs_geojson_prefers_job_locations_lat_lon_over_geocoded(conn):
    # Seed BOTH a city geocode and a source coord; verify the source coord wins.
    _seed_chicago(conn)
    upsert_job(
        conn,
        _job(
            locations=[
                {
                    "city": "Chicago",
                    "state": "IL",
                    "location_text": "Chicago, IL",
                    # USAJOBS Search payload coordinates (more precise than city centroid)
                    "latitude": 41.8500,
                    "longitude": -87.6500,
                }
            ],
        ),
    )

    feature = jobs_geojson(conn)["features"][0]
    lon, lat = feature["geometry"]["coordinates"]
    assert lat == 41.85
    assert lon == -87.65
    assert feature["properties"]["geo_quality"] == "source"


def test_geocoding_summary_counts_source_coords_separately(conn):
    _seed_chicago(conn)
    # Job 1: source coords
    upsert_job(
        conn,
        _job(
            locations=[{
                "city": "Chicago", "state": "IL",
                "latitude": 41.85, "longitude": -87.65,
            }],
        ),
    )
    # Job 2: city geocode fallback (no source coords)
    upsert_job(
        conn,
        _job(
            position_id="JOB-2",
            announcement_number="JOB-2",
            usajobs_control_number="100000099",
            locations=[{"city": "Chicago", "state": "IL"}],
        ),
    )

    summary = geocoding_summary(conn)
    assert summary["source_coords"] == 1
    assert summary["city_matches"] == 1
    assert summary["state_matches"] == 0


def test_jobs_geojson_uses_city_match_when_available(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job())

    geo = jobs_geojson(conn)
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == 1
    feature = geo["features"][0]
    lon, lat = feature["geometry"]["coordinates"]
    assert pytest.approx(lat, abs=0.01) == 41.88
    assert pytest.approx(lon, abs=0.01) == -87.63
    assert feature["properties"]["geo_quality"] == "city"
    assert feature["properties"]["agency_code"] == "HSCB"
    assert feature["properties"]["state"] == "IL"


def test_jobs_geojson_falls_back_to_state_centroid(conn):
    upsert_job(
        conn,
        _job(
            position_id="UNKNOWN-CITY",
            announcement_number="UNKNOWN-CITY",
            usajobs_control_number="100000002",
            city="Nowheresville",
            location_text="Nowheresville, Illinois",
            locations=[
                {"city": "Nowheresville", "state": "IL", "location_text": "Nowheresville, Illinois"}
            ],
        ),
    )

    features = jobs_geojson(conn)["features"]
    assert len(features) == 1
    assert features[0]["properties"]["geo_quality"] == "state_centroid"


def test_jobs_geojson_excludes_closed_postings(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job(close_date="2020-01-01"))

    assert jobs_geojson(conn)["features"] == []


def test_closed_jobs_geojson_includes_recently_closed_postings(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job(close_date="2026-04-15"))

    features = closed_jobs_geojson(conn, trailing_days=90)["features"]
    assert len(features) == 1
    props = features[0]["properties"]
    assert props["status"] == "closed"
    assert props["close_date"] == "2026-04-15"
    assert props["closed_within_days"] >= 0


def test_closed_jobs_geojson_excludes_old_closed_postings(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job(close_date="2020-01-01"))

    assert closed_jobs_geojson(conn, trailing_days=90)["features"] == []


def test_jobs_geojson_includes_postings_with_no_close_date(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job(close_date=None))

    assert len(jobs_geojson(conn)["features"]) == 1


def test_jobs_geojson_skips_locations_without_a_state(conn):
    upsert_job(
        conn,
        _job(
            state=None,
            city=None,
            location_text="Overseas",
            locations=[{"city": None, "state": None, "location_text": "Overseas"}],
        ),
    )

    assert jobs_geojson(conn)["features"] == []


def test_job_details_groups_locations_by_job(conn):
    _seed_chicago(conn)
    upsert_geocoded_location(conn, city="Denton", state="TX", lat=33.2148, lon=-97.1331)
    upsert_job(
        conn,
        _job(
            locations=[
                {"city": "Chicago", "state": "IL", "location_text": "Chicago, IL"},
                {"city": "Denton", "state": "TX", "location_text": "Denton, TX"},
            ]
        ),
    )

    details = job_details(conn)
    assert len(details) == 1
    only = next(iter(details.values()))
    assert only["url"] == "https://www.usajobs.gov/job/100000001"
    states = sorted(loc["state"] for loc in only["locations"])
    assert states == ["IL", "TX"]


def test_opm_state_aggregates_handles_missing_records(conn):
    assert opm_state_aggregates(conn) == {}


def test_opm_state_aggregates_sums_by_state(conn):
    conn.execute(
        """
        INSERT INTO opm_workforce_records (
            dataset, location_state, employment_count, accessions_count, separations_count
        ) VALUES
        ('fedscope', 'IL', 1000, 50, 30),
        ('fedscope', 'IL',  500, 25, 15),
        ('fedscope', 'TX', 2000, 80, 40),
        ('fedscope', '  ', 9999, 0, 0)
        """
    )
    conn.commit()

    aggregates = opm_state_aggregates(conn)
    assert aggregates["IL"] == {"employment": 1500, "accessions": 75, "separations": 45}
    assert aggregates["TX"] == {"employment": 2000, "accessions": 80, "separations": 40}
    assert "  " not in aggregates


def test_agency_and_series_options_sorted_by_postings(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job())
    upsert_job(
        conn,
        _job(
            position_id="FEMA-OPEN-002",
            announcement_number="FEMA-OPEN-002",
            usajobs_control_number="100000003",
            agency="National Park Service",
            agency_code="IN15",
            series="0025",
        ),
    )
    upsert_job(
        conn,
        _job(
            position_id="FEMA-OPEN-003",
            announcement_number="FEMA-OPEN-003",
            usajobs_control_number="100000004",
            series="0089",
        ),
    )

    agencies = agency_options(conn)
    assert agencies[0]["code"] == "HSCB"
    assert agencies[0]["name"] == "Federal Emergency Management Agency"
    assert agencies[0]["aliases"] == ["FEDERAL EMERGENCY MANAGEMENT AGENCY", "FEMA"]
    assert agencies[0]["postings"] == 2

    series = series_options(conn)
    assert series[0]["code"] == "0089"
    assert series[0]["postings"] == 2


def test_manifest_records_geocoding_summary_and_opm_label(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job())
    upsert_job(
        conn,
        _job(
            position_id="MISSING-CITY",
            announcement_number="MISSING-CITY",
            usajobs_control_number="100000099",
            city="Atlantis",
            location_text="Atlantis, IL",
            locations=[{"city": "Atlantis", "state": "IL", "location_text": "Atlantis, IL"}],
        ),
    )

    summary = geocoding_summary(conn)
    assert summary["city_matches"] == 1
    assert summary["state_matches"] == 1
    assert summary["unmatched"] == 0
    assert summary["total"] == 2

    man = manifest(conn, feature_count=2, job_count=2, opm_state_count=0)
    assert man["opm_label"] == "federal workforce, not postings"
    assert man["schema_version"] == 2
    assert "generated_at" in man
    assert "reference_year" in man
    assert "layers" in man
    assert "data_sources" in man
    assert man["posting_coverage"]["scope"] == "local_static_snapshot"
    assert man["posting_coverage"]["job_count"] == 2


def test_posting_coverage_summary_explains_local_snapshot_scope(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job(source="usajobs_search", source_endpoint="/api/Search"))
    upsert_job(
        conn,
        _job(
            source="usajobs_historic",
            position_id="HIST-OPEN",
            announcement_number="HIST-OPEN",
            usajobs_control_number="100000088",
        ),
    )
    conn.execute(
        """
        INSERT INTO import_manifests (
            source, endpoint, download_mode, filters_json, actual_records,
            pages_completed, status, started_at, completed_at
        ) VALUES (
            'usajobs_search', '/api/Search', 'FULL_DOWNLOAD',
            '{"ResultsPerPage": 500}', 1, 1, 'completed',
            '2026-05-08T12:00:00+00:00', '2026-05-08T12:01:00+00:00'
        )
        """
    )
    conn.commit()

    summary = posting_coverage_summary(conn, job_count=2, feature_count=2)

    assert summary["scope"] == "local_static_snapshot"
    assert summary["live_usajobs_total"] is None
    assert summary["open_usajobs_jobs_in_db"] == 2
    assert summary["open_current_search_jobs_in_db"] == 1
    assert summary["open_historic_jobs_in_db"] == 1
    assert summary["last_current_import_records"] == 1
    assert summary["last_current_import_pages"] == 1
    assert summary["last_current_import_filters"] == {"ResultsPerPage": 500}


def test_record_geocoding_miss_dedupes(conn):
    record_geocoding_miss(conn, city="Atlantis", state="IL", location_text="Atlantis, IL")
    record_geocoding_miss(conn, city="Atlantis", state="IL", location_text="Atlantis, IL")

    row = conn.execute(
        "SELECT seen_count FROM geocoding_misses WHERE city='atlantis' AND state='IL'"
    ).fetchone()
    assert row["seen_count"] == 2


def test_zip_centroids_payload_exports_static_lookup(conn):
    upsert_zip_centroid(
        conn,
        zip_code="60601",
        lat=41.88531,
        lon=-87.62164,
        city="Chicago",
        state="IL",
        county_fips="17031",
        source="test",
    )

    assert zip_centroids_payload(conn) == [
        {
            "zip": "60601",
            "lat": 41.88531,
            "lon": -87.62164,
            "city": "Chicago",
            "state": "IL",
            "county_fips": "17031",
        }
    ]


# ---------- D.5.11: per-job pay_grid + status flag --------------------------


def _seed_locality(conn, *, code, year, name, adjustment_pct, counties):
    now = utc_now()
    conn.execute(
        """
        INSERT INTO locality_pay_areas (
            code, year, name, description, adjustment_pct,
            polygon_path, source, source_url, imported_at
        ) VALUES (?, ?, ?, NULL, ?, NULL, 'test', NULL, ?)
        """,
        (code, year, name, adjustment_pct, now),
    )
    for fips in counties:
        conn.execute(
            """
            INSERT INTO locality_pay_counties (locality_code, year, county_fips, inclusion_type)
            VALUES (?, ?, ?, 'core')
            """,
            (code, year, fips),
        )
    conn.commit()


def _seed_pay_row(conn, *, pay_plan_code, year, grade, step, locality_code, rate):
    conn.execute(
        """
        INSERT INTO pay_scales (
            pay_plan, year, grade, step, locality_code,
            annual_rate, source, source_url, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'test', NULL, ?)
        """,
        (pay_plan_code, year, grade, step, locality_code, rate, utc_now()),
    )
    conn.commit()


def test_job_details_pay_grid_status_exact_when_locality_row_present(conn):
    _seed_chicago(conn)
    _seed_locality(
        conn, code="CHI", year=2026, name="Chicago-Naperville",
        adjustment_pct=32.45, counties=["17031"],
    )
    # Seed a locality-specific row for grade 12 step 1 — the calculator
    # should use it verbatim (status='exact').
    _seed_pay_row(
        conn, pay_plan_code="GS", year=2026, grade="12", step=1,
        locality_code="CHI", rate=110_803.00,
    )
    upsert_job(conn, _job())

    detail = next(iter(job_details(conn, year=2026).values()))

    grid = detail["pay_grid"]
    assert grid["status"] == "exact"
    assert grid["year"] == 2026
    assert grid["pay_plan"] == "GS"
    assert grid["locality"]["code"] == "CHI"
    assert grid["grades"]["12"]["01"] == 110_803.00


def test_job_details_pay_grid_status_approximated_when_only_base_row(conn):
    _seed_chicago(conn)
    _seed_locality(
        conn, code="CHI", year=2026, name="Chicago-Naperville",
        adjustment_pct=32.45, counties=["17031"],
    )
    # Only a base row — the calculator should derive base × (1 + pct).
    _seed_pay_row(
        conn, pay_plan_code="GS", year=2026, grade="12", step=1,
        locality_code="", rate=80_000.00,
    )
    upsert_job(conn, _job())

    detail = next(iter(job_details(conn, year=2026).values()))

    grid = detail["pay_grid"]
    assert grid["status"] == "approximated"
    # 80000 × (1 + 32.45/100) = 105960.00
    assert grid["grades"]["12"]["01"] == 105_960.00


def test_job_details_pay_grid_status_unavailable_when_no_rows(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job())

    detail = next(iter(job_details(conn, year=2026).values()))

    grid = detail["pay_grid"]
    assert grid["status"] == "unavailable"
    assert "missing_reason" in grid
    assert "pay_scales" in grid["missing_reason"].lower()


def test_job_details_pay_grid_unavailable_when_no_pay_plan(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job(pay_plan="", grade_low="", grade_high=""))

    detail = next(iter(job_details(conn, year=2026).values()))
    grid = detail["pay_grid"]
    assert grid["status"] == "unavailable"


def test_current_reference_year_prefers_pay_scales_max_year(conn):
    # Seed pay rows for 2024, 2025, 2026 — the resolver must pick 2026.
    for year in (2024, 2025, 2026):
        _seed_pay_row(
            conn, pay_plan_code="GS", year=year, grade="01", step=1,
            locality_code="", rate=20_000.00 + year,
        )
    assert current_reference_year(conn) == 2026
