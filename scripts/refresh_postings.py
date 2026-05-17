"""Pull current federal-wide USAJOBS postings and write the public-map bundle.

Designed to run unattended in CI (GitHub Actions) and from the operator's
laptop. The flow:

1. Initialize the SQLite schema (no-op if it already exists).
2. Run reference-data ingests (states, counties, locality pay, BEA RPP, …).
3. Refresh the agency code list (so new sub-elements show up in the typeahead).
4. Run a federal-wide USAJOBS Search import, sliced per department so the
   USAJOBS 10,000-result-per-query cap does not truncate the corpus.
5. Backfill agency_code on any rows that came in without one.
6. Re-export the public-map static bundle.

Each step is idempotent. The bundle is committed by the surrounding workflow
(``.github/workflows/refresh-public-map.yml``) only when the contents change.

Run:
    python scripts/refresh_postings.py --max-pages 50
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import connect, init_schema  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help=(
            "USAJOBS Search page cap (each page = 500 records). The importer "
            "auto-stops when pagination runs out, so this is a safety ceiling, "
            "not a target. Default 100 = up to 50,000 postings (federal-wide "
            "ceiling is well below that today, but the cap leaves headroom)."
        ),
    )
    parser.add_argument(
        "--skip-reference-data",
        action="store_true",
        help="Skip the reference-data refresh (use when polygons/COL/pay are already fresh).",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip the USAJOBS Search import (re-export only).",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip the bundle export (import only).",
    )
    return parser.parse_args()


def _run_script(script: str, *args: str) -> None:
    """Invoke another scripts/* module as a subprocess so it sees clean argv."""
    cmd = [sys.executable, str(REPO / "scripts" / script), *args]
    logger.info(">> %s", " ".join(cmd[1:]))
    completed = subprocess.run(cmd, cwd=REPO, check=False)
    if completed.returncode != 0:
        raise SystemExit(
            f"{script} failed with exit code {completed.returncode}"
        )


def _run_federal_current(max_pages: int) -> None:
    """Federal-wide current Search import, department-sliced.

    USAJOBS Search caps any single query at 10,000 results, so a no-filter
    federal-wide query silently truncates the corpus and undercounts every
    agency whose postings sort past the cap. The ``federal_full_by_department``
    preset issues one ``Organization=<department>`` query per department, so
    each slice stays under the ceiling and the full corpus comes through.
    """
    from src.public_map_corpus import run_public_map_corpus_preset

    logger.info(
        "--- federal-wide current Search import, department-sliced (max_pages=%d per slice) ---",
        max_pages,
    )
    config = load_config()
    conn = connect(config.database_path)
    init_schema(conn)
    try:
        result = run_public_map_corpus_preset(
            conn,
            config,
            "federal_full_by_department",
            current_max_pages=max_pages,
        )
        logger.info(
            "Imported %d records over %d pages (manifests=%s, recon_modes=%s).",
            result.records_imported,
            result.pages_completed,
            result.manifest_ids,
            result.recon_modes,
        )
    finally:
        conn.close()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = load_config()
    conn = connect(config.database_path)
    init_schema(conn)
    conn.close()

    if not args.skip_reference_data:
        logger.info("=== STEP: reference data refresh ===")
        _run_script("refresh_public_map_data.py")
        logger.info("=== STEP: agency code list refresh ===")
        _run_script("ingest_agency_codes.py")

    if not args.skip_import:
        _run_federal_current(args.max_pages)
        logger.info("=== STEP: backfill agency codes on imported jobs ===")
        _run_script("backfill_agency_codes.py")

    if not args.skip_export:
        logger.info("=== STEP: public-map bundle export ===")
        _run_script("export_public_map.py")

    logger.info("refresh_postings: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
