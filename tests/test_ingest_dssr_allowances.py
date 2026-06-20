"""Tests for the DSSR overseas-allowance ingest (no live network).

Parsing is exercised against small fixtures shaped exactly like the live
allowances.state.gov Web920 tables; the seed CSVs are checked for integrity so
a clean/offline checkout always builds.
"""
from __future__ import annotations

import io
import sqlite3
import zipfile

import pytest

from scripts.ingest_dssr_allowances import (
    SEED_ALLOWANCES,
    SEED_SPENDABLE,
    extract_docx_cells,
    gather_rows,
    import_dssr,
    load_allowance_seed,
    load_spendable_seed,
    merge_allowance_tables,
    parse_allowance_table,
    parse_effective_date,
    parse_spendable_cells,
    _parse_band,
)
from src.database import connect, init_schema


HARDSHIP_HTML = """
<html><body>Rates Effective: 06/14/2026
<tr><td title='Country Name'><a id='ITALY'>ITALY</a></td><td title='Post Name'>Rome</td><td title='Rate' style='text-align: right'>0%&nbsp;</td></tr>
<tr><td title='Country Name'><a id='AFGHANISTAN'>AFGHANISTAN</a></td><td title='Post Name'>Kabul</td><td title='Rate' style='text-align: right'>35%&nbsp;</td></tr>
</body></html>
"""

DANGER_HTML = """
<tr><td title='Country Name'><a id='AFGHANISTAN'>AFGHANISTAN</a></td><td title='Post Name'>Kabul</td><td title='Rate' style='text-align: center'>35%&nbsp;</td><td title='Effective Date' style='text-align: center'>04/30/2006</td></tr>
"""

COLA_HTML = """
<tr><td title='Country Name'><a id='ITALY'>ITALY</a></td><td title='Post Name'>Rome</td><td title='Post Allowance' style='text-align: right'>30%&nbsp;</td></tr>
<tr><td title='Country Name'><a id='AFGHANISTAN'>AFGHANISTAN</a></td><td title='Post Name'>Kabul</td><td title='Post Allowance' style='text-align: right'>0%&nbsp;</td></tr>
"""


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "dssr.sqlite")
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def test_parse_effective_date():
    assert parse_effective_date("foo Rates Effective: 06/14/2026 bar") == "2026-06-14"
    assert parse_effective_date("no date here") is None


def test_parse_allowance_table_hardship():
    rows = parse_allowance_table(HARDSHIP_HTML, "Rate")
    by = {(r["country"], r["post"]): r for r in rows}
    assert by[("ITALY", "Rome")]["pct"] == 0
    assert by[("AFGHANISTAN", "Kabul")]["pct"] == 35


def test_parse_allowance_table_danger_has_effective_date():
    rows = parse_allowance_table(DANGER_HTML, "Rate")
    assert rows[0]["effective_date"] == "2006-04-30"
    assert rows[0]["pct"] == 35


def test_parse_allowance_table_cola_uses_post_allowance_title():
    rows = parse_allowance_table(COLA_HTML, "Post Allowance")
    by = {(r["country"], r["post"]): r["pct"] for r in rows}
    assert by[("ITALY", "Rome")] == 30
    assert by[("AFGHANISTAN", "Kabul")] == 0


def test_merge_resolves_iso_and_combines_three_tables():
    merged = merge_allowance_tables(
        parse_allowance_table(HARDSHIP_HTML, "Rate"),
        parse_allowance_table(DANGER_HTML, "Rate"),
        parse_allowance_table(COLA_HTML, "Post Allowance"),
        default_effective="2026-06-14",
    )
    by = {(m["country_name"], m["post_name"]): m for m in merged}
    rome = by[("ITALY", "Rome")]
    assert rome["country_iso"] == "IT"
    assert rome["post_differential_pct"] == 0.0
    assert rome["danger_pay_pct"] is None  # Rome not in danger table
    assert rome["cola_pct_spendable_income"] == 30.0
    kabul = by[("AFGHANISTAN", "Kabul")]
    assert kabul["country_iso"] == "AF"
    assert kabul["danger_pay_pct"] == 35.0
    assert kabul["effective_date"] == "2006-04-30"  # per-row danger date wins


def test_parse_band_variants():
    assert _parse_band("146,000 and over") == (146000, None)
    assert _parse_band("139,000 - 145,999") == (139000, 145999)
    assert _parse_band("40,000 and under") == (0, 40000)
    assert _parse_band("garbage") is None


def test_parse_spendable_cells():
    cells = ["Annual Base Salary", "1", "2", "3", "4", "5", "6",
             "146,000 and over", "46,500", "52,300", "58,100", "61,000", "66,800", "69,700",
             "100,000 - 105,999", "37,200", "41,800", "46,400", "48,800", "53,400", "55,700"]
    rows = parse_spendable_cells(cells)
    assert len(rows) == 12  # 2 bands x 6 family sizes
    fam1_top = next(r for r in rows if r["salary_min"] == 146000 and r["family_size"] == 1)
    assert fam1_top["annual_spendable_income"] == 46500
    assert fam1_top["salary_max"] is None
    fam1_100k = next(r for r in rows if r["salary_min"] == 100000 and r["family_size"] == 1)
    assert fam1_100k["annual_spendable_income"] == 37200


def test_extract_docx_cells_roundtrip():
    buf = io.BytesIO()
    runs = "".join(f"<w:t>{t}</w:t>" for t in ["A", "", "B", "  ", "C"])
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body>{runs}</w:body></w:document>")
    cells = extract_docx_cells(buf.getvalue())
    assert cells == ["A", "B", "C"]


def test_import_dssr_replace_all_and_query(conn):
    allow = [{
        "country_name": "ITALY", "country_iso": "IT", "post_name": "Rome",
        "post_differential_pct": 0.0, "danger_pay_pct": None,
        "cola_pct_spendable_income": 30.0, "effective_date": "2026-06-14",
        "source_url": "https://allowances.state.gov/Web920/",
    }]
    spend = [{
        "salary_min": 100000, "salary_max": 105999, "family_size": 1,
        "annual_spendable_income": 37200, "effective_date": "2023-01-01",
        "source_url": "https://allowances.state.gov/x.docx",
    }]
    n = import_dssr(conn, allowances=allow, spendable=spend)
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM overseas_post_allowances").fetchone()[0] == 1
    # Re-import replaces rather than duplicating.
    import_dssr(conn, allowances=allow, spendable=spend)
    assert conn.execute("SELECT COUNT(*) FROM overseas_post_allowances").fetchone()[0] == 1


def test_seed_allowances_integrity():
    rows = load_allowance_seed(SEED_ALLOWANCES)
    assert len(rows) > 500  # the full published table, not a stub
    by = {(r["country_iso"], r["post_name"]): r for r in rows}
    kabul = by[("AF", "Kabul")]
    assert kabul["post_differential_pct"] == 35.0
    assert kabul["danger_pay_pct"] == 35.0
    assert kabul["cola_pct_spendable_income"] == 0.0
    assert by[("AT", "Vienna")]["cola_pct_spendable_income"] == 60.0
    assert by[("CH", "Bern")]["cola_pct_spendable_income"] == 120.0


def test_seed_spendable_integrity():
    rows = load_spendable_seed(SEED_SPENDABLE)
    assert len(rows) == 132  # 22 bands x 6 family sizes
    top = next(r for r in rows if r["salary_max"] is None and r["family_size"] == 1)
    assert top["annual_spendable_income"] == 46500


def test_gather_rows_falls_back_to_seed_when_live_fails():
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    allow, spend, label = gather_rows(use_live=True, fetch=boom)
    assert label == "seed"
    assert len(allow) > 500
    assert len(spend) == 132


def test_gather_rows_offline_uses_seed_without_fetch():
    allow, spend, label = gather_rows(use_live=False)
    assert label == "seed"
    assert allow and spend
