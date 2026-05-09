"""Tests for the public-map ingest scripts.

Each ingest script exposes a pure ``import_*`` function we call directly with
fixture files. No subprocess, no network. The fixture files mirror the
real-world CSV / GeoJSON shape so format drift is caught early.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.ingest_acs_county_rent import (
    import_acs_county_rent_from_csv,
    SEED_CSV as ACS_SEED_CSV,
)
from scripts.ingest_bea_rpp import import_rpp_from_csv
from scripts.ingest_cbsa_polygons import import_cbsa_from_geojson
from scripts.ingest_county_polygons import import_counties_from_geojson
from scripts.ingest_gs_pay import import_gs_pay_from_csv
from scripts.ingest_locality_definitions import import_definitions_from_csv
from scripts.ingest_locality_pay import import_locality_pay_from_csv
from scripts.ingest_locality_polygons import (
    build_locality_polygons_via_dissolve,
    import_polygons,
)
from scripts.ingest_state_polygons import import_states_from_geojson
from src.database import connect, init_schema


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "federal_jobs.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


# ---------- helpers --------------------------------------------------------


def _write_geojson(path: Path, features: list[dict]) -> Path:
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _il_polygon() -> dict:
    return {"type": "Polygon", "coordinates": [[
        [-91.5, 37.0], [-87.0, 37.0], [-87.0, 42.5], [-91.5, 42.5], [-91.5, 37.0],
    ]]}


# ---------- state polygons -------------------------------------------------


def test_state_polygons_ingest_writes_rows_and_files(conn, tmp_path):
    geojson = _write_geojson(
        tmp_path / "states.geojson",
        [
            {
                "type": "Feature",
                "properties": {"STUSPS": "IL", "NAME": "Illinois"},
                "geometry": _il_polygon(),
            },
            {
                "type": "Feature",
                "properties": {"STUSPS": "tx", "NAME": "Texas"},
                "geometry": _il_polygon(),
            },
        ],
    )
    output = tmp_path / "out"
    written = import_states_from_geojson(
        conn, input_path=geojson, output_dir=output, source="test:tiger"
    )
    assert written == 2
    rows = conn.execute("SELECT state, name, polygon_path FROM state_polygons ORDER BY state").fetchall()
    assert [r["state"] for r in rows] == ["IL", "TX"]
    for row in rows:
        path = Path(row["polygon_path"])
        # polygon_path is repo-relative; resolve under tmp_path/out
        assert (output / f"{row['state']}.geojson").exists()


# ---------- counties -------------------------------------------------------


def test_county_polygons_use_state_fp_when_stusps_missing(conn, tmp_path):
    geojson = _write_geojson(
        tmp_path / "counties.geojson",
        [
            {
                "type": "Feature",
                "properties": {"GEOID": "17031", "NAME": "Cook", "STATEFP": "17", "CBSAFP": "16980"},
                "geometry": _il_polygon(),
            }
        ],
    )
    written = import_counties_from_geojson(
        conn, input_path=geojson, output_dir=tmp_path / "out_counties", source="test:tiger"
    )
    assert written == 1
    row = conn.execute("SELECT * FROM counties WHERE fips='17031'").fetchone()
    assert row["state"] == "IL"
    assert row["cbsa_code"] == "16980"


# ---------- CBSAs ----------------------------------------------------------


def test_cbsa_lsad_maps_to_metro_or_micro(conn, tmp_path):
    geojson = _write_geojson(
        tmp_path / "cbsa.geojson",
        [
            {
                "type": "Feature",
                "properties": {"CBSAFP": "16980", "NAME": "Chicago-Naperville-Elgin", "LSAD": "M1"},
                "geometry": _il_polygon(),
            },
            {
                "type": "Feature",
                "properties": {"CBSAFP": "12345", "NAME": "Tinytown", "LSAD": "M2"},
                "geometry": _il_polygon(),
            },
        ],
    )
    import_cbsa_from_geojson(
        conn, input_path=geojson, output_dir=tmp_path / "out_cbsa", source="test:tiger"
    )
    rows = {r["cbsa_code"]: dict(r) for r in conn.execute("SELECT * FROM metro_areas").fetchall()}
    assert rows["16980"]["cbsa_type"] == "metro"
    assert rows["12345"]["cbsa_type"] == "micro"


# ---------- OPM locality definitions --------------------------------------


def test_locality_definitions_ingest_seeds_areas_and_counties(conn, tmp_path):
    csv_path = _write_csv(
        tmp_path / "defs.csv",
        rows=[
            {"locality_code": "CHI", "year": "2026", "county_fips": "17031",
             "inclusion_type": "core", "locality_name": "Chicago-Naperville"},
            {"locality_code": "CHI", "year": "2026", "county_fips": "17043",
             "inclusion_type": "core", "locality_name": "Chicago-Naperville"},
            {"locality_code": "DCB", "year": "2026", "county_fips": "11001",
             "inclusion_type": "core", "locality_name": "Washington-Baltimore-Arlington"},
        ],
        fieldnames=["locality_code", "year", "county_fips", "inclusion_type", "locality_name"],
    )
    written = import_definitions_from_csv(
        conn, input_path=csv_path, source="test", source_url=None, replace_year=False,
    )
    assert written == 3
    counties = {r["county_fips"] for r in conn.execute(
        "SELECT county_fips FROM locality_pay_counties WHERE locality_code='CHI' AND year=2026"
    ).fetchall()}
    assert counties == {"17031", "17043"}
    chi = conn.execute(
        "SELECT name, source FROM locality_pay_areas WHERE code='CHI' AND year=2026"
    ).fetchone()
    assert chi["name"] == "Chicago-Naperville"


def test_locality_definitions_replace_year_clears_old_membership(conn, tmp_path):
    initial = _write_csv(
        tmp_path / "defs_initial.csv",
        rows=[{"locality_code": "CHI", "year": "2026", "county_fips": "17031"}],
        fieldnames=["locality_code", "year", "county_fips"],
    )
    import_definitions_from_csv(
        conn, input_path=initial, source="test", source_url=None, replace_year=False,
    )
    revised = _write_csv(
        tmp_path / "defs_revised.csv",
        rows=[{"locality_code": "CHI", "year": "2026", "county_fips": "17043"}],
        fieldnames=["locality_code", "year", "county_fips"],
    )
    import_definitions_from_csv(
        conn, input_path=revised, source="test", source_url=None, replace_year=True,
    )
    counties = {r["county_fips"] for r in conn.execute(
        "SELECT county_fips FROM locality_pay_counties WHERE locality_code='CHI' AND year=2026"
    ).fetchall()}
    assert counties == {"17043"}


# ---------- OPM locality % -------------------------------------------------


def test_locality_pay_csv_updates_adjustment_pct(conn, tmp_path):
    csv_path = _write_csv(
        tmp_path / "pay.csv",
        rows=[
            {"locality_code": "CHI", "year": "2026", "adjustment_pct": "32.45",
             "locality_name": "Chicago-Naperville"},
            {"locality_code": "RUS", "year": "2026", "adjustment_pct": "17.00",
             "locality_name": "Rest of U.S."},
        ],
        fieldnames=["locality_code", "year", "adjustment_pct", "locality_name"],
    )
    import_locality_pay_from_csv(
        conn, input_path=csv_path, source="test", source_url=None,
    )
    chi = conn.execute(
        "SELECT adjustment_pct FROM locality_pay_areas WHERE code='CHI' AND year=2026"
    ).fetchone()
    assert chi["adjustment_pct"] == pytest.approx(32.45)


# ---------- locality polygons ---------------------------------------------


def test_locality_polygons_dissolve_path_unions_member_counties(conn, tmp_path):
    # Seed two member counties with simple polygon files and definitions.
    counties_geo = _write_geojson(
        tmp_path / "counties.geojson",
        [
            {
                "type": "Feature",
                "properties": {"GEOID": "17031", "NAME": "Cook", "STATEFP": "17"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-88, 41], [-87, 41], [-87, 42], [-88, 42], [-88, 41]
                ]]},
            },
            {
                "type": "Feature",
                "properties": {"GEOID": "17043", "NAME": "DuPage", "STATEFP": "17"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-88.5, 41.5], [-88, 41.5], [-88, 42], [-88.5, 42], [-88.5, 41.5]
                ]]},
            },
        ],
    )
    import_counties_from_geojson(
        conn, input_path=counties_geo, output_dir=tmp_path / "out_counties", source="test"
    )

    defs_csv = _write_csv(
        tmp_path / "defs.csv",
        rows=[
            {"locality_code": "CHI", "year": "2026", "county_fips": "17031"},
            {"locality_code": "CHI", "year": "2026", "county_fips": "17043"},
        ],
        fieldnames=["locality_code", "year", "county_fips"],
    )
    import_definitions_from_csv(
        conn, input_path=defs_csv, source="test", source_url=None, replace_year=False
    )

    built = build_locality_polygons_via_dissolve(
        conn, year=2026, output_dir=tmp_path / "out_loc", source="dissolve",
    )
    assert "CHI" in built
    geom = built["CHI"]["feature"]["geometry"]
    assert geom["type"] == "MultiPolygon"
    assert len(geom["coordinates"]) == 2  # both member counties contributed


def test_locality_polygons_arcgis_path_writes_rows(conn, tmp_path):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"locality_code": "CHI", "locality_name": "Chicago-Naperville"},
                "geometry": _il_polygon(),
            },
        ],
    }
    written = import_polygons(
        conn,
        year=2026,
        fc=fc,
        code_property="locality_code",
        name_property="locality_name",
        output_dir=tmp_path / "out_loc",
        source="opm_arcgis",
    )
    assert written == 1
    row = conn.execute(
        "SELECT polygon_path, source FROM locality_pay_areas WHERE code='CHI' AND year=2026"
    ).fetchone()
    assert row["polygon_path"] is not None
    assert row["source"] == "opm_arcgis"


# ---------- GS pay tables --------------------------------------------------


def test_gs_pay_csv_inserts_base_and_locality_rows(conn, tmp_path):
    csv_path = _write_csv(
        tmp_path / "gs_pay.csv",
        rows=[
            {"year": "2026", "grade": "13", "step": "1", "locality_code": "",
             "annual_rate": "92000", "source_url": "https://opm.gov/2026"},
            {"year": "2026", "grade": "13", "step": "1", "locality_code": "CHI",
             "annual_rate": "121814", "source_url": ""},
        ],
        fieldnames=["year", "grade", "step", "locality_code", "annual_rate", "source_url"],
    )
    written = import_gs_pay_from_csv(
        conn, input_path=csv_path, pay_plan="GS", source="test:gs",
        default_source_url="https://opm.gov/2026",
    )
    assert written == 2
    base = conn.execute(
        "SELECT annual_rate, source_url FROM pay_scales "
        "WHERE pay_plan='GS' AND year=2026 AND grade='13' AND step=1 AND locality_code=''"
    ).fetchone()
    chi = conn.execute(
        "SELECT annual_rate, source_url FROM pay_scales "
        "WHERE pay_plan='GS' AND year=2026 AND grade='13' AND step=1 AND locality_code='CHI'"
    ).fetchone()
    assert base["annual_rate"] == 92000
    assert chi["annual_rate"] == 121814
    # The locality row's source_url falls back to the default when blank in the CSV.
    assert chi["source_url"] == "https://opm.gov/2026"


def test_gs_pay_skips_invalid_rows(conn, tmp_path):
    csv_path = _write_csv(
        tmp_path / "gs.csv",
        rows=[
            {"year": "2026", "grade": "13", "step": "1", "locality_code": "",
             "annual_rate": "92000", "source_url": ""},
            {"year": "BAD", "grade": "13", "step": "1", "locality_code": "",
             "annual_rate": "1", "source_url": ""},
            {"year": "2026", "grade": "", "step": "1", "locality_code": "",
             "annual_rate": "100", "source_url": ""},
        ],
        fieldnames=["year", "grade", "step", "locality_code", "annual_rate", "source_url"],
    )
    written = import_gs_pay_from_csv(
        conn, input_path=csv_path, pay_plan="GS", source="test", default_source_url=None
    )
    assert written == 1


# ---------- BEA RPP --------------------------------------------------------


def test_bea_rpp_csv_inserts_state_and_metro_rows(conn, tmp_path):
    csv_path = _write_csv(
        tmp_path / "rpp.csv",
        rows=[
            {"year": "2024", "geo_type": "state", "geo_code": "il", "rpp_overall": "99.5",
             "rpp_goods": "98.0", "rpp_services": "100.5", "rpp_rents": "105.2"},
            {"year": "2024", "geo_type": "cbsa", "geo_code": "16980", "rpp_overall": "112.4",
             "rpp_goods": "", "rpp_services": "", "rpp_rents": ""},
            {"year": "2024", "geo_type": "country", "geo_code": "US", "rpp_overall": "100.0",
             "rpp_goods": "", "rpp_services": "", "rpp_rents": ""},
        ],
        fieldnames=["year", "geo_type", "geo_code", "rpp_overall",
                    "rpp_goods", "rpp_services", "rpp_rents"],
    )
    written = import_rpp_from_csv(conn, input_path=csv_path, source="bea:rpp")
    assert written == 2  # the unsupported "country" row is skipped
    il = conn.execute(
        "SELECT rpp_overall, rpp_goods FROM cost_of_living_index "
        "WHERE geo_type='state' AND geo_code='IL' AND year=2024 AND source='bea:rpp'"
    ).fetchone()
    assert il["rpp_overall"] == pytest.approx(99.5)
    assert il["rpp_goods"] == pytest.approx(98.0)


# ---------- D.5.14: 2026 seed cutover --------------------------------------


def test_2026_gs_seed_imports_full_grid_and_resolves_reference_year(conn):
    """The checked-in 2026 seed loads cleanly and pay_scales gains a 2026 row
    set. Reference year resolution must then return 2026."""
    from scripts.ingest_gs_pay import SEED_CSV
    from src.public_map_export import current_reference_year

    assert SEED_CSV.exists(), f"missing 2026 GS seed at {SEED_CSV}"
    assert SEED_CSV.name == "2026_base.csv"

    written = import_gs_pay_from_csv(
        conn,
        input_path=SEED_CSV,
        pay_plan="GS",
        source="opm:gs_pay",
        default_source_url=None,
    )
    # 15 grades × 10 steps = 150 cells.
    assert written == 150

    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM pay_scales WHERE pay_plan='GS' AND year=2026"
    ).fetchone()
    assert rows["n"] == 150
    assert current_reference_year(conn) == 2026


def test_2026_locality_pay_seed_loads_with_year_2026():
    """The locality-pay seed file must declare year=2026 for V1 cutover."""
    from scripts.ingest_locality_pay import SEED_CSV

    assert SEED_CSV.exists(), f"missing 2026 locality pay seed at {SEED_CSV}"
    assert SEED_CSV.name == "2026.csv"
    with SEED_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "locality_pay seed is empty"
    assert all(int(row["year"]) == 2026 for row in rows)
    # RUS (Rest of U.S.) must always be present — the calculator's
    # default-locality fallback depends on it.
    assert any(row["locality_code"].upper() == "RUS" for row in rows)


def test_2026_locality_definitions_seed_loads_with_year_2026():
    from scripts.ingest_locality_definitions import SEED_CSV

    assert SEED_CSV.exists(), f"missing 2026 locality defs seed at {SEED_CSV}"
    assert SEED_CSV.name == "2026.csv"
    with SEED_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "locality_definitions seed is empty"
    assert all(int(row["year"]) == 2026 for row in rows)


# ---------- D.5.10: ACS county rent ---------------------------------------


def _seed_state_rpp(conn, state: str, year: int, rpp: float) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO cost_of_living_index (
            year, geo_type, geo_code, rpp_overall, rpp_goods, rpp_services,
            rpp_rents, source, imported_at
        ) VALUES (?, 'state', ?, ?, NULL, NULL, NULL, 'bea:rpp', '2026-01-01T00:00:00Z')
        """,
        (year, state, rpp),
    )
    conn.commit()


def test_acs_county_rent_derives_county_index_using_state_rpp(conn, tmp_path):
    """``county_col_index = state_rpp × (county_rent / state_median_rent)``.

    With three IL counties whose rents are 1000 / 1300 / 1500, the median is
    1300. Cook (1300 in our seed) gets 99.5 × (1300/1300) = 99.5; the cheap
    county gets 99.5 × (1000/1300) ≈ 76.54; the expensive one gets 99.5 ×
    (1500/1300) ≈ 114.81.
    """
    _seed_state_rpp(conn, "IL", 2024, 99.5)
    csv_path = _write_csv(
        tmp_path / "acs.csv",
        rows=[
            {"year": "2023", "state": "IL", "county_fips": "17001",
             "county_name": "Cheap", "median_rent": "1000"},
            {"year": "2023", "state": "IL", "county_fips": "17031",
             "county_name": "Cook", "median_rent": "1300"},
            {"year": "2023", "state": "IL", "county_fips": "17999",
             "county_name": "Pricey", "median_rent": "1500"},
        ],
        fieldnames=["year", "state", "county_fips", "county_name", "median_rent"],
    )
    written = import_acs_county_rent_from_csv(
        conn, input_path=csv_path, source="census:acs5_b25064"
    )
    assert written == 3
    rows = {
        row["geo_code"]: row
        for row in conn.execute(
            "SELECT geo_code, rpp_overall, rpp_rents, year, source "
            "FROM cost_of_living_index WHERE geo_type='county'"
        ).fetchall()
    }
    assert rows["17031"]["rpp_overall"] == pytest.approx(99.5, abs=0.01)
    assert rows["17031"]["rpp_rents"] == pytest.approx(1300.0)
    assert rows["17031"]["source"] == "census:acs5_b25064"
    assert rows["17001"]["rpp_overall"] == pytest.approx(76.54, abs=0.01)
    assert rows["17999"]["rpp_overall"] == pytest.approx(114.81, abs=0.01)


def test_acs_county_rent_falls_back_to_within_state_ratio_without_bea_rpp(conn, tmp_path):
    """Without a BEA state RPP row, the ingest must still produce a value
    (the within-state ratio scaled to a 100-base index)."""
    csv_path = _write_csv(
        tmp_path / "acs.csv",
        rows=[
            {"year": "2023", "state": "TX", "county_fips": "48201",
             "county_name": "Harris", "median_rent": "1340"},
            {"year": "2023", "state": "TX", "county_fips": "48453",
             "county_name": "Travis", "median_rent": "1640"},
        ],
        fieldnames=["year", "state", "county_fips", "county_name", "median_rent"],
    )
    written = import_acs_county_rent_from_csv(
        conn, input_path=csv_path, source="census:acs5_b25064"
    )
    assert written == 2
    rows = {
        row["geo_code"]: row["rpp_overall"]
        for row in conn.execute(
            "SELECT geo_code, rpp_overall FROM cost_of_living_index WHERE geo_type='county'"
        )
    }
    # Median rent across (1340, 1640) is 1490. Harris ratio 1340/1490=0.899...
    assert rows["48201"] == pytest.approx(89.93, abs=0.05)
    assert rows["48453"] == pytest.approx(110.07, abs=0.05)


def test_acs_county_rent_seed_loads_for_every_state(conn):
    """The checked-in seed must cover all 50 states + DC and parse cleanly."""
    assert ACS_SEED_CSV.exists(), f"missing ACS seed at {ACS_SEED_CSV}"
    written = import_acs_county_rent_from_csv(
        conn, input_path=ACS_SEED_CSV, source="census:acs5_b25064"
    )
    assert written >= 100
    states = {
        row["geo_code"][:2]
        for row in conn.execute(
            "SELECT geo_code FROM cost_of_living_index WHERE geo_type='county'"
        )
    }
    # 50 state FIPS prefixes + DC's 11.
    assert len(states) >= 51
