"""Ingest BEA Regional Price Parities into ``cost_of_living_index``.

BEA publishes RPPs at state and metro (CBSA) level. Download the dataset
from <https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area>
and pass the resulting CSV via ``--input``.

Expected CSV columns (header required, case-insensitive):
    year, geo_type, geo_code, rpp_overall
Optional columns: rpp_goods, rpp_services, rpp_rents.

``geo_type`` is ``state`` (2-letter postal) or ``cbsa`` (5-digit CBSA code).
``rpp_overall`` is the overall RPP value where 100 = national average.

Run:
    python scripts/ingest_bea_rpp.py --input data/external/bea_rpp_2024.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import utc_now  # noqa: E402
from src.ingest_common import emit_summary, resolve_or_download, run_ingest  # noqa: E402

SOURCE_KEY = "bea_rpp"
DISPLAY_NAME = "BEA Regional Price Parities"
CATEGORY = "col"
SEED_CSV = REPO / "data" / "external" / "bea_rpp" / "2023.csv"

REQUIRED_COLUMNS = {"year", "geo_type", "geo_code", "rpp_overall"}
VALID_GEO_TYPES = {"state", "cbsa"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional CSV. When omitted, falls back to the checked-in seed at "
            f"{SEED_CSV.relative_to(REPO).as_posix()} per ADR-0027."
        ),
    )
    parser.add_argument("--source", default="bea:rpp")
    return parser.parse_args()


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def import_rpp_from_csv(
    conn: sqlite3.Connection,
    *,
    input_path: Path,
    source: str,
) -> int:
    now = utc_now()
    written = 0
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        normalized_fields = {
            (name or "").strip().lower(): name
            for name in (reader.fieldnames or [])
        }
        missing = REQUIRED_COLUMNS - set(normalized_fields)
        if missing:
            raise ValueError(
                f"CSV missing required columns: {sorted(missing)}; got {reader.fieldnames!r}"
            )
        for row in reader:
            year_raw = row.get(normalized_fields["year"], "").strip()
            geo_type = row.get(normalized_fields["geo_type"], "").strip().lower()
            geo_code = row.get(normalized_fields["geo_code"], "").strip()
            rpp_overall = _to_float(row.get(normalized_fields["rpp_overall"], ""))
            if not year_raw or geo_type not in VALID_GEO_TYPES or not geo_code or rpp_overall is None:
                continue
            try:
                year = int(year_raw)
            except ValueError:
                continue
            geo_code_norm = geo_code.upper() if geo_type == "state" else geo_code.zfill(5)[:5]
            rpp_goods = _to_float(row.get(normalized_fields.get("rpp_goods", ""), ""))
            rpp_services = _to_float(row.get(normalized_fields.get("rpp_services", ""), ""))
            rpp_rents = _to_float(row.get(normalized_fields.get("rpp_rents", ""), ""))
            conn.execute(
                """
                INSERT INTO cost_of_living_index (
                    year, geo_type, geo_code, rpp_overall, rpp_goods,
                    rpp_services, rpp_rents, source, imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(year, geo_type, geo_code, source) DO UPDATE SET
                    rpp_overall=excluded.rpp_overall,
                    rpp_goods=excluded.rpp_goods,
                    rpp_services=excluded.rpp_services,
                    rpp_rents=excluded.rpp_rents,
                    imported_at=excluded.imported_at
                """,
                (year, geo_type, geo_code_norm, rpp_overall, rpp_goods,
                 rpp_services, rpp_rents, source, now),
            )
            written += 1
    conn.commit()
    return written


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    resolved = resolve_or_download(
        source_key=SOURCE_KEY,
        default_url=None,
        cache_dir=SEED_CSV.parent,
        filename=SEED_CSV.name,
        user_input=args.input,
        seed_path=SEED_CSV,
    )
    row_count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        database_path=cfg.database_path,
        notes=f"input={resolved.name}",
        work=lambda conn: import_rpp_from_csv(
            conn,
            input_path=resolved,
            source=args.source,
        ),
    )
    emit_summary(SOURCE_KEY, row_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
