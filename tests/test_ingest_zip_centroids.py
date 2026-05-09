from __future__ import annotations

import sqlite3

import pytest

from scripts.ingest_zip_centroids import ingest_file
from src.database import connect, init_schema


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "federal_jobs.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def test_ingest_zip_centroids_reads_simplemaps_csv(conn, tmp_path):
    csv_path = tmp_path / "uszips.csv"
    csv_path.write_text(
        "zip,lat,lng,city,state_id,county_fips\n"
        "60601,41.88531,-87.62164,Chicago,IL,17031\n",
        encoding="utf-8",
    )

    rows = ingest_file(conn, csv_path, source="simplemaps:test")

    assert rows == 1
    row = conn.execute("SELECT * FROM zip_centroids WHERE zip='60601'").fetchone()
    assert row["city"] == "Chicago"
    assert row["state"] == "IL"
    assert row["county_fips"] == "17031"


def test_ingest_zip_centroids_reads_census_gazetteer_txt(conn, tmp_path):
    txt_path = tmp_path / "gaz.txt"
    txt_path.write_text(
        "GEOID\tALAND\tAWATER\tINTPTLAT\tINTPTLONG\n"
        "20002\t0\t0\t38.90251\t-76.99152\n",
        encoding="utf-8",
    )

    rows = ingest_file(conn, txt_path, source="census:test")

    assert rows == 1
    row = conn.execute("SELECT * FROM zip_centroids WHERE zip='20002'").fetchone()
    assert row["lat"] == 38.90251
    assert row["lon"] == -76.99152
    assert row["city"] is None
