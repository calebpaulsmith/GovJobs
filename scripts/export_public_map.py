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
    closed_jobs_geojson,
    cost_of_living,
    counties_geojson,
    current_reference_year,
    job_details,
    jobs_geojson,
    localities_geojson,
    manifest,
    metros_geojson,
    opm_state_aggregates,
    pay_tables,
    series_options,
    states_geojson,
    zip_centroids_payload,
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
        year = current_reference_year(conn)
        geojson = jobs_geojson(conn, year=year, repo_root=REPO)
        closed_geojson = closed_jobs_geojson(conn, year=year)
        details = job_details(conn, year=year)
        opm = opm_state_aggregates(conn)
        agencies = agency_options(conn)
        series = series_options(conn)
        states = states_geojson(conn, repo_root=REPO, year=year)
        localities = localities_geojson(conn, repo_root=REPO, year=year)
        counties = counties_geojson(conn, repo_root=REPO, year=year)
        metros = metros_geojson(conn, repo_root=REPO, year=year)
        pay_tables_payload = pay_tables(conn)
        col_payload = cost_of_living(conn)
        zip_centroids = zip_centroids_payload(conn)
        layer_counts = {
            "states.geojson": len(states["features"]),
            "localities.geojson": len(localities["features"]),
            "counties.geojson": len(counties["features"]),
            "metros.geojson": len(metros["features"]),
            "jobs.geojson": len(geojson["features"]),
            "closed_jobs.geojson": len(closed_geojson["features"]),
            "zip_centroids.json": len(zip_centroids),
        }
        man = manifest(
            conn,
            feature_count=len(geojson["features"]),
            job_count=len(details),
            opm_state_count=len(opm),
            reference_year=year,
            layer_counts=layer_counts,
        )
    finally:
        conn.close()

    print(f"Reference year:   {man['reference_year']}")
    print(f"Open postings:    {man['job_count']:,}")
    print(f"Closed markers:   {layer_counts['closed_jobs.geojson']:,} trailing-90-day locations")
    print(f"Map features:     {man['feature_count']:,} (one per job-location)")
    print(f"OPM states:       {man['opm_state_count']:,}")
    print(f"Agencies:         {len(agencies):,}")
    print(f"Series:           {len(series):,}")
    print(f"ZIP centroids:    {len(zip_centroids):,}")
    print(
        "Polygons:         "
        f"{layer_counts['states.geojson']:,} states / "
        f"{layer_counts['localities.geojson']:,} localities / "
        f"{layer_counts['counties.geojson']:,} counties / "
        f"{layer_counts['metros.geojson']:,} metros"
    )
    print(
        "Geocoding:        "
        f"{man['geocoding']['city_matches']:,} city / "
        f"{man['geocoding']['state_matches']:,} state-centroid / "
        f"{man['geocoding']['unmatched']:,} unmatched"
    )
    print(f"Data sources:     {len(man['data_sources']):,} tracked")

    if args.dry_run:
        print("Dry run — no files written.")
        return 0

    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    sizes = {
        "jobs.geojson": _write_json(output / "jobs.geojson", geojson),
        "closed_jobs.geojson": _write_json(output / "closed_jobs.geojson", closed_geojson),
        "jobs_detail.json": _write_json(output / "jobs_detail.json", details),
        "opm_states.json": _write_json(output / "opm_states.json", opm),
        "agencies.json": _write_json(output / "agencies.json", agencies),
        "series.json": _write_json(output / "series.json", series),
        "states.geojson": _write_json(output / "states.geojson", states),
        "localities.geojson": _write_json(output / "localities.geojson", localities),
        "counties.geojson": _write_json(output / "counties.geojson", counties),
        "metros.geojson": _write_json(output / "metros.geojson", metros),
        "pay_tables.json": _write_json(output / "pay_tables.json", pay_tables_payload),
        "cost_of_living.json": _write_json(output / "cost_of_living.json", col_payload),
        "zip_centroids.json": _write_json(output / "zip_centroids.json", zip_centroids),
        "manifest.json": _write_json(output / "manifest.json", man),
    }
    print()
    print(f"Wrote bundle to {output}")
    for name, size in sizes.items():
        print(f"  {name:<22} {size:>10,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
