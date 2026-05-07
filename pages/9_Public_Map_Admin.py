"""Local-only admin dashboard for the public map's reference data.

Per ADR-0018 the operator self-verifies every external dataset here before
trusting it for the nightly export. This page is part of the dashboard's
``pages/`` tree and is **never** deployed.

Capabilities:
- Per-source status table (last run, last success, row count, error, override)
- Refresh button that runs the matching ingest script
- CSV upload override (toggles ``manual_override`` and stores notes)
- Year-over-year diff for pay scales — surfaces unexpected changes
- "Run nightly export now" button
"""
from __future__ import annotations

import datetime
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_source_registry import (
    freshness_summary,
    list_status,
    set_manual_override,
)
from src.ui_data import app_connection


REPO = Path(__file__).resolve().parents[1]


SCRIPT_FOR_KEY: dict[str, list[str]] = {
    "census_states": ["scripts/ingest_state_polygons.py"],
    "census_counties": ["scripts/ingest_county_polygons.py"],
    "census_cbsa": ["scripts/ingest_cbsa_polygons.py"],
    "opm_locality_definitions": ["scripts/ingest_locality_definitions.py"],
    "opm_locality_pay": ["scripts/ingest_locality_pay.py"],
    "opm_locality_polygons": ["scripts/ingest_locality_polygons.py"],
    "opm_gs_pay": ["scripts/ingest_gs_pay.py"],
    "bea_rpp": ["scripts/ingest_bea_rpp.py"],
}

CATEGORY_LABELS = {
    "geometry": "Geometry",
    "pay": "Pay tables",
    "locality": "Locality definitions",
    "col": "Cost of living",
    "job_postings": "Job postings",
}


def _age_label(timestamp: str | None) -> str:
    if not timestamp:
        return "never"
    try:
        when = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - when
    if delta.days >= 365:
        return f"{delta.days // 365}y ago"
    if delta.days >= 30:
        return f"{delta.days // 30}mo ago"
    if delta.days >= 1:
        return f"{delta.days}d ago"
    if delta.seconds >= 3600:
        return f"{delta.seconds // 3600}h ago"
    return f"{max(delta.seconds // 60, 1)}m ago"


def _status_indicator(row: dict) -> str:
    if row.get("last_error"):
        return "RED"
    if not row.get("last_success_at"):
        return "GRAY"
    try:
        when = datetime.datetime.fromisoformat(
            row["last_success_at"].replace("Z", "+00:00")
        )
    except ValueError:
        return "GRAY"
    age_days = (datetime.datetime.now(datetime.timezone.utc) - when).days
    if age_days > 400:
        return "YELLOW"
    return "GREEN"


def _render_status_table(rows: list[dict]) -> None:
    if not rows:
        st.info(
            "No data sources tracked yet. Run "
            "`python scripts/refresh_public_map_data.py` to register them."
        )
        return
    df = pd.DataFrame(
        [
            {
                "Status": _status_indicator(row),
                "Source": row.get("display_name") or row.get("source_key"),
                "Category": CATEGORY_LABELS.get(row.get("category", ""), row.get("category")),
                "Last success": _age_label(row.get("last_success_at")),
                "Rows": row.get("row_count") or 0,
                "Override": "yes" if row.get("manual_override") else "",
                "Last error": (row.get("last_error") or "")[:120],
                "Key": row.get("source_key"),
            }
            for row in rows
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def _run_subprocess(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable] + args,
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def _render_refresh_controls(rows: list[dict]) -> None:
    st.subheader("Refresh a single source")
    keys = sorted({row["source_key"] for row in rows} | set(SCRIPT_FOR_KEY))
    if not keys:
        return
    selected = st.selectbox("Source key", keys)
    matched_script = next(
        (cmd for prefix, cmd in SCRIPT_FOR_KEY.items() if selected.startswith(prefix)),
        None,
    )
    extra_args = st.text_input(
        "Extra arguments",
        placeholder="--input data/external/foo.csv",
        help="Appended to the ingest script invocation.",
    )
    if matched_script is None:
        st.warning(
            "No registered ingest script for this key — refresh from the CLI instead."
        )
        return
    if st.button(f"Run {' '.join(matched_script)}", type="primary"):
        cmd = list(matched_script)
        if extra_args.strip():
            cmd.extend(extra_args.strip().split())
        with st.spinner(f"Running `{' '.join(cmd)}`"):
            result = _run_subprocess(cmd)
        if result.returncode == 0:
            st.success("Ingest succeeded.")
        else:
            st.error(f"Ingest failed (exit {result.returncode}).")
        if result.stdout:
            st.code(result.stdout, language="text")
        if result.stderr:
            st.code(result.stderr, language="text")


def _render_override_controls(rows: list[dict]) -> None:
    st.subheader("Manual override")
    if not rows:
        return
    options = {f"{row['display_name']} ({row['source_key']})": row for row in rows}
    label = st.selectbox("Source", list(options.keys()), key="override_source")
    target = options[label]
    enabled = st.toggle(
        "Manual override active",
        value=bool(target.get("manual_override")),
        help=(
            "When enabled, the orchestrator will not overwrite this source. "
            "Use after a manual CSV upload."
        ),
    )
    note = st.text_input(
        "Note",
        value=(target.get("notes") or "")[:200],
        max_chars=200,
    )
    upload = st.file_uploader(
        "Upload CSV override",
        type=["csv"],
        help=(
            "Saves the file under data/external/manual/<source_key>/<filename>. "
            "You still need to run the matching ingest script with --input pointing here."
        ),
    )
    if st.button("Apply override"):
        conn = app_connection()
        set_manual_override(
            conn,
            target["source_key"],
            enabled=enabled,
            notes=note or None,
        )
        if upload is not None:
            target_dir = REPO / "data" / "external" / "manual" / target["source_key"]
            target_dir.mkdir(parents=True, exist_ok=True)
            saved = target_dir / upload.name
            with saved.open("wb") as handle:
                handle.write(upload.getvalue())
            st.success(f"Saved override file to {saved.relative_to(REPO)}.")
        else:
            st.success("Override flag updated.")


def _pay_scale_diff(conn) -> pd.DataFrame:
    """Year-over-year change per (pay_plan, grade, step, locality_code).

    Each row shows the latest two years' annual_rate plus the % change.
    Used to spot bad imports — large unexplained jumps fire here.
    """
    return pd.read_sql_query(
        """
        WITH latest AS (
            SELECT pay_plan, grade, step, locality_code,
                   MAX(year) AS y_latest
            FROM pay_scales
            GROUP BY pay_plan, grade, step, locality_code
        ),
        prev AS (
            SELECT ps.pay_plan, ps.grade, ps.step, ps.locality_code,
                   MAX(ps.year) AS y_prev
            FROM pay_scales ps
            JOIN latest l
              ON l.pay_plan=ps.pay_plan AND l.grade=ps.grade
             AND l.step=ps.step AND l.locality_code=ps.locality_code
             AND ps.year < l.y_latest
            GROUP BY ps.pay_plan, ps.grade, ps.step, ps.locality_code
        )
        SELECT l.pay_plan, l.grade, l.step, l.locality_code,
               l.y_latest, ps_l.annual_rate AS rate_latest,
               p.y_prev, ps_p.annual_rate AS rate_prev,
               ROUND((ps_l.annual_rate - ps_p.annual_rate) * 100.0 / ps_p.annual_rate, 2) AS pct_change
        FROM latest l
        JOIN pay_scales ps_l
          ON ps_l.pay_plan=l.pay_plan AND ps_l.grade=l.grade
         AND ps_l.step=l.step AND ps_l.locality_code=l.locality_code
         AND ps_l.year=l.y_latest
        JOIN prev p
          ON p.pay_plan=l.pay_plan AND p.grade=l.grade
         AND p.step=l.step AND p.locality_code=l.locality_code
        JOIN pay_scales ps_p
          ON ps_p.pay_plan=p.pay_plan AND ps_p.grade=p.grade
         AND ps_p.step=p.step AND ps_p.locality_code=p.locality_code
         AND ps_p.year=p.y_prev
        ORDER BY ABS(pct_change) DESC, l.pay_plan, l.grade, l.step
        """,
        conn,
    )


def _export_now() -> None:
    if st.button("Export public map bundle now"):
        with st.spinner("Running scripts/export_public_map.py"):
            result = _run_subprocess(["scripts/export_public_map.py"])
        if result.returncode == 0:
            st.success("Export succeeded.")
        else:
            st.error(f"Export failed (exit {result.returncode}).")
        if result.stdout:
            st.code(result.stdout, language="text")
        if result.stderr:
            st.code(result.stderr, language="text")


def main() -> None:
    st.set_page_config(page_title="Public Map Admin", layout="wide")
    st.title("Public Map Admin")
    st.caption(
        "Local-only operator console for the data sources behind "
        "thegrandpipeline.com/map. This page is never deployed."
    )

    conn = app_connection()
    summary = freshness_summary(conn)
    cols = st.columns(5)
    cols[0].metric("Tracked", summary["total"])
    cols[1].metric("Succeeded", summary["succeeded"])
    cols[2].metric("Errored", summary["errored"])
    cols[3].metric("Manual override", summary["manual_override"])
    cols[4].metric("Missing", summary["missing"])

    rows = list_status(conn)
    st.subheader("Data sources")
    _render_status_table(rows)

    left, right = st.columns(2)
    with left:
        _render_refresh_controls(rows)
    with right:
        _render_override_controls(rows)

    st.subheader("Pay-scale year-over-year diff")
    diff = _pay_scale_diff(conn)
    if diff.empty:
        st.info("No pay scales loaded yet.")
    else:
        st.caption(
            "Sorted by absolute % change. Investigate any row with |pct_change| > 8% — "
            "that is far above typical annual locality movement."
        )
        st.dataframe(diff, use_container_width=True, hide_index=True)

    st.subheader("Export")
    _export_now()


main()
