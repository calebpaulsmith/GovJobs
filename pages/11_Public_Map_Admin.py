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
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from config import load_config
from src.data_source_registry import (
    freshness_summary,
    list_status,
    set_manual_override,
)
from src.data_import import import_current_search
from src.public_map_corpus import run_public_map_recon
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

REFRESH_ALL_STEPS: list[tuple[str, str, list[str]]] = [
    ("census_states", "State polygons", ["scripts/ingest_state_polygons.py"]),
    ("census_counties", "County polygons", ["scripts/ingest_county_polygons.py"]),
    ("census_cbsa", "CBSA polygons", ["scripts/ingest_cbsa_polygons.py"]),
    ("opm_locality_definitions", "OPM locality definitions", ["scripts/ingest_locality_definitions.py"]),
    ("opm_locality_pay", "OPM locality percentages", ["scripts/ingest_locality_pay.py"]),
    ("opm_locality_polygons", "OPM locality polygons", ["scripts/ingest_locality_polygons.py"]),
    ("opm_gs_pay", "GS pay tables", ["scripts/ingest_gs_pay.py"]),
    ("bea_rpp", "BEA Regional Price Parities", ["scripts/ingest_bea_rpp.py"]),
]

CATEGORY_LABELS = {
    "geometry": "Geometry",
    "pay": "Pay tables",
    "locality": "Locality definitions",
    "col": "Cost of living",
    "job_postings": "Job postings",
}

PUBLIC_MAP_DATA = REPO / "public_map" / "static" / "data"


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


def _format_delta(previous: int | None, current: int | None) -> str:
    if previous is None or current is None:
        return ""
    delta = int(current) - int(previous)
    if delta > 0:
        return f"+{delta:,}"
    return f"{delta:,}"


def _status_by_key(conn) -> dict[str, dict]:
    return {row["source_key"]: row for row in list_status(conn)}


def _manifest_layers() -> dict[str, int]:
    path = PUBLIC_MAP_DATA / "manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    layers = payload.get("layers") or {}
    return {str(key): int(value or 0) for key, value in layers.items()}


def _job_totals(conn) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_usajobs,
            SUM(CASE WHEN source='usajobs_search' THEN 1 ELSE 0 END) AS current_search,
            SUM(CASE WHEN source='usajobs_historic' THEN 1 ELSE 0 END) AS historic,
            SUM(
                CASE
                    WHEN source LIKE 'usajobs%'
                     AND (close_date IS NULL OR close_date >= date('now'))
                    THEN 1 ELSE 0
                END
            ) AS open_usajobs
        FROM jobs
        WHERE source LIKE 'usajobs%'
        """
    ).fetchone()
    return {
        "total_usajobs": int(row["total_usajobs"] or 0),
        "current_search": int(row["current_search"] or 0),
        "historic": int(row["historic"] or 0),
        "open_usajobs": int(row["open_usajobs"] or 0),
    }


def _last_completed_import(conn) -> dict | None:
    """Return the most recent successful row from import_manifests, or None.

    Picks the latest by ``completed_at`` so a half-finished newer manifest
    doesn't outrank a finished older one.
    """
    row = conn.execute(
        """
        SELECT id, source, endpoint, status, started_at, completed_at,
               actual_records, pages_completed, filters_json
        FROM import_manifests
        WHERE status = 'completed'
        ORDER BY COALESCE(completed_at, started_at) DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def _bundle_summary() -> dict | None:
    """Return ``manifest.json`` freshness fields, or ``None`` if missing."""
    path = PUBLIC_MAP_DATA / "manifest.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return {
        "generated_at": payload.get("generated_at"),
        "reference_year": payload.get("reference_year"),
        "job_count": int(payload.get("job_count") or 0),
        "feature_count": int(payload.get("feature_count") or 0),
    }


def _bundle_is_stale(conn, bundle: dict | None) -> bool:
    """Bundle is stale when an import completed AFTER the bundle was generated.

    A stale flag tells the operator to re-run the export so the public map
    reflects the latest local data.
    """
    if not bundle or not bundle.get("generated_at"):
        return True
    last = _last_completed_import(conn)
    if not last:
        return False
    completed = last.get("completed_at") or last.get("started_at") or ""
    return bool(completed) and completed > bundle["generated_at"]


def _render_headline(conn) -> None:
    """Top-of-page summary: last import + DB totals + bundle freshness.

    Appears as the first content under the title so the operator can see at
    a glance whether the local data is fresher than what's in the bundle.
    """
    last = _last_completed_import(conn)
    totals = _job_totals(conn)
    bundle = _bundle_summary()
    stale = _bundle_is_stale(conn, bundle)

    cols = st.columns([2, 1, 1, 1, 1])

    if last:
        when_label = _age_label(last.get("completed_at") or last.get("started_at"))
        endpoint = (last.get("endpoint") or last.get("source") or "?").lstrip("/")
        records = int(last.get("actual_records") or 0)
        cols[0].metric(
            "Last completed import",
            when_label,
            delta=f"{records:,} rows · {endpoint}",
            delta_color="off",
        )
    else:
        cols[0].metric("Last completed import", "never", delta="run an importer below")

    cols[1].metric("Open USAJOBS", f"{totals['open_usajobs']:,}")
    cols[2].metric("All USAJOBS", f"{totals['total_usajobs']:,}")

    if bundle:
        bundle_age = _age_label(bundle.get("generated_at"))
        cols[3].metric(
            "Bundle generated",
            bundle_age,
            delta=f"{bundle.get('job_count', 0):,} markers",
            delta_color="off",
        )
        cols[4].metric("Reference year", bundle.get("reference_year") or "—")
    else:
        cols[3].metric("Bundle generated", "missing")
        cols[4].metric("Reference year", "—")

    if stale:
        if bundle and bundle.get("generated_at"):
            st.warning(
                "Bundle is older than the latest import — the public map will not reflect "
                "the most recent local data until you re-export. Use **Refresh all** below "
                "or run `python scripts/export_public_map.py`."
            )
        else:
            st.info(
                "No bundle on disk yet. Run **Refresh all** below or "
                "`python scripts/export_public_map.py` to produce one."
            )


def _refresh_ticker_frame(items: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Status": item["status"],
                "Refreshed item": item["label"],
                "Previous total": item.get("previous"),
                "Current total": item.get("current"),
                "Delta": _format_delta(item.get("previous"), item.get("current")),
            }
            for item in items
        ]
    )


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


def _render_refresh_all(rows: list[dict], conn) -> None:
    st.subheader("Refresh all reference data")
    st.caption(
        "Runs every public-map reference ingest, then rebuilds the static map bundle. "
        "The ticker shows each source's row count before and after the refresh."
    )
    if st.button("Refresh all reference data and export bundle", type="primary", use_container_width=True):
        before = _status_by_key(conn)
        items = [
            {
                "source_key": source_key,
                "label": label,
                "previous": int((before.get(source_key) or {}).get("row_count") or 0),
                "current": int((before.get(source_key) or {}).get("row_count") or 0),
                "status": "PENDING",
                "stdout": "",
                "stderr": "",
            }
            for source_key, label, _cmd in REFRESH_ALL_STEPS
        ]
        items.append(
            {
                "source_key": "public_map_bundle",
                "label": "Static public map bundle",
                "previous": sum(_manifest_layers().values()),
                "current": sum(_manifest_layers().values()),
                "status": "PENDING",
                "stdout": "",
                "stderr": "",
            }
        )

        ticker = st.empty()
        log_container = st.container()
        failures = 0

        for index, (_source_key, _label, cmd) in enumerate(REFRESH_ALL_STEPS):
            items[index]["status"] = "RUNNING"
            ticker.dataframe(_refresh_ticker_frame(items), use_container_width=True, hide_index=True)
            result = _run_subprocess(cmd)
            after = _status_by_key(conn)
            status_row = after.get(items[index]["source_key"]) or {}
            items[index]["current"] = int(status_row.get("row_count") or 0)
            items[index]["stdout"] = result.stdout
            items[index]["stderr"] = result.stderr
            if result.returncode == 0 and not status_row.get("last_error"):
                items[index]["status"] = "OK"
            else:
                items[index]["status"] = "FAILED"
                failures += 1
            ticker.dataframe(_refresh_ticker_frame(items), use_container_width=True, hide_index=True)

        bundle_index = len(items) - 1
        if failures:
            items[bundle_index]["status"] = "SKIPPED"
            ticker.dataframe(_refresh_ticker_frame(items), use_container_width=True, hide_index=True)
            st.error(f"{failures} refresh step(s) failed. Fix those before exporting the public bundle.")
        else:
            items[bundle_index]["status"] = "RUNNING"
            ticker.dataframe(_refresh_ticker_frame(items), use_container_width=True, hide_index=True)
            result = _run_subprocess(["scripts/export_public_map.py"])
            items[bundle_index]["current"] = sum(_manifest_layers().values())
            items[bundle_index]["stdout"] = result.stdout
            items[bundle_index]["stderr"] = result.stderr
            items[bundle_index]["status"] = "OK" if result.returncode == 0 else "FAILED"
            ticker.dataframe(_refresh_ticker_frame(items), use_container_width=True, hide_index=True)
            if result.returncode == 0:
                st.success("Reference data refreshed and public map bundle exported.")
            else:
                st.error(f"Export failed (exit {result.returncode}).")

        with log_container.expander("Refresh logs", expanded=bool(failures)):
            for item in items:
                st.markdown(f"**{item['label']} - {item['status']}**")
                if item.get("stdout"):
                    st.code(item["stdout"], language="text")
                if item.get("stderr"):
                    st.code(item["stderr"], language="text")


def _render_all_jobs_controls(conn) -> None:
    st.subheader("Get all current USAJOBS postings")
    st.caption(
        "Runs the federal-wide current Search import with no agency filter. "
        "Reconnaissance runs first and updates docs/DOWNLOAD_STRATEGY.md."
    )
    before = _job_totals(conn)
    cols = st.columns(4)
    cols[0].metric("All USAJOBS rows", f"{before['total_usajobs']:,}")
    cols[1].metric("Open USAJOBS rows", f"{before['open_usajobs']:,}")
    cols[2].metric("Current Search rows", f"{before['current_search']:,}")
    cols[3].metric("Historic rows", f"{before['historic']:,}")

    no_page_cap = st.toggle(
        "No page cap",
        value=False,
        help="When enabled, the importer follows USAJOBS pagination until the API reports no next page.",
    )
    max_pages = st.number_input(
        "Page cap",
        min_value=1,
        max_value=500,
        value=25,
        step=5,
        disabled=no_page_cap,
    )
    if st.button("Import federal-wide current postings", use_container_width=True):
        cfg = load_config()
        progress = st.empty()
        progress.info("Running data reconnaissance...")
        recommendations = run_public_map_recon(cfg)
        progress.info("Importing federal-wide current Search pages...")
        result = import_current_search(
            conn,
            cfg,
            {},
            max_pages=None if no_page_cap else int(max_pages),
        )
        after = _job_totals(conn)
        progress.success(
            f"Imported {result.records_imported:,} record(s) across "
            f"{result.pages_completed:,} page(s)."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Metric": "All USAJOBS rows",
                        "Previous total": before["total_usajobs"],
                        "Current total": after["total_usajobs"],
                        "Delta": _format_delta(before["total_usajobs"], after["total_usajobs"]),
                    },
                    {
                        "Metric": "Open USAJOBS rows",
                        "Previous total": before["open_usajobs"],
                        "Current total": after["open_usajobs"],
                        "Delta": _format_delta(before["open_usajobs"], after["open_usajobs"]),
                    },
                    {
                        "Metric": "Current Search rows",
                        "Previous total": before["current_search"],
                        "Current total": after["current_search"],
                        "Delta": _format_delta(before["current_search"], after["current_search"]),
                    },
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Recon modes: " + ", ".join(rec.mode for rec in recommendations))


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


# Spot-check sample for D.5.14 — three published OPM cells per year. The
# operator pastes the official values from the OPM PDF; the page compares
# against pay_scales rows for the active reference year and flags any cell
# whose stored rate is more than $1 off the official value.
SPOT_CHECK_SAMPLES: list[tuple[str, int, str]] = [
    ("01", 1, ""),     # GS-1 step 1 base — top-left of the table
    ("13", 1, ""),     # GS-13 step 1 base — referenced by pay-vs-COL math
    ("15", 10, ""),    # GS-15 step 10 base — bottom-right of the table
]


def _reference_year_panel(conn) -> None:
    from src.public_map_export import current_reference_year  # late import to avoid ui import cycles

    ref_year = current_reference_year(conn)
    target = 2026
    if ref_year == target:
        st.success(f"Reference year resolves to **{ref_year}**. ✓ matches the V1 target ({target}).")
    elif ref_year < target:
        st.warning(
            f"Reference year resolves to **{ref_year}** but V1 target is **{target}**. "
            "Run `scripts/refresh_public_map_data.py` (or use Refresh all above) "
            "to load the 2026 seeds, then re-export the bundle."
        )
    else:
        st.info(f"Reference year resolves to **{ref_year}** (ahead of V1 target {target}).")

    st.caption(
        "Per CLAUDE.md invariant 15, V1 ships official OPM 2026 GS base + locality rows. "
        f"The checked-in 2026 seed is computed from the 2025 base × 1.0% across-the-board "
        "raise (per the OPM PDF title \"Incorporating the 1% General Schedule Increase\") "
        "and is **bootstrap data only** until the operator verifies sampled cells against "
        "the official OPM 2026 PDF."
    )

    sample_rows = []
    for grade, step, locality in SPOT_CHECK_SAMPLES:
        row = conn.execute(
            """
            SELECT pay_plan, year, grade, step, locality_code, annual_rate, source, source_url
            FROM pay_scales
            WHERE pay_plan='GS' AND year=? AND grade=? AND step=? AND locality_code=?
            """,
            (ref_year, grade, step, locality),
        ).fetchone()
        sample_rows.append({
            "Cell": f"GS-{int(grade)} step {step}{f' ({locality})' if locality else ' (BASE)'}",
            "Stored rate": f"${int(row['annual_rate']):,}" if row else "—",
            "Source": row["source"] if row else "(missing — run refresh)",
        })
    st.markdown(f"**Sampled {ref_year} GS cells**")
    st.dataframe(pd.DataFrame(sample_rows), use_container_width=True, hide_index=True)
    st.markdown(
        "**Operator verification:** open the OPM 2026 GS PDF "
        "(<https://www.opm.gov/policy-data-oversight/pay-leave/salaries-wages/salary-tables/pdf/2026/GS.pdf>) "
        "and confirm the three cells above. If any value differs by more than $1, "
        "replace `data/external/opm_gs_pay/2026_base.csv` with the official numbers and re-run "
        "`python scripts/ingest_gs_pay.py` from this page's Refresh controls."
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

    # Headline: last import + DB totals + bundle freshness. First thing the
    # operator sees so a stale bundle is impossible to miss.
    _render_headline(conn)

    summary = freshness_summary(conn)
    st.subheader("Data-source health")
    cols = st.columns(5)
    cols[0].metric("Tracked", summary["total"])
    cols[1].metric("Succeeded", summary["succeeded"])
    cols[2].metric("Errored", summary["errored"])
    cols[3].metric("Manual override", summary["manual_override"])
    cols[4].metric("Missing", summary["missing"])

    rows = list_status(conn)
    st.subheader("Data sources")
    _render_status_table(rows)

    _render_refresh_all(rows, conn)
    _render_all_jobs_controls(conn)

    left, right = st.columns(2)
    with left:
        _render_refresh_controls(rows)
    with right:
        _render_override_controls(rows)

    st.subheader("Reference year (D.5.14)")
    _reference_year_panel(conn)

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
