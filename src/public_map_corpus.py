"""Corpus-growth presets for the public map.

D.5.7 needs larger, reproducible import scopes before the public map can be
evaluated honestly. These helpers keep the Streamlit page thin while preserving
the repo rule that large imports pass through reconnaissance first.
"""
from __future__ import annotations

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
        key="federal_current",
        label="Federal-wide current postings",
        description="Current USAJOBS Search with no agency filter.",
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
