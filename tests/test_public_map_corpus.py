from __future__ import annotations

import sqlite3
from datetime import date
from types import SimpleNamespace

from src.data_import import ImportResult
from src.data_recon import Recommendation
from src.public_map_corpus import (
    TOP_25_AGENCY_CODES,
    department_codes_from_db,
    run_public_map_corpus_preset,
    trailing_90_closed_params,
)


def test_trailing_90_closed_params():
    params = trailing_90_closed_params(today=date(2026, 5, 8))
    assert params == {
        "StartPositionCloseDate": "2026-02-07",
        "EndPositionCloseDate": "2026-05-08",
    }


def test_federal_current_preset_runs_recon_then_current_import(monkeypatch):
    calls = []

    def fake_current(conn, config, query_params, *, max_pages):
        calls.append((query_params, max_pages))
        return ImportResult(pages_completed=2, records_imported=1000, manifest_id=7)

    monkeypatch.setattr("src.public_map_corpus.import_current_search", fake_current)

    result = run_public_map_corpus_preset(
        object(),
        SimpleNamespace(),
        "federal_current",
        current_max_pages=2,
        run_recon_fn=lambda config: [Recommendation("STAGED_DOWNLOAD", "ok", "go")],
    )

    assert calls == [({}, 2)]
    assert result.records_imported == 1000
    assert result.manifest_ids == [7]
    assert result.recon_modes == ["STAGED_DOWNLOAD"]


def test_top_25_preset_runs_one_current_scope_per_agency(monkeypatch):
    calls = []

    def fake_current(conn, config, query_params, *, max_pages):
        calls.append(query_params)
        return ImportResult(pages_completed=1, records_imported=3, manifest_id=None)

    monkeypatch.setattr("src.public_map_corpus.import_current_search", fake_current)

    result = run_public_map_corpus_preset(
        object(),
        SimpleNamespace(),
        "top_25_current",
        current_max_pages=1,
        run_recon_fn=lambda config: [],
    )

    assert len(calls) == len(TOP_25_AGENCY_CODES)
    assert calls[0] == {"Organization": TOP_25_AGENCY_CODES[0]}
    assert result.records_imported == len(TOP_25_AGENCY_CODES) * 3


def _conn_with_agencies(rows: list[tuple[str, str | None, int]]) -> sqlite3.Connection:
    """Build an in-memory agency_codes table for slicing tests."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE agency_codes (code TEXT, name TEXT, department_code TEXT, "
        "department_name TEXT, active INTEGER, source TEXT, updated_at TEXT)"
    )
    conn.executemany(
        "INSERT INTO agency_codes (code, department_code, department_name, active) "
        "VALUES (?, ?, ?, ?)",
        [(r[0], r[1], r[1] or "", r[2]) for r in rows],
    )
    return conn


def test_department_codes_from_db_dedups_and_excludes_blanks_and_inactive():
    conn = _conn_with_agencies(
        [
            ("VATA", "VA", 1),
            ("VAXY", "VA", 1),  # duplicate department
            ("HSCB", "HS", 1),
            ("FOO0", None, 1),  # null department code
            ("BAR0", "", 1),    # blank department code
            ("OLD0", "OLD", 0),  # inactive
        ]
    )
    assert department_codes_from_db(conn) == ["HS", "VA"]


def test_federal_full_by_department_iterates_one_search_per_department(monkeypatch):
    conn = _conn_with_agencies(
        [
            ("VATA", "VA", 1),
            ("HSCB", "HS", 1),
            ("ARXA", "AR", 1),
        ]
    )
    calls = []

    def fake_current(conn_arg, config, query_params, *, max_pages):
        calls.append((query_params, max_pages))
        return ImportResult(pages_completed=3, records_imported=900, manifest_id=len(calls))

    monkeypatch.setattr("src.public_map_corpus.import_current_search", fake_current)

    result = run_public_map_corpus_preset(
        conn,
        SimpleNamespace(),
        "federal_full_by_department",
        current_max_pages=20,
        run_recon_fn=lambda config: [],
    )

    assert calls == [
        ({"Organization": "AR"}, 20),
        ({"Organization": "HS"}, 20),
        ({"Organization": "VA"}, 20),
    ]
    assert result.records_imported == 3 * 900
    assert result.pages_completed == 3 * 3
    assert sorted(result.manifest_ids) == [1, 2, 3]


def test_historic_closed_preset_uses_close_date_window(monkeypatch):
    calls = []

    def fake_historic(conn, config, query_params, *, max_pages, download_mode):
        calls.append((query_params, max_pages, download_mode))
        return ImportResult(pages_completed=4, records_imported=2500, manifest_id=11)

    monkeypatch.setattr("src.public_map_corpus.import_historic_joa", fake_historic)

    result = run_public_map_corpus_preset(
        object(),
        SimpleNamespace(),
        "historic_closed_90",
        historic_max_pages=4,
        today=date(2026, 5, 8),
        run_recon_fn=lambda config: [],
    )

    assert calls == [
        (
            {
                "StartPositionCloseDate": "2026-02-07",
                "EndPositionCloseDate": "2026-05-08",
            },
            4,
            "FOCUSED_FULL_DOWNLOAD",
        )
    ]
    assert result.records_imported == 2500
    assert result.manifest_ids == [11]
