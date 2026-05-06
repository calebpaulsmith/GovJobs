"""Reconnaissance step. Estimates dataset sizes before any full download.

Run as `python -m src.data_recon`. Without USAJOBS credentials in `.env`,
this script falls back to documented order-of-magnitude estimates and is
explicit about that in the recon log. It does NOT download the full
dataset under any circumstance.

Public surface:

- `Thresholds`            — frozen dataclass loaded from Config.
- `DatasetEstimate`       — frozen dataclass for one dataset's size estimate.
- `Recommendation`        — frozen dataclass: mode + reason + next action.
- `recommend_mode(...)`   — pure function. Tested in tests/test_data_recon.py.
- `probe_*`               — best-effort network probes; degrade gracefully.
- `update_strategy_doc`   — rewrites the "## Recon log" section of
                            docs/DOWNLOAD_STRATEGY.md.
- `run_recon`             — entry point used by `python -m src.data_recon`.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

# config.py lives at the repo root; make it importable when run as a module.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import Config, load_config  # noqa: E402
from src.logging_utils import get_logger, setup_logging  # noqa: E402

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants — order-of-magnitude defaults used when probing isn't possible.
# Recon overwrites these with observed values when credentials are present.

USAJOBS_HOST = "https://data.usajobs.gov"

DEFAULT_HISTORIC_TOTAL_RECORDS = 4_000_000
DEFAULT_HISTORIC_AVG_BYTES_PER_RECORD = 4_000   # ~4 KB compact record
DEFAULT_HISTORIC_DB_BYTES_PER_RECORD = 1_500    # ~1.5 KB after normalization
DEFAULT_RECORDS_PER_HOUR = 200_000              # safe sustained throughput

DEFAULT_SEARCH_TOTAL_RECORDS = 50_000
DEFAULT_SEARCH_AVG_BYTES = 5_000
DEFAULT_SEARCH_DB_BYTES = 1_500

DEFAULT_TEXT_AVG_BYTES = 30_000

DEFAULT_OPM_FEDSCOPE_BYTES = 2_000_000_000
DEFAULT_OPM_FEDSCOPE_ROWS = 10_000_000

VALID_MODES = (
    "FULL_DOWNLOAD",
    "FOCUSED_FULL_DOWNLOAD",
    "STAGED_DOWNLOAD",
    "SAMPLE_ONLY",
)


# ---------------------------------------------------------------------------
# Dataclasses


@dataclass(frozen=True)
class Thresholds:
    max_full_download_gb: float
    max_database_gb: float
    max_full_download_rows: int
    max_import_hours: float

    @classmethod
    def from_config(cls, c: Config) -> "Thresholds":
        return cls(
            max_full_download_gb=c.max_full_download_gb,
            max_database_gb=c.max_database_gb,
            max_full_download_rows=c.max_full_download_rows,
            max_import_hours=c.max_import_hours,
        )


@dataclass(frozen=True)
class DatasetEstimate:
    dataset: str
    endpoint: str
    date_range: Optional[tuple[str, str]] = None
    estimated_records: Optional[int] = None
    estimated_raw_bytes: Optional[int] = None
    estimated_db_bytes: Optional[int] = None
    estimated_import_hours: Optional[float] = None
    api_limits_note: str = ""
    confidence: str = "low"  # low | medium | high
    probed: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Recommendation:
    mode: str
    reason: str
    next_action: str


# ---------------------------------------------------------------------------
# Recommendation logic — pure, deterministic, fully tested.


def _gb(n_bytes: Optional[int]) -> float:
    return (n_bytes or 0) / 1_000_000_000


def _within_all(
    *,
    raw_gb: float,
    db_gb: float,
    rows: int,
    hours: float,
    t: Thresholds,
) -> bool:
    return (
        raw_gb <= t.max_full_download_gb
        and db_gb <= t.max_database_gb
        and rows <= t.max_full_download_rows
        and hours <= t.max_import_hours
    )


def _list_breaches(raw_gb: float, db_gb: float, rows: int, hours: float, t: Thresholds) -> str:
    bits: list[str] = []
    if raw_gb > t.max_full_download_gb:
        bits.append(f"raw {raw_gb:.1f}GB > {t.max_full_download_gb}GB")
    if db_gb > t.max_database_gb:
        bits.append(f"db {db_gb:.1f}GB > {t.max_database_gb}GB")
    if rows > t.max_full_download_rows:
        bits.append(f"rows {rows:,} > {t.max_full_download_rows:,}")
    if hours > t.max_import_hours:
        bits.append(f"hours {hours:.1f} > {t.max_import_hours}")
    return ", ".join(bits) or "(none)"


def recommend_mode(
    estimate: DatasetEstimate,
    thresholds: Thresholds,
    *,
    focused_factor: float = 0.20,
    staged_max_passes: float = 10.0,
) -> Recommendation:
    """Pick a download mode for one dataset.

    Mode order:

    1. ``FULL_DOWNLOAD`` — everything fits in one pass.
    2. ``FOCUSED_FULL_DOWNLOAD`` — a focused subset (target agencies / series /
       last 5 years) of size ~``focused_factor`` × full fits in one pass.
    3. ``STAGED_DOWNLOAD`` — full doesn't fit; per-pass slice is feasible and
       total passes is ≤ ``staged_max_passes``; final DB still fits.
    4. ``SAMPLE_ONLY`` — even staged is impractical, OR record count unknown.

    The function is pure: same inputs ⇒ same outputs. No I/O.
    """
    if estimate.estimated_records is None:
        return Recommendation(
            "SAMPLE_ONLY",
            "Record count could not be estimated; cannot guarantee a full pull will fit.",
            "Re-run recon with broader probes; meanwhile pull a representative sample.",
        )

    raw_gb = _gb(estimate.estimated_raw_bytes)
    db_gb = _gb(estimate.estimated_db_bytes)
    rows = int(estimate.estimated_records)
    hours = float(estimate.estimated_import_hours or 0.0)

    if _within_all(raw_gb=raw_gb, db_gb=db_gb, rows=rows, hours=hours, t=thresholds):
        return Recommendation(
            "FULL_DOWNLOAD",
            "All four estimates (raw size, DB size, row count, import hours) "
            "are within configured thresholds.",
            "Run the historic importer with the full date range; record progress in import_manifests.",
        )

    f_raw = raw_gb * focused_factor
    f_db = db_gb * focused_factor
    f_rows = int(rows * focused_factor)
    f_hours = hours * focused_factor
    if _within_all(raw_gb=f_raw, db_gb=f_db, rows=f_rows, hours=f_hours, t=thresholds):
        breaches = _list_breaches(raw_gb, db_gb, rows, hours, thresholds)
        return Recommendation(
            "FOCUSED_FULL_DOWNLOAD",
            f"Full breaches {breaches}. A focused slice (~{int(focused_factor * 100)}% of full, "
            "scoped to target agencies and series) fits.",
            "Run a focused import: FEMA / DHS / CISA / HUD / FIMA / USACE / EPA / USDA / DOI / DOT / "
            "HHS / EDA / SBA, plus series 0089, 0301, 0343, 1109, 0020, 0101, 0110, 0300, 0501, 0560.",
        )

    passes_by_raw = (raw_gb / thresholds.max_full_download_gb) if thresholds.max_full_download_gb else 1.0
    passes_by_rows = rows / thresholds.max_full_download_rows
    passes_by_hours = (hours / thresholds.max_import_hours) if thresholds.max_import_hours else 1.0
    passes_needed = max(passes_by_raw, passes_by_rows, passes_by_hours)
    final_db_fits = db_gb <= thresholds.max_database_gb

    if passes_needed <= staged_max_passes and final_db_fits:
        return Recommendation(
            "STAGED_DOWNLOAD",
            f"Full dataset too large for one pass (~{passes_needed:.1f} passes needed); each pass "
            f"fits when sliced by date or agency, and the final DB ({db_gb:.1f} GB) fits.",
            "Stage in this order: last 12 months → last 5 years for target agencies/series → full "
            "history for those → full federal historical structured records if time permits → "
            "AnnouncementText only for selected/high-value records.",
        )

    reason_bits: list[str] = []
    if not final_db_fits:
        reason_bits.append(f"final DB {db_gb:.1f} GB exceeds limit {thresholds.max_database_gb} GB")
    if passes_needed > staged_max_passes:
        reason_bits.append(f"{passes_needed:.1f} passes needed (>{staged_max_passes:.0f})")
    return Recommendation(
        "SAMPLE_ONLY",
        "Even a staged pull is impractical: " + "; ".join(reason_bits) + ".",
        "Pull a representative sample (current jobs, FEMA/DHS, GS-13/14/15, remote, Chicago/Midwest, "
        "and non-matches for scoring tests). See Project_Start.md §SAMPLE_ONLY.",
    )


# ---------------------------------------------------------------------------
# Probes — best effort. Use a typed callable so tests can inject a stub.

HttpGet = Callable[[str, dict, dict], "object"]


def _make_http_get(timeout: float = 15.0):
    """Return a callable that wraps requests.get. Imported lazily so that
    pure-logic tests don't need the requests package available."""
    import requests  # noqa: WPS433 - intentional local import

    def _get(url: str, params: dict, headers: dict):
        return requests.get(url, params=params, headers=headers, timeout=timeout)

    return _get


def _usajobs_headers(config: Config, *, include_auth: bool = True) -> dict:
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": config.usajobs_user_agent or "GovJobs local recon",
    }
    if include_auth and config.usajobs_authorization_key:
        headers["Authorization-Key"] = config.usajobs_authorization_key
    return headers


def probe_usajobs_search(
    config: Config, http_get: Optional[HttpGet] = None
) -> DatasetEstimate:
    """Return an estimate for the current Search API. Falls back to documented
    estimates if credentials are missing or the probe fails."""
    if not config.has_usajobs_credentials:
        log.warning("USAJOBS credentials missing; using documented estimate for Search.")
        records = DEFAULT_SEARCH_TOTAL_RECORDS
        return DatasetEstimate(
            dataset="USAJOBS Search (current open JOAs)",
            endpoint="GET /api/Search",
            estimated_records=records,
            estimated_raw_bytes=records * DEFAULT_SEARCH_AVG_BYTES,
            estimated_db_bytes=records * DEFAULT_SEARCH_DB_BYTES,
            estimated_import_hours=records / DEFAULT_RECORDS_PER_HOUR,
            api_limits_note="Documented estimate; no credentials.",
            confidence="low",
            probed=False,
            notes="No credentials — fell back to documented order-of-magnitude estimate.",
        )

    http_get = http_get or _make_http_get()
    try:
        resp = http_get(
            f"{USAJOBS_HOST}/api/Search",
            {"ResultsPerPage": 1, "Page": 1},
            _usajobs_headers(config),
        )
        resp.raise_for_status()  # type: ignore[attr-defined]
        data = resp.json()  # type: ignore[attr-defined]
        sr = data.get("SearchResult", {}) if isinstance(data, dict) else {}
        count = sr.get("SearchResultCountAll") or sr.get("SearchResultCount")
        records = int(count) if count is not None else DEFAULT_SEARCH_TOTAL_RECORDS
    except Exception as e:  # pragma: no cover - defensive; tests stub network
        log.exception("Search probe failed: %s", e)
        return DatasetEstimate(
            dataset="USAJOBS Search (current open JOAs)",
            endpoint="GET /api/Search",
            api_limits_note=f"Probe error: {e}",
            confidence="low",
            probed=True,
            notes="Probe raised an exception. Verify credentials and network.",
        )

    return DatasetEstimate(
        dataset="USAJOBS Search (current open JOAs)",
        endpoint="GET /api/Search",
        estimated_records=records,
        estimated_raw_bytes=records * DEFAULT_SEARCH_AVG_BYTES,
        estimated_db_bytes=records * DEFAULT_SEARCH_DB_BYTES,
        estimated_import_hours=records / DEFAULT_RECORDS_PER_HOUR,
        api_limits_note="Probed Search count via SearchResultCountAll.",
        confidence="medium",
        probed=True,
    )


def probe_historic_joa(
    config: Config, http_get: Optional[HttpGet] = None
) -> DatasetEstimate:
    """Estimate HistoricJoa size from the public bulk endpoint."""
    http_get = http_get or _make_http_get()
    try:
        resp = http_get(
            f"{USAJOBS_HOST}/api/HistoricJoa",
            {},
            _usajobs_headers(config, include_auth=False),
        )
        resp.raise_for_status()  # type: ignore[attr-defined]
        payload = resp.json()  # type: ignore[attr-defined]
        paging = payload.get("paging", {}) if isinstance(payload, dict) else {}
        metadata = paging.get("metadata", {}) if isinstance(paging, dict) else {}
        data_list = payload.get("data", []) if isinstance(payload, dict) else []
        records = int(metadata["totalCount"])
        returned = len(data_list) if isinstance(data_list, list) else int(metadata.get("pageSize") or 1)
        content = getattr(resp, "content", None)
        size_bytes = len(content) if content else len(json.dumps(payload).encode())
        avg_bytes = size_bytes / max(returned, 1)
        now = dt.datetime.now(dt.timezone.utc)
        return DatasetEstimate(
            dataset="USAJOBS HistoricJoa",
            endpoint="GET /api/HistoricJoa",
            date_range=("all available", f"{now:%Y-%m-%d}"),
            estimated_records=records,
            estimated_raw_bytes=int(records * avg_bytes),
            estimated_db_bytes=int(records * DEFAULT_HISTORIC_DB_BYTES_PER_RECORD),
            estimated_import_hours=records / DEFAULT_RECORDS_PER_HOUR,
            api_limits_note="Public endpoint; probed unfiltered totalCount and first-page byte size.",
            confidence="high",
            probed=True,
        )
    except Exception as e:
        log.warning("HistoricJoa public probe failed: %s", e)

    records = DEFAULT_HISTORIC_TOTAL_RECORDS
    return DatasetEstimate(
        dataset="USAJOBS HistoricJoa",
        endpoint="GET /api/HistoricJoa",
        estimated_records=records,
        estimated_raw_bytes=records * DEFAULT_HISTORIC_AVG_BYTES_PER_RECORD,
        estimated_db_bytes=records * DEFAULT_HISTORIC_DB_BYTES_PER_RECORD,
        estimated_import_hours=records / DEFAULT_RECORDS_PER_HOUR,
        api_limits_note="Public probe failed; documented estimate.",
        confidence="low",
        probed=True,
        notes="Probe returned no usable count. Verify endpoint availability.",
    )


def probe_announcement_text(
    config: Config, http_get: Optional[HttpGet] = None
) -> DatasetEstimate:
    """AnnouncementText is selective by design — total population isn't pulled.
    The estimate reports per-record cost rather than a total."""
    note = "Pulled selectively (saved jobs, high-match jobs, recent jobs, RAG-flagged)."
    return DatasetEstimate(
        dataset="USAJOBS AnnouncementText",
        endpoint="GET /api/HistoricJoa/AnnouncementText",
        estimated_records=None,
        estimated_raw_bytes=None,
        estimated_db_bytes=None,
        estimated_import_hours=None,
        api_limits_note=f"~{DEFAULT_TEXT_AVG_BYTES} bytes/record (est.); selective import only.",
        confidence="low",
        probed=False,
        notes=note,
    )


def probe_opm_workforce() -> DatasetEstimate:
    """OPM workforce data is file-based. V1 uses documented estimates until
    the OPM importer is built; recon will revisit."""
    return DatasetEstimate(
        dataset="OPM Federal Workforce",
        endpoint="File downloads via data.opm.gov / FedScope",
        estimated_records=DEFAULT_OPM_FEDSCOPE_ROWS,
        estimated_raw_bytes=DEFAULT_OPM_FEDSCOPE_BYTES,
        estimated_db_bytes=int(DEFAULT_OPM_FEDSCOPE_BYTES * 0.4),
        estimated_import_hours=DEFAULT_OPM_FEDSCOPE_ROWS / DEFAULT_RECORDS_PER_HOUR,
        api_limits_note="File download (no API rate limit).",
        confidence="low",
        probed=False,
        notes="Placeholder estimates. Inspect data.opm.gov downloads to refine.",
    )


# ---------------------------------------------------------------------------
# Strategy doc updater


def render_recon_block(
    estimate: DatasetEstimate, recommendation: Recommendation, ts: str
) -> str:
    raw_gb = _gb(estimate.estimated_raw_bytes)
    db_gb = _gb(estimate.estimated_db_bytes)
    rows = estimate.estimated_records
    hrs = estimate.estimated_import_hours
    rows_str = f"{rows:,}" if rows is not None else "?"
    hrs_str = f"{hrs:.2f} h" if hrs is not None else "?"
    raw_str = f"{raw_gb:.2f} GB" if estimate.estimated_raw_bytes is not None else "?"
    db_str = f"{db_gb:.2f} GB" if estimate.estimated_db_bytes is not None else "?"
    date_range = (
        f"{estimate.date_range[0]} → {estimate.date_range[1]}" if estimate.date_range else "n/a"
    )
    return (
        "```text\n"
        f"Run timestamp:       {ts}\n"
        f"Dataset:             {estimate.dataset}\n"
        f"Endpoint:            {estimate.endpoint}\n"
        f"Date range:          {date_range}\n"
        f"Estimated records:   {rows_str}\n"
        f"Estimated raw size:  {raw_str}\n"
        f"Estimated DB size:   {db_str}\n"
        f"Estimated import:    {hrs_str}\n"
        f"API limits:          {estimate.api_limits_note}\n"
        f"Confidence:          {estimate.confidence}\n"
        f"Probed:              {estimate.probed}\n"
        f"Recommended mode:    {recommendation.mode}\n"
        f"Reason:              {recommendation.reason}\n"
        f"Next action:         {recommendation.next_action}\n"
        f"Notes:               {estimate.notes}\n"
        "```\n"
    )


_RECON_LOG_HEADER = "## Recon log"


def update_strategy_doc(strategy_path: Path, blocks: Iterable[str]) -> None:
    """Replace the body of the '## Recon log' section with the given blocks.

    Idempotent: every run re-writes the section. Anything before the section
    (the dataset placeholders, decision tree, etc.) is preserved verbatim, as
    is anything after the section (e.g. `## User approval gate`).
    """
    text = strategy_path.read_text(encoding="utf-8")
    blocks_str = "\n".join(blocks).rstrip() + "\n"

    idx = text.find(_RECON_LOG_HEADER)
    new_section = (
        f"{_RECON_LOG_HEADER}\n\n"
        "Most recent run rewrites this section. Each block represents one dataset.\n\n"
        f"{blocks_str}"
    )

    if idx == -1:
        new_text = text.rstrip() + "\n\n" + new_section + "\n"
    else:
        before = text[:idx]
        rest = text[idx + len(_RECON_LOG_HEADER):]
        next_match = re.search(r"\n## ", rest)
        after = rest[next_match.start():] if next_match else ""
        new_text = before + new_section + after

    strategy_path.write_text(new_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point


def run_recon(
    config: Optional[Config] = None,
    *,
    write_doc: bool = True,
    http_get: Optional[HttpGet] = None,
) -> list[tuple[DatasetEstimate, Recommendation]]:
    config = config or load_config()
    setup_logging(level=config.log_level, log_file=config.log_file)
    thresholds = Thresholds.from_config(config)

    log.info("Recon start. Thresholds: %s", thresholds)
    log.info("USAJOBS credentials present: %s", config.has_usajobs_credentials)

    estimates: list[DatasetEstimate] = [
        probe_usajobs_search(config, http_get=http_get),
        probe_historic_joa(config, http_get=http_get),
        probe_announcement_text(config, http_get=http_get),
        probe_opm_workforce(),
    ]

    results: list[tuple[DatasetEstimate, Recommendation]] = []
    for est in estimates:
        rec = recommend_mode(est, thresholds)
        log.info("[%s] %s — %s", est.dataset, rec.mode, rec.reason)
        results.append((est, rec))

    if write_doc:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        blocks = [render_recon_block(e, r, ts) for e, r in results]
        strategy_path = _REPO_ROOT / "docs" / "DOWNLOAD_STRATEGY.md"
        update_strategy_doc(strategy_path, blocks)
        log.info("Wrote recon log to %s", strategy_path)

    return results


if __name__ == "__main__":
    run_recon()
