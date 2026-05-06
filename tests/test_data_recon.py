"""Unit tests for src.data_recon.

Focus: the pure recommendation logic and the strategy-doc updater. No
network calls. No real config file. Probes are tested only at the level
of the credentials-missing fallback (where they should produce a
DatasetEstimate without contacting USAJOBS).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from config import Config
from src.data_recon import (
    DatasetEstimate,
    Recommendation,
    Thresholds,
    _RECON_LOG_HEADER,
    probe_announcement_text,
    probe_historic_joa,
    probe_opm_workforce,
    probe_usajobs_search,
    recommend_mode,
    render_recon_block,
    update_strategy_doc,
)


# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture
def thresholds() -> Thresholds:
    return Thresholds(
        max_full_download_gb=5.0,
        max_database_gb=10.0,
        max_full_download_rows=5_000_000,
        max_import_hours=8.0,
    )


def _est(**overrides) -> DatasetEstimate:
    base = dict(
        dataset="Test",
        endpoint="GET /test",
        estimated_records=1_000_000,
        estimated_raw_bytes=1_000_000_000,        # 1 GB
        estimated_db_bytes=500_000_000,           # 0.5 GB
        estimated_import_hours=2.0,
    )
    base.update(overrides)
    return DatasetEstimate(**base)


def _no_creds_config(tmp_path: Path) -> Config:
    return Config(
        usajobs_user_agent=None,
        usajobs_authorization_key=None,
        database_path=tmp_path / "db.sqlite",
        raw_data_path=tmp_path / "raw",
        processed_data_path=tmp_path / "processed",
        max_full_download_gb=5.0,
        max_database_gb=10.0,
        max_full_download_rows=5_000_000,
        max_import_hours=8.0,
        log_level="WARNING",
        log_file=tmp_path / "app.log",
    )


# ---------------------------------------------------------------------------
# recommend_mode — happy paths


def test_full_download_when_within_all_thresholds(thresholds):
    est = _est(
        estimated_records=100_000,
        estimated_raw_bytes=200_000_000,   # 0.2 GB
        estimated_db_bytes=100_000_000,    # 0.1 GB
        estimated_import_hours=0.5,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "FULL_DOWNLOAD"
    assert "within configured thresholds" in rec.reason


def test_at_exact_thresholds_is_full_download(thresholds):
    est = _est(
        estimated_records=thresholds.max_full_download_rows,
        estimated_raw_bytes=int(thresholds.max_full_download_gb * 1_000_000_000),
        estimated_db_bytes=int(thresholds.max_database_gb * 1_000_000_000),
        estimated_import_hours=thresholds.max_import_hours,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "FULL_DOWNLOAD"


# ---------------------------------------------------------------------------
# recommend_mode — unknown estimates


def test_unknown_records_falls_back_to_sample_only(thresholds):
    est = _est(estimated_records=None)
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "SAMPLE_ONLY"
    assert "could not be estimated" in rec.reason


# ---------------------------------------------------------------------------
# recommend_mode — focused subset fits


def test_focused_when_full_breaches_one_threshold(thresholds):
    """Full breaches raw size and rows, but a 20% slice fits."""
    est = _est(
        estimated_records=10_000_000,         # > 5M; 20% = 2M (fits)
        estimated_raw_bytes=8_000_000_000,    # 8 GB > 5 GB; 20% = 1.6 GB (fits)
        estimated_db_bytes=4_000_000_000,     # 4 GB (fits)
        estimated_import_hours=4.0,           # 20% = 0.8h (fits)
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "FOCUSED_FULL_DOWNLOAD"
    assert "FEMA" in rec.next_action  # focused targets named


def test_focused_when_only_rows_breach(thresholds):
    est = _est(
        estimated_records=10_000_000,
        estimated_raw_bytes=1_000_000_000,
        estimated_db_bytes=500_000_000,
        estimated_import_hours=1.0,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "FOCUSED_FULL_DOWNLOAD"


# ---------------------------------------------------------------------------
# recommend_mode — staged


def test_staged_when_focused_does_not_fit_but_per_pass_does(thresholds):
    """Focused (20%) doesn't fit on rows (~7M > 5M), but passes ≤ 10."""
    est = _est(
        estimated_records=35_000_000,         # focused 7M (>5M → focused fails); passes by rows = 7
        estimated_raw_bytes=2_000_000_000,    # tiny; focused fits, but rows dominates
        estimated_db_bytes=2_000_000_000,     # final DB 2 GB (fits)
        estimated_import_hours=4.0,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "STAGED_DOWNLOAD"
    assert "passes needed" in rec.reason


def test_staged_when_raw_dominates_passes(thresholds):
    est = _est(
        estimated_records=4_000_000,           # within
        estimated_raw_bytes=40_000_000_000,    # 40 GB → passes by raw = 8 (focused fails: 8 GB > 5)
        estimated_db_bytes=8_000_000_000,      # 8 GB final DB fits
        estimated_import_hours=2.0,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "STAGED_DOWNLOAD"


# ---------------------------------------------------------------------------
# recommend_mode — sample only


def test_sample_only_when_passes_exceed_limit(thresholds):
    est = _est(
        estimated_records=60_000_000,          # passes by rows = 12 (>10)
        estimated_raw_bytes=2_000_000_000,
        estimated_db_bytes=2_000_000_000,
        estimated_import_hours=4.0,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "SAMPLE_ONLY"
    assert "passes needed" in rec.reason


def test_sample_only_when_final_db_exceeds_limit(thresholds):
    est = _est(
        estimated_records=20_000_000,          # focused fails (4M)? actually 4M fits.
        # Force focused to fail with raw too:
        estimated_raw_bytes=30_000_000_000,    # 30 GB → focused 6 GB (>5 → focused fails); passes 6
        estimated_db_bytes=15_000_000_000,     # 15 GB > 10 GB threshold → STAGED rejected
        estimated_import_hours=4.0,
    )
    rec = recommend_mode(est, thresholds)
    assert rec.mode == "SAMPLE_ONLY"
    assert "exceeds limit" in rec.reason


# ---------------------------------------------------------------------------
# recommend_mode — parameter overrides


def test_focused_factor_can_be_tuned(thresholds):
    """A wider focused factor (50%) can rescue datasets that wouldn't fit at 20%."""
    est = _est(
        estimated_records=8_000_000,           # 50% = 4M fits; 20% would have fit too
        estimated_raw_bytes=12_000_000_000,    # 50% = 6 GB still fails; 20% = 2.4 GB fits
        estimated_db_bytes=4_000_000_000,
        estimated_import_hours=4.0,
    )
    rec_default = recommend_mode(est, thresholds)
    assert rec_default.mode == "FOCUSED_FULL_DOWNLOAD"
    # Force focused_factor=0.5 (less aggressive). Now focused 50% fails on raw → staged.
    rec_loose = recommend_mode(est, thresholds, focused_factor=0.5)
    assert rec_loose.mode in ("STAGED_DOWNLOAD", "SAMPLE_ONLY")


# ---------------------------------------------------------------------------
# render_recon_block — formatting


def test_render_block_includes_all_fields(thresholds):
    est = _est()
    rec = recommend_mode(est, thresholds)
    block = render_recon_block(est, rec, "2026-05-04T12:00:00Z")
    assert block.startswith("```text\n")
    assert block.endswith("```\n")
    assert "Run timestamp:       2026-05-04T12:00:00Z" in block
    assert "Recommended mode:    " + rec.mode in block
    assert "Estimated records:   1,000,000" in block


def test_render_block_handles_unknown_estimates():
    est = DatasetEstimate(
        dataset="Selective",
        endpoint="GET /api/AnnouncementText",
        estimated_records=None,
        estimated_raw_bytes=None,
        estimated_db_bytes=None,
        estimated_import_hours=None,
    )
    rec = Recommendation("SAMPLE_ONLY", "no records", "do nothing")
    block = render_recon_block(est, rec, "ts")
    assert "Estimated records:   ?" in block
    assert "Estimated import:    ?" in block


# ---------------------------------------------------------------------------
# update_strategy_doc — idempotent rewrite


def test_update_strategy_doc_replaces_recon_log_section(tmp_path: Path):
    p = tmp_path / "DOWNLOAD_STRATEGY.md"
    p.write_text(
        "# Title\n\n"
        "## Some other section\n\n"
        "Body.\n\n"
        f"{_RECON_LOG_HEADER}\n\n"
        "[no recon runs recorded]\n\n"
        "## User approval gate\n\n"
        "Approval text.\n",
        encoding="utf-8",
    )

    update_strategy_doc(p, ["BLOCK_A\n", "BLOCK_B\n"])
    text1 = p.read_text(encoding="utf-8")
    assert "[no recon runs recorded]" not in text1
    assert "BLOCK_A" in text1 and "BLOCK_B" in text1
    assert "## User approval gate" in text1
    assert "## Some other section" in text1

    # Idempotent: replace again with new blocks. Old blocks are gone.
    update_strategy_doc(p, ["BLOCK_C\n"])
    text2 = p.read_text(encoding="utf-8")
    assert "BLOCK_A" not in text2 and "BLOCK_B" not in text2
    assert "BLOCK_C" in text2
    assert "## User approval gate" in text2


def test_update_strategy_doc_appends_section_if_missing(tmp_path: Path):
    p = tmp_path / "DOWNLOAD_STRATEGY.md"
    p.write_text("# Title\n\nNo recon log here.\n", encoding="utf-8")
    update_strategy_doc(p, ["BLOCK_X\n"])
    text = p.read_text(encoding="utf-8")
    assert _RECON_LOG_HEADER in text
    assert "BLOCK_X" in text


# ---------------------------------------------------------------------------
# Probes — fallback behavior when credentials are missing


def test_probe_search_falls_back_without_credentials(tmp_path):
    cfg = _no_creds_config(tmp_path)
    est = probe_usajobs_search(cfg, http_get=None)
    assert est.probed is False
    assert est.estimated_records is not None
    assert "no credentials" in est.notes.lower()


def test_probe_historic_falls_back_without_credentials(tmp_path):
    cfg = _no_creds_config(tmp_path)
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        content = b'{"paging":{"metadata":{"totalCount":3133132,"pageSize":500}},"data":[{},{}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "paging": {"metadata": {"totalCount": 3_133_132, "pageSize": 500}},
                "data": [{}, {}],
            }

    def fake_get(url, params, headers):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _FakeResp()

    est = probe_historic_joa(cfg, http_get=fake_get)
    assert est.probed is True
    assert est.confidence == "high"
    assert est.estimated_records == 3_133_132
    assert captured["url"].endswith("/api/HistoricJoa")
    assert captured["params"] == {}
    assert "Authorization-Key" not in captured["headers"]


def test_probe_announcement_text_is_selective(tmp_path):
    cfg = _no_creds_config(tmp_path)
    est = probe_announcement_text(cfg, http_get=None)
    assert est.estimated_records is None  # selective by design


def test_probe_opm_returns_estimates():
    est = probe_opm_workforce()
    assert est.estimated_records is not None
    assert est.estimated_raw_bytes is not None


# ---------------------------------------------------------------------------
# Probe — search uses injected http_get when credentials present


def test_probe_search_uses_injected_http_get(tmp_path):
    cfg = Config(
        usajobs_user_agent="real@user.test",
        usajobs_authorization_key="real-key",
        database_path=tmp_path / "db.sqlite",
        raw_data_path=tmp_path / "raw",
        processed_data_path=tmp_path / "processed",
        max_full_download_gb=5.0,
        max_database_gb=10.0,
        max_full_download_rows=5_000_000,
        max_import_hours=8.0,
        log_level="WARNING",
        log_file=tmp_path / "app.log",
    )
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        content = b'{"SearchResult":{"SearchResultCountAll":42000}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"SearchResult": {"SearchResultCountAll": 42_000}}

    def fake_get(url, params, headers):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _FakeResp()

    est = probe_usajobs_search(cfg, http_get=fake_get)
    assert est.estimated_records == 42_000
    assert est.probed is True
    assert captured["url"].endswith("/api/Search")
    assert captured["headers"]["Authorization-Key"] == "real-key"
