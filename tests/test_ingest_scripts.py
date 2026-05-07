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
