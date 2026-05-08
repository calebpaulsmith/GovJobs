from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.data_import import ImportResult
from src.data_recon import Recommendation
from src.public_map_corpus import (
    TOP_25_AGENCY_CODES,
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
