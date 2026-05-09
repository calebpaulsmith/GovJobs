"""Tests for the Phase A.7 polygon and pay-table exporters.

These exercise the file-reading polygon emitters (`states_geojson`,
`localities_geojson`, `counties_geojson`, `metros_geojson`), the pay
lookup tables (`pay_tables`, `cost_of_living`), the new `locality_code`
property on markers, and the manifest's `data_sources` freshness map.

Fixtures use tmp_path so polygon files live alongside each test rather
than depending on `data/external/`. The exporter handles both repo-
relative and absolute paths so this works without seeding real data.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.data_source_registry import begin_run, complete_run, fail_run
from src.database import (
    connect,
    init_schema,
    upsert_geocoded_location,
    upsert_job,
    utc_now,
)
from src.public_map_export import (
    cost_of_living,
    counties_geojson,
    current_reference_year,
    data_sources_freshness,
    jobs_geojson,
    localities_geojson,
    manifest,
    metros_geojson,
    pay_tables,
    simplify_geometry,
    states_geojson,
)


YEAR = 2026


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "federal_jobs.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


# ---------- helpers --------------------------------------------------------


def _write_polygon(path: Path, coordinates: list[list[list[float]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": coordinates},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _il_box() -> list[list[list[float]]]:
    return [[
        [-91.5, 37.0], [-87.0, 37.0], [-87.0, 42.5], [-91.5, 42.5], [-91.5, 37.0],
    ]]


def _tx_box() -> list[list[list[float]]]:
    return [[
        [-106.6, 25.8], [-93.5, 25.8], [-93.5, 36.5], [-106.6, 36.5], [-106.6, 25.8],
    ]]


def _cook_box() -> list[list[list[float]]]:
    return [[
        [-88.3, 41.5], [-87.5, 41.5], [-87.5, 42.2], [-88.3, 42.2], [-88.3, 41.5],
    ]]


def _seed_state_polygon(
    conn, *, state, name, polygon_path
):
    conn.execute(
        """
        INSERT OR REPLACE INTO state_polygons (state, name, polygon_path, source, imported_at)
        VALUES (?, ?, ?, 'test:tiger', ?)
        """,
        (state, name, str(polygon_path), utc_now()),
    )
    conn.commit()


def _seed_county(
    conn, *, fips, name, state, cbsa_code=None, polygon_path=None
):
    conn.execute(
        """
        INSERT OR REPLACE INTO counties (fips, name, state, cbsa_code, polygon_path, source, imported_at)
        VALUES (?, ?, ?, ?, ?, 'test:tiger', ?)
        """,
        (fips, name, state, cbsa_code, str(polygon_path) if polygon_path else None, utc_now()),
    )
    conn.commit()


def _seed_metro(conn, *, cbsa_code, name, cbsa_type="metro", polygon_path=None):
    conn.execute(
        """
        INSERT OR REPLACE INTO metro_areas (cbsa_code, name, cbsa_type, polygon_path, source, imported_at)
        VALUES (?, ?, ?, ?, 'test:tiger', ?)
        """,
        (cbsa_code, name, cbsa_type, str(polygon_path) if polygon_path else None, utc_now()),
    )
    conn.commit()


def _seed_locality(
    conn, *, code, year=YEAR, name, adjustment_pct, county_fips, polygon_path=None
):
    conn.execute(
        """
        INSERT OR REPLACE INTO locality_pay_areas (
            code, year, name, description, adjustment_pct,
            polygon_path, source, source_url, imported_at
        ) VALUES (?, ?, ?, NULL, ?, ?, 'test', NULL, ?)
        """,
        (code, year, name, adjustment_pct, str(polygon_path) if polygon_path else None, utc_now()),
    )
    for fips in county_fips:
        conn.execute(
            """
            INSERT OR REPLACE INTO locality_pay_counties (locality_code, year, county_fips, inclusion_type)
            VALUES (?, ?, ?, 'core')
            """,
            (code, year, fips),
        )
    conn.commit()


def _seed_pay_row(
    conn, *, pay_plan_code="GS", year=YEAR, grade, step, locality_code, rate
):
    conn.execute(
        """
        INSERT OR REPLACE INTO pay_scales (
            pay_plan, year, grade, step, locality_code,
            annual_rate, source, source_url, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'opm:test', 'https://example.org/pay', ?)
        """,
        (pay_plan_code, year, grade, step, locality_code, rate, utc_now()),
    )
    conn.commit()


def _seed_rpp(conn, *, geo_type, geo_code, year, rpp_overall, source="bea:rpp"):
    conn.execute(
        """
        INSERT OR REPLACE INTO cost_of_living_index (
            year, geo_type, geo_code, rpp_overall, rpp_goods, rpp_services,
            rpp_rents, source, imported_at
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
        """,
        (year, geo_type, geo_code, rpp_overall, source, utc_now()),
    )
    conn.commit()


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
        "grade_low": "13",
        "grade_high": "13",
        "pay_plan": "GS",
        "salary_min": 110_000,
        "salary_max": 160_000,
        "location_text": "Chicago, Illinois",
        "state": "IL",
        "city": "Chicago",
        "remote_status": "hybrid",
        "open_date": "2026-04-01",
        "close_date": "2099-12-31",
        "url": "https://www.usajobs.gov/job/100000001",
        "source_endpoint": "/api/historicjoa",
        "locations": [{"city": "Chicago", "state": "IL", "location_text": "Chicago, IL"}],
    }
    base.update(overrides)
    return base


def _seed_chicago_geocode(conn):
    upsert_geocoded_location(
        conn, city="Chicago", state="IL", lat=41.8781, lon=-87.6298, county_fips="17031"
    )


def _seed_full_chicago_fixture(conn, tmp_path):
    """A fixture with one polygon for IL, one county (Cook), one CBSA (Chicago),
    one locality (CHI) and a posting in Chicago."""
    il = _write_polygon(tmp_path / "states" / "IL.geojson", _il_box())
    cook = _write_polygon(tmp_path / "counties" / "17031.geojson", _cook_box())
    chi_metro = _write_polygon(tmp_path / "metros" / "16980.geojson", _cook_box())
    chi_loc = _write_polygon(tmp_path / "localities" / "CHI.geojson", _cook_box())

    _seed_state_polygon(conn, state="IL", name="Illinois", polygon_path=il)
    _seed_county(conn, fips="17031", name="Cook", state="IL", cbsa_code="16980", polygon_path=cook)
    _seed_metro(conn, cbsa_code="16980", name="Chicago-Naperville-Elgin", polygon_path=chi_metro)
    _seed_locality(
        conn,
        code="CHI",
        name="Chicago-Naperville",
        adjustment_pct=32.45,
        county_fips=["17031"],
        polygon_path=chi_loc,
    )
    # GS-13 step 1 locality row + step 5 (a representative cell so the popup
    # has something to show).
    _seed_pay_row(conn, grade="13", step=1, locality_code="CHI", rate=110_803.00)
    _seed_pay_row(conn, grade="13", step=5, locality_code="CHI", rate=122_500.00)
    # COL data for IL state and Chicago CBSA
    _seed_rpp(conn, geo_type="state", geo_code="IL", year=2024, rpp_overall=99.5)
    _seed_rpp(conn, geo_type="cbsa", geo_code="16980", year=2024, rpp_overall=104.2)

    _seed_chicago_geocode(conn)
    upsert_job(conn, _job())


# ---------- simplify_geometry --------------------------------------------


def test_simplify_geometry_drops_collinear_points():
    # A square with an extra collinear midpoint on each edge should
    # collapse back to four corners (plus the closing point).
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [0.0, 0.0], [1.0, 0.0], [2.0, 0.0],
            [2.0, 1.0], [2.0, 2.0],
            [1.0, 2.0], [0.0, 2.0],
            [0.0, 1.0], [0.0, 0.0],
        ]],
    }
    simplified = simplify_geometry(geometry, tolerance=0.001)
    assert simplified is not None
    ring = simplified["coordinates"][0]
    # Five points: 4 corners + closing point.
    assert len(ring) == 5
    assert ring[0] == ring[-1]


def test_simplify_geometry_passes_multipolygon_through():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
        ],
    }
    simplified = simplify_geometry(geometry, tolerance=0.0)
    assert simplified == geometry


def test_simplify_geometry_handles_none():
    assert simplify_geometry(None, tolerance=0.1) is None


# ---------- current_reference_year ---------------------------------------


def test_current_reference_year_picks_max_pay_scale_year(conn):
    _seed_pay_row(conn, year=2025, grade="13", step=1, locality_code="", rate=100_000)
    _seed_pay_row(conn, year=2026, grade="13", step=1, locality_code="", rate=105_000)
    assert current_reference_year(conn) == 2026


# ---------- states_geojson -----------------------------------------------


def test_states_geojson_joins_postings_and_pay(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)

    fc = states_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    feature = fc["features"][0]
    props = feature["properties"]
    assert props["state"] == "IL"
    assert props["name"] == "Illinois"
    assert props["postings"] == 1
    assert props["locality_code"] == "CHI"
    assert props["gs13_step1_locality"] == 110_803.00
    assert props["rpp_overall"] == 99.5
    # pay_vs_col = 110803 / 99.5 * 100 = 111_360.80...
    assert props["pay_vs_col"] is not None and props["pay_vs_col"] > 100


def test_states_total_postings_matches_marker_count(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)
    # Add a TX state polygon with no postings to confirm we don't double-count.
    tx = _write_polygon(tmp_path / "states" / "TX.geojson", _tx_box())
    _seed_state_polygon(conn, state="TX", name="Texas", polygon_path=tx)

    states = states_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    total_state_postings = sum(f["properties"]["postings"] for f in states["features"])
    markers = jobs_geojson(conn, year=YEAR)["features"]
    assert total_state_postings == len(markers) == 1


def test_states_geojson_skips_states_without_polygon_file(conn, tmp_path):
    # Polygon path points at a missing file — feature is skipped.
    _seed_state_polygon(
        conn,
        state="IL",
        name="Illinois",
        polygon_path=tmp_path / "missing.geojson",
    )
    fc = states_geojson(conn, repo_root=tmp_path, year=YEAR)
    assert fc["features"] == []


# ---------- localities_geojson -------------------------------------------


def test_localities_geojson_carries_county_count_and_pay(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)

    fc = localities_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["code"] == "CHI"
    assert props["county_count"] == 1
    assert props["adjustment_pct"] == 32.45
    assert props["gs13_step1_locality"] == 110_803.00
    # rpp averaged across CBSAs containing CHI counties
    assert props["rpp_overall"] == 104.2
    assert props["rpp_overall_approximate"] is True
    assert props["postings"] == 1


# ---------- counties_geojson ---------------------------------------------


def test_counties_geojson_joins_locality_and_state_rpp(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)

    fc = counties_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["fips"] == "17031"
    assert props["state"] == "IL"
    assert props["cbsa_code"] == "16980"
    assert props["locality_code"] == "CHI"
    # No county-level RPP seeded in this fixture — falls back to the state value.
    assert props["rpp_overall"] == 99.5
    assert props["rpp_overall_source"] == "state"
    assert props["gs13_step1_locality"] == 110_803.00
    assert props["postings"] == 1


def test_counties_geojson_prefers_county_rpp_when_present(conn, tmp_path):
    """D.5.10: when census_acs_rent has populated a county-level row in
    cost_of_living_index, counties_geojson must use it instead of the
    state-level fallback and label the source as 'county'."""
    _seed_full_chicago_fixture(conn, tmp_path)
    # ACS-derived county row that differs from the state-level value
    _seed_rpp(
        conn,
        geo_type="county",
        geo_code="17031",
        year=2023,
        rpp_overall=109.62,
        source="census:acs5_b25064",
    )

    fc = counties_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    props = fc["features"][0]["properties"]
    assert props["rpp_overall"] == 109.62
    assert props["rpp_overall_source"] == "county"
    assert props["pay_vs_col"] is not None


def test_counties_postings_match_marker_county_fips(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)
    fc = counties_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    total = sum(f["properties"]["postings"] for f in fc["features"])
    # One marker, one county — must match.
    assert total == 1


# ---------- metros_geojson -----------------------------------------------


def test_metros_geojson_joins_rpp_and_postings(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)

    fc = metros_geojson(conn, repo_root=tmp_path, year=YEAR, tolerance=0.0)
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["cbsa_code"] == "16980"
    assert props["cbsa_type"] == "metro"
    assert props["rpp_overall"] == 104.2
    assert props["postings"] == 1


# ---------- markers carry locality_code ----------------------------------


def test_jobs_geojson_includes_locality_code(conn, tmp_path):
    _seed_full_chicago_fixture(conn, tmp_path)
    feature = jobs_geojson(conn, year=YEAR)["features"][0]
    assert feature["properties"]["locality_code"] == "CHI"


def test_jobs_geojson_falls_back_to_locality_polygon_for_source_coordinates(conn, tmp_path):
    chi_loc = _write_polygon(tmp_path / "localities" / "CHI.geojson", _cook_box())
    _seed_locality(
        conn,
        code="CHI",
        name="Chicago-Naperville",
        adjustment_pct=32.45,
        county_fips=["17031"],
        polygon_path=chi_loc,
    )
    upsert_job(
        conn,
        _job(
            locations=[
                {
                    "city": "Chicago, Illinois",
                    "state": "IL",
                    "location_text": "Chicago, IL",
                    "latitude": 41.8781,
                    "longitude": -87.6298,
                }
            ],
        ),
    )

    feature = jobs_geojson(conn, year=YEAR, repo_root=tmp_path)["features"][0]

    assert feature["properties"]["locality_code"] == "CHI"


def test_jobs_geojson_locality_code_is_none_when_county_unmatched(conn, tmp_path):
    # Geocode without a county_fips — no locality match expected.
    upsert_geocoded_location(
        conn, city="Anywhere", state="IL", lat=40.0, lon=-89.0, county_fips=None
    )
    upsert_job(
        conn,
        _job(
            position_id="ANY-1",
            announcement_number="ANY-1",
            usajobs_control_number="100000099",
            city="Anywhere",
            location_text="Anywhere, IL",
            locations=[{"city": "Anywhere", "state": "IL", "location_text": "Anywhere, IL"}],
        ),
    )
    feature = jobs_geojson(conn, year=YEAR)["features"][0]
    assert feature["properties"]["locality_code"] is None


# ---------- pay_tables ---------------------------------------------------


def test_pay_tables_groups_by_plan_year_locality_grade_step(conn, tmp_path):
    _seed_pay_row(conn, year=2026, grade="13", step=1, locality_code="CHI", rate=110_803.0)
    _seed_pay_row(conn, year=2026, grade="13", step=5, locality_code="CHI", rate=122_500.0)
    _seed_pay_row(conn, year=2026, grade="13", step=1, locality_code="", rate=96_148.0)
    _seed_pay_row(conn, year=2025, grade="13", step=1, locality_code="", rate=92_000.0)

    tables = pay_tables(conn)
    assert tables["GS"]["2026"]["CHI"]["13"]["1"] == 110_803.0
    assert tables["GS"]["2026"]["CHI"]["13"]["5"] == 122_500.0
    assert tables["GS"]["2026"]["BASE"]["13"]["1"] == 96_148.0
    assert tables["GS"]["2025"]["BASE"]["13"]["1"] == 92_000.0


# ---------- cost_of_living -----------------------------------------------


def test_cost_of_living_returns_latest_year_per_geo(conn):
    _seed_rpp(conn, geo_type="state", geo_code="IL", year=2023, rpp_overall=98.0)
    _seed_rpp(conn, geo_type="state", geo_code="IL", year=2024, rpp_overall=99.5)
    _seed_rpp(conn, geo_type="cbsa", geo_code="16980", year=2024, rpp_overall=104.2)

    col = cost_of_living(conn)
    assert col["by_state"]["IL"]["year"] == 2024
    assert col["by_state"]["IL"]["rpp_overall"] == 99.5
    assert col["by_cbsa"]["16980"]["rpp_overall"] == 104.2
    # by_county is always present (D.5.10), even if empty
    assert "by_county" in col
    assert col["by_county"] == {}


def test_cost_of_living_by_county_carries_acs_rows(conn):
    """D.5.10: county-level rows from census:acs5_b25064 land in by_county."""
    _seed_rpp(
        conn,
        geo_type="county",
        geo_code="17031",
        year=2023,
        rpp_overall=109.62,
        source="census:acs5_b25064",
    )
    _seed_rpp(
        conn,
        geo_type="county",
        geo_code="06037",
        year=2023,
        rpp_overall=113.8,
        source="census:acs5_b25064",
    )
    col = cost_of_living(conn)
    assert col["by_county"]["17031"]["rpp_overall"] == 109.62
    assert col["by_county"]["17031"]["source"] == "census:acs5_b25064"
    assert col["by_county"]["06037"]["rpp_overall"] == 113.8


# ---------- manifest data sources ----------------------------------------


def test_manifest_data_sources_carries_freshness(conn):
    begin_run(conn, "census_states", "Census state polygons", "geometry")
    complete_run(conn, "census_states", row_count=56, notes="sample")
    begin_run(conn, "opm_locality_pay", "OPM locality pay", "pay")
    fail_run(conn, "opm_locality_pay", "boom")

    freshness = data_sources_freshness(conn)
    assert freshness["census_states"]["row_count"] == 56
    assert freshness["census_states"]["last_success_at"]
    assert freshness["census_states"]["has_error"] is False
    assert freshness["opm_locality_pay"]["has_error"] is True

    man = manifest(
        conn,
        feature_count=0,
        job_count=0,
        opm_state_count=0,
        layer_counts={"states.geojson": 0, "counties.geojson": 0},
    )
    assert "census_states" in man["data_sources"]
    assert man["layers"]["states.geojson"] == 0
