"""Orchestrator for the public map's reference-data ingest.

Runs every configured ingest script in order, capturing per-source success or
failure into ``data_source_status`` so the admin dashboard reflects the
outcome regardless of which step failed.

Each step is configured by environment-variable conventions so the script
needs no editing as you add new annual files. Every variable is optional;
unset variables cause that step to be skipped (with a yellow status that
the admin page surfaces as "input not configured").

Environment variables:
    PUBLIC_MAP_STATE_GEOJSON      - path to states GeoJSON
    PUBLIC_MAP_COUNTY_GEOJSON     - path to counties GeoJSON
    PUBLIC_MAP_CBSA_GEOJSON       - path to CBSAs GeoJSON
    PUBLIC_MAP_LOCALITY_DEFS_CSV  - OPM annual definitions CSV
    PUBLIC_MAP_LOCALITY_PAY_CSV   - OPM annual locality % CSV
    PUBLIC_MAP_LOCALITY_YEAR      - integer year for locality polygons (defaults to current)
    PUBLIC_MAP_GS_PAY_CSVS        - colon/semicolon-separated list of GS pay CSV paths
    PUBLIC_MAP_OTHER_PAY_PLANS    - "PLAN=path" pairs separated by ';' (e.g. "FW=fw.csv;ES=es.csv")
    PUBLIC_MAP_BEA_RPP_CSV        - BEA RPP CSV path

Run:
    python scripts/refresh_public_map_data.py
    python scripts/refresh_public_map_data.py --skip locality_polygons
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


@dataclass
class Step:
    key: str
    label: str
    args: list[str]
    enabled: bool = True
    skip_reason: str | None = None


def _split_paths(raw: str | None) -> list[Path]:
    if not raw:
        return []
    parts = raw.replace(";", os.pathsep).split(os.pathsep)
    return [Path(p.strip()) for p in parts if p.strip()]


def _split_plan_pairs(raw: str | None) -> list[tuple[str, Path]]:
    if not raw:
        return []
    pairs: list[tuple[str, Path]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        plan, path = chunk.split("=", 1)
        pairs.append((plan.strip().upper(), Path(path.strip())))
    return pairs


def _python() -> str:
    return sys.executable or "python"


def build_steps() -> list[Step]:
    year = int(
        os.environ.get(
            "PUBLIC_MAP_LOCALITY_YEAR",
            datetime.date.today().year,
        )
    )

    steps: list[Step] = []

    state_geo = os.environ.get("PUBLIC_MAP_STATE_GEOJSON")
    steps.append(
        Step(
            key="ingest_state_polygons",
            label="State polygons",
            args=[_python(), "scripts/ingest_state_polygons.py", "--input", state_geo or ""],
            enabled=bool(state_geo),
            skip_reason="PUBLIC_MAP_STATE_GEOJSON not set" if not state_geo else None,
        )
    )

    county_geo = os.environ.get("PUBLIC_MAP_COUNTY_GEOJSON")
    steps.append(
        Step(
            key="ingest_county_polygons",
            label="County polygons",
            args=[_python(), "scripts/ingest_county_polygons.py", "--input", county_geo or ""],
            enabled=bool(county_geo),
            skip_reason="PUBLIC_MAP_COUNTY_GEOJSON not set" if not county_geo else None,
        )
    )

    cbsa_geo = os.environ.get("PUBLIC_MAP_CBSA_GEOJSON")
    steps.append(
        Step(
            key="ingest_cbsa_polygons",
            label="CBSA polygons",
            args=[_python(), "scripts/ingest_cbsa_polygons.py", "--input", cbsa_geo or ""],
            enabled=bool(cbsa_geo),
            skip_reason="PUBLIC_MAP_CBSA_GEOJSON not set" if not cbsa_geo else None,
        )
    )

    locality_defs = os.environ.get("PUBLIC_MAP_LOCALITY_DEFS_CSV")
    steps.append(
        Step(
            key="ingest_locality_definitions",
            label="OPM locality definitions",
            args=[
                _python(),
                "scripts/ingest_locality_definitions.py",
                "--input",
                locality_defs or "",
            ],
            enabled=bool(locality_defs),
            skip_reason="PUBLIC_MAP_LOCALITY_DEFS_CSV not set" if not locality_defs else None,
        )
    )

    locality_pay = os.environ.get("PUBLIC_MAP_LOCALITY_PAY_CSV")
    steps.append(
        Step(
            key="ingest_locality_pay",
            label="OPM locality percentages",
            args=[
                _python(),
                "scripts/ingest_locality_pay.py",
                "--input",
                locality_pay or "",
            ],
            enabled=bool(locality_pay),
            skip_reason="PUBLIC_MAP_LOCALITY_PAY_CSV not set" if not locality_pay else None,
        )
    )

    steps.append(
        Step(
            key="ingest_locality_polygons",
            label="OPM locality polygons",
            args=[
                _python(),
                "scripts/ingest_locality_polygons.py",
                "--year",
                str(year),
            ],
        )
    )

    for path in _split_paths(os.environ.get("PUBLIC_MAP_GS_PAY_CSVS")):
        steps.append(
            Step(
                key=f"ingest_gs_pay::{path.name}",
                label=f"GS pay table ({path.name})",
                args=[
                    _python(),
                    "scripts/ingest_gs_pay.py",
                    "--input",
                    str(path),
                    "--source-key",
                    f"opm_gs_pay_{path.stem}",
                ],
            )
        )

    for plan, path in _split_plan_pairs(os.environ.get("PUBLIC_MAP_OTHER_PAY_PLANS")):
        steps.append(
            Step(
                key=f"ingest_other_pay_plans::{plan}",
                label=f"{plan} pay tables",
                args=[
                    _python(),
                    "scripts/ingest_other_pay_plans.py",
                    "--plan",
                    plan,
                    "--input",
                    str(path),
                ],
            )
        )

    bea_rpp = os.environ.get("PUBLIC_MAP_BEA_RPP_CSV")
    steps.append(
        Step(
            key="ingest_bea_rpp",
            label="BEA Regional Price Parities",
            args=[_python(), "scripts/ingest_bea_rpp.py", "--input", bea_rpp or ""],
            enabled=bool(bea_rpp),
            skip_reason="PUBLIC_MAP_BEA_RPP_CSV not set" if not bea_rpp else None,
        )
    )

    return steps


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Step key (or substring) to skip. Repeatable.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List configured steps and their enabled state, then exit.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        default=True,
        help="Default true: keep running remaining steps after one fails.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    steps = build_steps()

    if args.list:
        for step in steps:
            status = "ENABLED" if step.enabled else f"SKIP ({step.skip_reason})"
            print(f"{step.key:<48} {status}")
        return 0

    skip_patterns = [s.lower() for s in args.skip]
    failures: list[str] = []
    for step in steps:
        if any(pat in step.key.lower() for pat in skip_patterns):
            print(f"-> [{step.key}] skipped via --skip")
            continue
        if not step.enabled:
            print(f"-> [{step.key}] skipped: {step.skip_reason}")
            continue
        print(f"-> [{step.key}] {step.label}")
        result = subprocess.run(step.args, cwd=REPO)
        if result.returncode != 0:
            failures.append(step.key)
            print(f"   FAILED (exit {result.returncode})")
            if not args.continue_on_error:
                break
    if failures:
        print(f"\n{len(failures)} step(s) failed: {', '.join(failures)}")
        return 1
    print("\nAll configured ingests succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
