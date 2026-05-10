"""Corpus-growth presets for the public map.

D.5.7 needs larger, reproducible import scopes before the public map can be
evaluated honestly. These helpers keep the Streamlit page thin while preserving
the repo rule that large imports pass through reconnaissance first.

USAJOBS Search caps total returnable results at 10,000 per query (its paging
window stops there even if more rows match). To get federal-wide coverage
beyond that, the ``federal_full_by_department`` preset iterates every active
department code in ``agency_codes`` and runs a separate Search per slice.
Each per-department slice is well under 10K so the full corpus comes through.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Mapping

from config import Config
from src.data_import import ImportResult, import_current_search, import_historic_joa
from src.data_recon import Recommendation, run_recon

TOP_25_AGENCY_CODES = [
    "VA",
    "AR",
    "NV",
    "DD",
    "HS",
    "DJ",
    "AG",
    "IN",
    "HE",
    "TR",
    "AF",
    "CM",
    "TD",
    "NN",
    "SE",
    "GS",
    "SZ",
    "EP",
    "DN",
    "ED",
    "ST",
    "DL",
    "NF",
    "SB",
    "HU",
]


@dataclass(frozen=True)
class CorpusPreset:
    key: str
    label: str
    description: str


@dataclass(frozen=True)
class CorpusRunResult:
    preset_key: str
    records_imported: int
    pages_completed: int
    manifest_ids: list[int]
    recon_modes: list[str]


PUBLIC_MAP_CORPUS_PRESETS = [
    CorpusPreset(
        key="federal_full_by_department",
        label="Federal-wide current — department-sliced (recommended)",
        description=(
            "Current USAJOBS Search iterated across every active department code "
            "in agency_codes. Bypasses the 10,000-result cap that hits a single "
            "no-filter Search by issuing one query per department."
        ),
    ),
    CorpusPreset(
        key="federal_current",
        label="Federal-wide current — single query (capped at 10,000)",
        description=(
            "Current USAJOBS Search with no agency filter. Hits the USAJOBS "
            "10,000-result cap; use 'department-sliced' instead for full coverage."
        ),
    ),
    CorpusPreset(
        key="top_25_current",
        label="Top-25 agency current postings",
        description="Current USAJOBS Search for the top public-map agency codes.",
    ),
    CorpusPreset(
        key="historic_closed_90",
        label="HistoricJoa trailing-90-days closed",
        description="HistoricJoa records whose close date fell in the last 90 days.",
    ),
]


def department_codes_from_db(conn: sqlite3.Connection) -> list[str]:
    """Return every distinct, active department code in ``agency_codes``.

    The result is the slicing key for ``federal_full_by_department``: each
    code becomes one ``Organization=<code>`` Search. Codes with mixed-case or
    blank values are filtered out, and the list is sorted for reproducibility.
    """
    rows = conn.execute(
        "SELECT DISTINCT department_code FROM agency_codes "
        "WHERE active=1 AND department_code IS NOT NULL AND department_code != '' "
        "ORDER BY department_code"
    ).fetchall()
    return [row[0] for row in rows]


def run_public_map_recon(config: Config) -> list[Recommendation]:
    """Run normal recon and update docs/DOWNLOAD_STRATEGY.md."""
    return [recommendation for _, recommendation in run_recon(config, write_doc=True)]


def run_public_map_corpus_preset(
    conn,
    config: Config,
    preset_key: str,
    *,
    current_max_pages: int = 2,
    historic_max_pages: int = 10,
    today: date | None = None,
    run_recon_fn: Callable[[Config], list[Recommendation]] = run_public_map_recon,
) -> CorpusRunResult:
    """Run one D.5.7 corpus-growth preset after recon.

    Page caps are deliberately explicit. The user can raise them from the
    Streamlit page after inspecting recon output and rate-limit comfort.
    """
    recommendations = run_recon_fn(config)
    manifest_ids: list[int] = []
    imported = 0
    pages = 0

    if preset_key == "federal_current":
        result = import_current_search(
            conn,
            config,
            {},
            max_pages=current_max_pages,
        )
        imported += result.records_imported
        pages += result.pages_completed
        _append_manifest(manifest_ids, result)

    elif preset_key == "federal_full_by_department":
        # USAJOBS Search caps any single query at 10,000 results; iterating
        # by department keeps every slice under that ceiling so federal-wide
        # coverage actually completes. Departments with zero open postings
        # cost only one cheap probing request.
        codes = department_codes_from_db(conn)
        for dept_code in codes:
            result = import_current_search(
                conn,
                config,
                {"Organization": dept_code},
                max_pages=current_max_pages,
            )
            imported += result.records_imported
            pages += result.pages_completed
            _append_manifest(manifest_ids, result)

    elif preset_key == "top_25_current":
        for agency_code in TOP_25_AGENCY_CODES:
            result = import_current_search(
                conn,
                config,
                {"Organization": agency_code},
                max_pages=current_max_pages,
            )
            imported += result.records_imported
            pages += result.pages_completed
            _append_manifest(manifest_ids, result)

    elif preset_key == "historic_closed_90":
        params = trailing_90_closed_params(today=today)
        result = import_historic_joa(
            conn,
            config,
            params,
            max_pages=historic_max_pages,
            download_mode="FOCUSED_FULL_DOWNLOAD",
        )
        imported += result.records_imported
        pages += result.pages_completed
        _append_manifest(manifest_ids, result)

    else:
        valid = ", ".join(p.key for p in PUBLIC_MAP_CORPUS_PRESETS)
        raise ValueError(f"Unknown public-map corpus preset {preset_key!r}. Use one of: {valid}.")

    return CorpusRunResult(
        preset_key=preset_key,
        records_imported=imported,
        pages_completed=pages,
        manifest_ids=manifest_ids,
        recon_modes=[rec.mode for rec in recommendations],
    )


def trailing_90_closed_params(*, today: date | None = None) -> Mapping[str, str]:
    resolved_today = today or date.today()
    start = resolved_today - timedelta(days=90)
    return {
        "StartPositionCloseDate": start.isoformat(),
        "EndPositionCloseDate": resolved_today.isoformat(),
    }


def _append_manifest(manifest_ids: list[int], result: ImportResult) -> None:
    if result.manifest_id is not None:
        manifest_ids.append(result.manifest_id)
