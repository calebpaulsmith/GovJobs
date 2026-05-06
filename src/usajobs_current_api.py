"""Importer entry points for current open USAJOBS Search results."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from config import Config
from src.data_import import ImportResult, import_current_search


def import_search(
    conn,
    config: Config,
    query_params: Mapping[str, Any] | None = None,
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> ImportResult:
    return import_current_search(
        conn,
        config,
        query_params,
        max_pages=max_pages,
        dry_run=dry_run,
    )
