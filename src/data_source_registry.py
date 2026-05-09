"""Status tracking for the public map's external data sources.

Per ADR-0018, every external dataset used by the public map writes a row to
``data_source_status`` so the local admin dashboard can show freshness, row
counts, last error, and manual-override flags.

Ingest scripts wrap their work like::

    from src.data_source_registry import begin_run, complete_run, fail_run

    begin_run(conn, "census_states", "Census state polygons", "geometry")
    try:
        rows = ...
        complete_run(conn, "census_states", row_count=len(rows))
    except Exception as exc:
        fail_run(conn, "census_states", str(exc))
        raise

The registry never modifies the underlying dataset tables — it only tracks
status. That keeps "did the ingest run?" separate from "did the data land?".
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from src.database import utc_now

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {
    "job_postings",
    "pay",
    "locality",
    "geometry",
    "col",
    "geocoding",
    "code_list",
}


def begin_run(
    conn: sqlite3.Connection,
    source_key: str,
    display_name: str,
    category: str,
) -> None:
    """Mark an ingest run as started. Upserts the registry row if missing."""
    if not source_key:
        raise ValueError("source_key is required")
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Unsupported category {category!r}; expected one of {sorted(VALID_CATEGORIES)}"
        )
    now = utc_now()
    conn.execute(
        """
        INSERT INTO data_source_status (
            source_key, display_name, category, last_run_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
            display_name=excluded.display_name,
            category=excluded.category,
            last_run_at=excluded.last_run_at,
            updated_at=excluded.updated_at
        """,
        (source_key, display_name, category, now, now),
    )
    conn.commit()


def complete_run(
    conn: sqlite3.Connection,
    source_key: str,
    *,
    row_count: int | None = None,
    notes: str | None = None,
) -> None:
    """Mark the most recent run as successful and store the row count."""
    now = utc_now()
    conn.execute(
        """
        UPDATE data_source_status
        SET last_success_at = ?,
            row_count = ?,
            last_error = NULL,
            notes = COALESCE(?, notes),
            updated_at = ?
        WHERE source_key = ?
        """,
        (now, row_count, notes, now, source_key),
    )
    conn.commit()


def fail_run(
    conn: sqlite3.Connection,
    source_key: str,
    error_message: str,
) -> None:
    """Mark the most recent run as failed with an error message."""
    now = utc_now()
    conn.execute(
        """
        UPDATE data_source_status
        SET last_error = ?,
            updated_at = ?
        WHERE source_key = ?
        """,
        (error_message[:2000] if error_message else None, now, source_key),
    )
    conn.commit()


def set_manual_override(
    conn: sqlite3.Connection,
    source_key: str,
    enabled: bool,
    notes: str | None = None,
) -> None:
    """Toggle the manual_override flag and add an optional note."""
    now = utc_now()
    conn.execute(
        """
        UPDATE data_source_status
        SET manual_override = ?,
            notes = COALESCE(?, notes),
            updated_at = ?
        WHERE source_key = ?
        """,
        (1 if enabled else 0, notes, now, source_key),
    )
    conn.commit()


def get_status(
    conn: sqlite3.Connection,
    source_key: str,
) -> dict[str, Any] | None:
    """Return one source's status, or None if not yet tracked."""
    row = conn.execute(
        "SELECT * FROM data_source_status WHERE source_key=?",
        (source_key,),
    ).fetchone()
    return dict(row) if row else None


def list_status(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Return every tracked source, optionally filtered by category."""
    if category is not None:
        rows = conn.execute(
            "SELECT * FROM data_source_status WHERE category=? ORDER BY display_name",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM data_source_status ORDER BY category, display_name"
        ).fetchall()
    return [dict(row) for row in rows]


def freshness_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aggregate counts for the admin dashboard's top-line metrics."""
    rows = list_status(conn)
    summary = {
        "total": len(rows),
        "succeeded": sum(1 for r in rows if r.get("last_success_at")),
        "errored": sum(1 for r in rows if r.get("last_error")),
        "manual_override": sum(1 for r in rows if r.get("manual_override")),
        "missing": sum(1 for r in rows if not r.get("last_success_at") and not r.get("last_error")),
    }
    return summary
