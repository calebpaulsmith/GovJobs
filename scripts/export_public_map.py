"""CLI entry that builds the public map's static data bundle.

Reads the local SQLite database and writes JSON / GeoJSON files into
`public_map/static/data/`. Cloudflare Pages picks them up on the next push.

Run:
    python scripts/export_public_map.py
    python scripts/export_public_map.py --dry-run
    python scripts/export_public_map.py --output some/other/dir
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import connect, init_schema  # noqa: E402
from src.public_map_export import (  # noqa: E402
    agency_options,
    job_details,
    jobs_geojson,
    manifest,
    opm_state_aggregates,
    series_options,
)


DEFAULT_OUTPUT = REPO / "public_map" / "static" / "data"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Directory to write the data bundle into "
            f"(default: {DEFAULT_OUTPUT.relative_to(REPO)})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all queries and print counts; do not write any files.",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: object) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return path.stat().st_size


def main() -> int:
    args = _parse_args()
    cfg = load_config()
    conn = connect(cfg.database_path)
    init_schema(conn)
    try:
        geojson = jobs_geojson(conn)
        details = job_details(conn)
        opm = opm_state_aggregates(conn)
        agencies = agency_options(conn)
        series = series_options(conn)
        man = manifest(
            conn,
            feature_count=len(geojson["features"]),
            job_count=len(details),
            opm_state_count=len(opm),
        )
    finally:
        conn.close()

    print(f"Open postings:    {man['job_count']:,}")
    print(f"Map features:     {man['feature_count']:,} (one per job-location)")
    print(f"OPM states:       {man['opm_state_count']:,}")
    print(f"Agencies:         {len(agencies):,}")
    print(f"Series:           {len(series):,}")
    print(
        "Geocoding:        "
        f"{man['geocoding']['city_matches']:,} city / "
        f"{man['geocoding']['state_matches']:,} state-centroid / "
        f"{man['geocoding']['unmatched']:,} unmatched"
    )

    if args.dry_run:
        print("Dry run — no files written.")
        return 0

    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    sizes = {
        "jobs.geojson": _write_json(output / "jobs.geojson", geojson),
        "jobs_detail.json": _write_json(output / "jobs_detail.json", details),
        "opm_states.json": _write_json(output / "opm_states.json", opm),
        "agencies.json": _write_json(output / "agencies.json", agencies),
        "series.json": _write_json(output / "series.json", series),
        "manifest.json": _write_json(output / "manifest.json", man),
    }
    print()
    print(f"Wrote bundle to {output}")
    for name, size in sizes.items():
        print(f"  {name:<20} {size:>10,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
