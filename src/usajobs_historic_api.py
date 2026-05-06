"""Importer entry points for USAJOBS HistoricJoa structured records."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from config import Config
from src.data_import import ImportResult, import_historic_joa


def import_historic(
    conn,
    config: Config,
    query_params: Mapping[str, Any] | None = None,
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
    download_mode: str = "SAMPLE_ONLY",
) -> ImportResult:
    return import_historic_joa(
        conn,
        config,
        query_params,
        max_pages=max_pages,
        dry_run=dry_run,
        download_mode=download_mode,
    )
