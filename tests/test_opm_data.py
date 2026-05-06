from __future__ import annotations

import sqlite3
import zipfile

import pandas as pd
import pytest

from config import load_config
from src.database import connect, init_schema
from src.opm_data import import_opm_file
from src.ui_data import opm_datasets_dataframe, opm_state_counts


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "opm.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def test_import_opm_csv_normalizes_common_columns(conn, tmp_path):
    source = tmp_path / "employment.csv"
    source.write_text(
        "\n".join(
            [
                "Fiscal Year,Quarter,Agency,Sub Agency,Occupation Series,Grade,Pay Plan,State,Headcount,Average Salary",
                "2026,Q1,Department of Homeland Security,FEMA,89,13,GS,Illinois,25,125000",
                "2026,Q1,Department of Homeland Security,FEMA,0343,14,GS,WI,10,132500",
            ]
        ),
        encoding="utf-8",
    )

    result = import_opm_file(
        conn,
        load_config(),
        source,
        dataset="fedscope_employment",
        clear_existing=True,
    )

    assert result.records_imported == 2
    rows = conn.execute("SELECT * FROM opm_workforce_records ORDER BY id").fetchall()
    assert rows[0]["period_year"] == 2026
    assert rows[0]["period_quarter"] == 1
    assert rows[0]["occupation_series"] == "0089"
    assert rows[0]["grade"] == "13"
    assert rows[0]["location_state"] == "IL"
    assert rows[0]["employment_count"] == 25
    assert rows[0]["salary_avg"] == 125000
    assert conn.execute("SELECT COUNT(*) FROM raw_api_responses WHERE source='opm'").fetchone()[0] == 1
    manifest = conn.execute("SELECT * FROM import_manifests WHERE id=?", (result.manifest_id,)).fetchone()
    assert manifest["status"] == "completed"


def test_import_opm_zip_and_state_counts(conn, tmp_path):
    csv_path = tmp_path / "accessions.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Year,Period,Agency Name,Series,Location State,Count",
                "2026,2026 Q2,Federal Emergency Management Agency,0089,IL,3",
                "2026,2026 Q2,Federal Emergency Management Agency,0343,Wisconsin,2",
            ]
        ),
        encoding="utf-8",
    )
    zip_path = tmp_path / "accessions.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(csv_path, arcname="accessions.csv")

    import_opm_file(conn, load_config(), zip_path, dataset="accessions", clear_existing=True)

    states = opm_state_counts(conn, metric="accessions")
    assert set(states["state"]) == {"IL", "WI"}
    assert int(states["accessions"].sum()) == 5


def test_import_opm_excel_and_dataset_summary(conn, tmp_path):
    source = tmp_path / "separations.xlsx"
    pd.DataFrame(
        [
            {
                "Reporting Year": 2025,
                "QTR": "Q4",
                "Department": "Department of Homeland Security",
                "Occupation": "0301",
                "State Code": "IL",
                "Total": 7,
            }
        ]
    ).to_excel(source, index=False)

    import_opm_file(conn, load_config(), source, dataset="separations", clear_existing=True)

    summary = opm_datasets_dataframe(conn)
    assert summary.iloc[0]["dataset"] == "separations"
    assert int(summary.iloc[0]["separations"]) == 7


def test_import_opm_rejects_unsupported_file(conn, tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"nope")

    with pytest.raises(ValueError, match="Unsupported"):
        import_opm_file(conn, load_config(), source, dataset="bad")
