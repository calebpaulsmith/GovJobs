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

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
    load_dotenv = None  # type: ignore[assignment]

if load_dotenv:
    load_dotenv(REPO / ".env")


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

    # Per ADR-0027, polygon ingests are self-bootstrapping. Env vars become
    # overrides — no env var means "use the default Census TIGER URL," not
    # "skip this step."
    state_geo = os.environ.get("PUBLIC_MAP_STATE_GEOJSON")
    state_args = [_python(), "scripts/ingest_state_polygons.py"]
    if state_geo:
        state_args.extend(["--input", state_geo])
    steps.append(
        Step(
            key="ingest_state_polygons",
            label="State polygons",
            args=state_args,
        )
    )

    county_geo = os.environ.get("PUBLIC_MAP_COUNTY_GEOJSON")
    county_args = [_python(), "scripts/ingest_county_polygons.py"]
    if county_geo:
        county_args.extend(["--input", county_geo])
    steps.append(
        Step(
            key="ingest_county_polygons",
            label="County polygons",
            args=county_args,
        )
    )

    cbsa_geo = os.environ.get("PUBLIC_MAP_CBSA_GEOJSON")
    cbsa_args = [_python(), "scripts/ingest_cbsa_polygons.py"]
    if cbsa_geo:
        cbsa_args.extend(["--input", cbsa_geo])
    steps.append(
        Step(
            key="ingest_cbsa_polygons",
            label="CBSA polygons",
            args=cbsa_args,
        )
    )

    # Per ADR-0027 these ingests fall back to a checked-in seed CSV when no
    # env var or --input is provided.
    locality_defs = os.environ.get("PUBLIC_MAP_LOCALITY_DEFS_CSV")
    locality_defs_args = [_python(), "scripts/ingest_locality_definitions.py"]
    if locality_defs:
        locality_defs_args.extend(["--input", locality_defs])
    steps.append(
        Step(
            key="ingest_locality_definitions",
            label="OPM locality definitions",
            args=locality_defs_args,
        )
    )

    locality_pay = os.environ.get("PUBLIC_MAP_LOCALITY_PAY_CSV")
    locality_pay_args = [_python(), "scripts/ingest_locality_pay.py"]
    if locality_pay:
        locality_pay_args.extend(["--input", locality_pay])
    steps.append(
        Step(
            key="ingest_locality_pay",
            label="OPM locality percentages",
            args=locality_pay_args,
        )
    )

    locality_poly_args = [_python(), "scripts/ingest_locality_polygons.py"]
    if os.environ.get("PUBLIC_MAP_LOCALITY_YEAR"):
        locality_poly_args.extend(["--year", str(year)])
    steps.append(
        Step(
            key="ingest_locality_polygons",
            label="OPM locality polygons",
            args=locality_poly_args,
        )
    )

    gs_pay_paths = _split_paths(os.environ.get("PUBLIC_MAP_GS_PAY_CSVS"))
    if gs_pay_paths:
        for path in gs_pay_paths:
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
    else:
        # Per ADR-0027, default to the checked-in 2025 GS base table seed.
        steps.append(
            Step(
                key="ingest_gs_pay::seed",
                label="GS pay table (2025 seed)",
                args=[_python(), "scripts/ingest_gs_pay.py"],
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
    bea_args = [_python(), "scripts/ingest_bea_rpp.py"]
    if bea_rpp:
        bea_args.extend(["--input", bea_rpp])
    steps.append(
        Step(
            key="ingest_bea_rpp",
            label="BEA Regional Price Parities",
            args=bea_args,
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
