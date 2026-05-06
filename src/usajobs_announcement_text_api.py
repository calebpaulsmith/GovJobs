"""Importer entry points for selected HistoricJoa AnnouncementText records."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from config import Config
from src.data_import import (
    ImportResult,
    import_announcement_text_by_filters,
    import_announcement_text_for_jobs,
)


def import_announcement_text(
    conn,
    config: Config,
    jobs: Iterable[Mapping[str, Any]],
    *,
    batch_size: int = 1,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> ImportResult:
    return import_announcement_text_for_jobs(
        conn,
        config,
        jobs,
        batch_size=batch_size,
        max_pages=max_pages,
        dry_run=dry_run,
    )


def import_announcement_text_filters(
    conn,
    config: Config,
    query_params: Mapping[str, Any],
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
    download_mode: str = "FOCUSED_FULL_DOWNLOAD",
) -> ImportResult:
    return import_announcement_text_by_filters(
        conn,
        config,
        query_params,
        max_pages=max_pages,
        dry_run=dry_run,
        download_mode=download_mode,
    )
