from __future__ import annotations

import sqlite3

import pytest

from src.database import (
    connect,
    init_schema,
    record_geocoding_miss,
    replace_job_categories,
    upsert_geocoded_location,
    upsert_job,
    upsert_job_text,
    upsert_zip_centroid,
    utc_now,
)
from src.public_map_export import (
    EXCERPT_MAX_CHARS,
    _excerpt,
    historical_badges,
    agency_options,
    closed_jobs_geojson,
    current_reference_year,
    federal_properties_geojson,
    geocoding_summary,
    job_details,
    jobs_geojson,
    manifest,
    opm_state_aggregates,
    unmatched_locations,
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


def test_unmatched_locations_lists_only_ungeocodable_open_postings(conn):
    _seed_chicago(conn)
    # Job 1: city geocode resolves → NOT unmatched.
    upsert_job(conn, _job(locations=[{"city": "Chicago", "state": "IL"}]))
    # Job 2 + 3: an overseas station with no geocode and no source coords →
    # unmatched, and they share a location string so they group with count 2.
    for n in ("2", "3"):
        upsert_job(
            conn,
            _job(
                position_id=f"OVERSEAS-{n}",
                announcement_number=f"OVERSEAS-{n}",
                usajobs_control_number=f"20000000{n}",
                location_text="Ramstein, Germany",
                city="Ramstein",
                state="",
                locations=[{"city": "Ramstein", "state": "", "location_text": "Ramstein, Germany"}],
            ),
        )
    # Job 4: closed posting at an ungeocodable station → excluded (open only).
    upsert_job(
        conn,
        _job(
            position_id="CLOSED-1",
            announcement_number="CLOSED-1",
            usajobs_control_number="200000004",
            close_date="2000-01-01",
            location_text="Atlantis, XX",
            city="Atlantis",
            state="",
            locations=[{"city": "Atlantis", "state": "", "location_text": "Atlantis, XX"}],
        ),
    )

    rows = unmatched_locations(conn)
    locations = {r["location"]: r for r in rows}
    assert "Ramstein, Germany" in locations
    assert locations["Ramstein, Germany"]["posting_count"] == 2
    # The geocoded Chicago job and the closed posting are not listed.
    assert all("Chicago" not in r["location"] for r in rows)
    assert all("Atlantis" not in r["location"] for r in rows)
    # Sample context is populated for operator triage.
    assert locations["Ramstein, Germany"]["sample_control_number"]


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


def test_closed_jobs_geojson_carries_open_date_for_area_pulse(conn):
    # D.5.28: the client derives the trailing-90-day opening-rate baseline
    # from closed features' open_date — it must ride the overlay.
    _seed_chicago(conn)
    upsert_job(conn, _job(open_date="2026-03-01", close_date="2026-05-20"))
    features = closed_jobs_geojson(conn, trailing_days=9000)["features"]
    assert len(features) >= 1
    assert features[0]["properties"]["open_date"] == "2026-03-01"
    assert features[0]["properties"]["status"] == "closed"


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


def test_job_details_includes_locality_code_of_first_location(conn):
    _seed_chicago(conn)
    _seed_locality(
        conn, code="CHI", year=2026, name="Chicago-Naperville",
        adjustment_pct=32.45, counties=["17031"],
    )
    upsert_job(conn, _job())

    detail = next(iter(job_details(conn, year=2026).values()))
    assert detail["locality_code"] == "CHI"


# ---- D.5.28: summary/qualifications excerpts -----------------------------


def test_excerpt_returns_none_for_empty_or_whitespace():
    assert _excerpt(None) is None
    assert _excerpt("") is None
    assert _excerpt("   \n\t  ") is None


def test_excerpt_passes_short_text_through_unchanged():
    text = "Lead disaster recovery efforts across Region V."
    assert _excerpt(text) == text


def test_excerpt_strips_html_tags_and_entities():
    html = (
        "<p>Lead <strong>disaster recovery</strong> efforts.</p>"
        "<ul><li>Plan&nbsp;and&nbsp;execute</li></ul>"
    )
    assert _excerpt(html) == "Lead disaster recovery efforts. Plan and execute"


def test_excerpt_trims_to_max_chars_with_ellipsis_on_word_boundary():
    long = "word " * 100  # 500 chars of "word "
    out = _excerpt(long)
    assert out is not None
    assert len(out) <= EXCERPT_MAX_CHARS
    assert out.endswith("…")
    # Last visible char before the ellipsis should not be mid-word; we trim
    # at the last whitespace inside the budget.
    assert not out[:-1].endswith("wor")


def test_excerpt_respects_custom_max_chars():
    out = _excerpt("a" * 50, max_chars=10)
    assert out is not None
    assert len(out) <= 10
    assert out.endswith("…")


def test_job_details_includes_excerpts_when_job_text_present(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job())
    job_id = conn.execute("SELECT id FROM jobs LIMIT 1").fetchone()["id"]
    upsert_job_text(
        conn,
        job_id,
        {
            "summary": (
                "<p>Lead <b>disaster recovery</b> efforts across Region V, "
                "coordinating with state and tribal partners.</p>"
            ),
            "qualifications": (
                "One year of specialized experience equivalent to the GS-12 "
                "level demonstrating program-management leadership."
            ),
        },
    )

    detail = next(iter(job_details(conn).values()))
    assert detail["summary_excerpt"] == (
        "Lead disaster recovery efforts across Region V, "
        "coordinating with state and tribal partners."
    )
    assert detail["qualifications_excerpt"].startswith("One year of specialized experience")
    assert len(detail["qualifications_excerpt"]) <= EXCERPT_MAX_CHARS


def test_job_details_omits_excerpts_when_job_text_missing(conn):
    _seed_chicago(conn)
    upsert_job(conn, _job())
    detail = next(iter(job_details(conn).values()))
    assert "summary_excerpt" in detail
    assert "qualifications_excerpt" in detail
    assert detail["summary_excerpt"] is None
    assert detail["qualifications_excerpt"] is None


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


def test_series_options_labels_from_job_categories(conn):
    _seed_chicago(conn)
    # Two postings for series 2210 carry the official JobCategory.Name; the
    # series label should come from that name, not the bare code.
    for pid in ("IT-001", "IT-002"):
        job_id = upsert_job(
            conn,
            _job(
                position_id=pid,
                announcement_number=pid,
                usajobs_control_number=f"2000000{pid[-1]}",
                series="2210",
            ),
        )
        replace_job_categories(
            conn, job_id, [{"series": "2210", "name": "Information Technology Management"}]
        )
    # A series with no JobCategory name and no curated label falls back to code.
    upsert_job(
        conn,
        _job(
            position_id="NN-001",
            announcement_number="NN-001",
            usajobs_control_number="20000009",
            series="9999",
        ),
    )

    by_code = {row["code"]: row["label"] for row in series_options(conn)}
    assert by_code["2210"] == "Information Technology Management"
    assert by_code["9999"] == "9999"


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


# ---------- Federal Real Property layer (D.5.9) -----------------------------


def _insert_federal_property(conn, **kwargs) -> None:
    defaults = {
        "frpp_id": "TEST-1",
        "name": "Test Building",
        "property_type": "Office",
        "agency": "GSA",
        "agency_code": "GS",
        "address": "123 Main St",
        "city": "Anywhere",
        "state": "VA",
        "zip": "22202",
        "county_fips": "51013",
        "latitude": 38.87,
        "longitude": -77.05,
        "building_status": "Active",
        "source": "test",
        "imported_at": utc_now(),
    }
    defaults.update(kwargs)
    conn.execute(
        """
        INSERT INTO federal_properties (
            frpp_id, name, property_type, agency, agency_code, address,
            city, state, zip, county_fips, latitude, longitude,
            building_status, source, imported_at
        ) VALUES (
            :frpp_id, :name, :property_type, :agency, :agency_code, :address,
            :city, :state, :zip, :county_fips, :latitude, :longitude,
            :building_status, :source, :imported_at
        )
        """,
        defaults,
    )
    conn.commit()


def test_federal_properties_geojson_returns_point_features(conn):
    _insert_federal_property(conn, frpp_id="A", latitude=38.87, longitude=-77.05)
    _insert_federal_property(conn, frpp_id="B", latitude=29.55, longitude=-95.09)

    fc = federal_properties_geojson(conn)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    geom_types = {f["geometry"]["type"] for f in fc["features"]}
    assert geom_types == {"Point"}
    ids = {f["properties"]["id"] for f in fc["features"]}
    assert ids == {"A", "B"}


def test_federal_properties_geojson_skips_missing_or_invalid_coords(conn):
    _insert_federal_property(conn, frpp_id="OK", latitude=38.87, longitude=-77.05)
    _insert_federal_property(conn, frpp_id="NULL_LAT", latitude=None, longitude=-77.0)
    _insert_federal_property(conn, frpp_id="OUT_OF_RANGE", latitude=99.0, longitude=0.0)

    fc = federal_properties_geojson(conn)
    ids = {f["properties"]["id"] for f in fc["features"]}
    assert ids == {"OK"}


def test_federal_properties_geojson_omits_null_properties(conn):
    _insert_federal_property(
        conn,
        frpp_id="SPARSE",
        property_type=None,
        address=None,
        zip=None,
        county_fips=None,
        building_status=None,
    )
    fc = federal_properties_geojson(conn)
    feat = fc["features"][0]
    assert feat["properties"]["id"] == "SPARSE"
    # Null fields should be omitted, not rendered as null/None.
    assert "property_type" not in feat["properties"]
    assert "address" not in feat["properties"]
    assert "zip" not in feat["properties"]
    assert "building_status" not in feat["properties"]
    # Non-null fields stay.
    assert feat["properties"]["name"] == "Test Building"
    assert feat["properties"]["state"] == "VA"


def test_federal_properties_geojson_empty_when_table_has_no_rows(conn):
    fc = federal_properties_geojson(conn)
    assert fc == {"type": "FeatureCollection", "features": []}


# ---------- D.5.28 historical badges (repost denormalization) ----------------


def _seed_repost_group(conn, member_specs):
    """Create one completed repost run with a single group whose members are
    (job_id, open_date) tuples (jobs must already exist)."""
    conn.execute(
        "INSERT INTO repost_runs (started_at, completed_at, params_json)"
        " VALUES (?, ?, '{}')",
        (utc_now(), utc_now()),
    )
    run_id = conn.execute("SELECT MAX(id) FROM repost_runs").fetchone()[0]
    conn.execute(
        "INSERT INTO repost_groups (run_id, group_signature, member_count,"
        " confidence_score, created_at) VALUES (?, 'sig', ?, 0.9, ?)",
        (run_id, len(member_specs), utc_now()),
    )
    group_id = conn.execute("SELECT MAX(id) FROM repost_groups").fetchone()[0]
    for job_id in member_specs:
        conn.execute(
            "INSERT INTO repost_group_members (group_id, job_id, created_at)"
            " VALUES (?, ?, ?)",
            (group_id, job_id, utc_now()),
        )
    conn.commit()
    return run_id


def test_historical_badges_orders_by_open_date_and_reports_span(conn):
    _seed_chicago(conn)
    ids = []
    for i, open_date in enumerate(["2024-09-01", "2025-06-01", "2026-03-01"]):
        upsert_job(
            conn,
            _job(
                usajobs_control_number=f"20000000{i}",
                position_id=f"REPOST-{i}",
                announcement_number=f"REPOST-{i}",
                open_date=open_date,
                url=f"https://www.usajobs.gov/job/20000000{i}",
            ),
        )
        ids.append(
            conn.execute(
                "SELECT id FROM jobs WHERE position_id = ?", (f"REPOST-{i}",)
            ).fetchone()[0]
        )
    # Insert members out of order — open_date must drive the ranking.
    _seed_repost_group(conn, [ids[1], ids[0], ids[2]])

    badges = historical_badges(conn)
    assert badges[ids[0]] == "1st posting"
    assert badges[ids[1]] == "2nd posting · 9 mo"
    assert badges[ids[2]] == "3rd posting · 18 mo"


def test_historical_badges_empty_without_completed_run(conn):
    assert historical_badges(conn) == {}
    # An incomplete run must not count either.
    conn.execute(
        "INSERT INTO repost_runs (started_at, completed_at, params_json)"
        " VALUES (?, NULL, '{}')",
        (utc_now(),),
    )
    conn.commit()
    assert historical_badges(conn) == {}


def test_historical_badges_only_uses_latest_completed_run(conn):
    _seed_chicago(conn)
    for i in range(2):
        upsert_job(
            conn,
            _job(
                usajobs_control_number=f"21000000{i}",
                position_id=f"LATEST-{i}",
                announcement_number=f"LATEST-{i}",
                open_date=f"2026-0{i + 1}-01",
                url=f"https://www.usajobs.gov/job/21000000{i}",
            ),
        )
    ids = [
        conn.execute("SELECT id FROM jobs WHERE position_id = ?", (f"LATEST-{i}",)).fetchone()[0]
        for i in range(2)
    ]
    _seed_repost_group(conn, ids)  # old run
    _seed_repost_group(conn, ids)  # latest run — the only one that counts
    old_run = conn.execute(
        "SELECT MIN(id) FROM repost_runs WHERE completed_at IS NOT NULL"
    ).fetchone()[0]
    # Groups from the older run must be ignored even if they disagree.
    badges = historical_badges(conn)
    assert set(badges) == set(ids)
    rows = conn.execute(
        "SELECT COUNT(*) FROM repost_groups WHERE run_id = ?", (old_run,)
    ).fetchone()[0]
    assert rows == 1  # the old group exists but contributed nothing extra


def test_job_details_carries_historical_badge(conn):
    _seed_chicago(conn)
    for i in range(2):
        upsert_job(
            conn,
            _job(
                usajobs_control_number=f"22000000{i}",
                position_id=f"BADGE-{i}",
                announcement_number=f"BADGE-{i}",
                open_date=f"2025-0{i + 1}-01",
                url=f"https://www.usajobs.gov/job/22000000{i}",
            ),
        )
    ids = [
        conn.execute("SELECT id FROM jobs WHERE position_id = ?", (f"BADGE-{i}",)).fetchone()[0]
        for i in range(2)
    ]
    _seed_repost_group(conn, ids)

    details = job_details(conn)
    assert details[str(ids[0])]["historical_badge"] == "1st posting"
    assert details[str(ids[1])]["historical_badge"] == "2nd posting · 1 mo"
    # A job outside any group carries None, not a fabricated badge.
    upsert_job(conn, _job(usajobs_control_number="230000001", position_id="SOLO-1",
                          announcement_number="SOLO-1", url="https://www.usajobs.gov/job/230000001"))
    solo_id = conn.execute("SELECT id FROM jobs WHERE position_id = 'SOLO-1'").fetchone()[0]
    assert job_details(conn)[str(solo_id)]["historical_badge"] is None
