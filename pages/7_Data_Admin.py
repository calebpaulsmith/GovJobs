from __future__ import annotations

import streamlit as st

from config import load_config
from src.opm_data import import_opm_file
from src.usajobs_announcement_text_api import import_announcement_text_filters
from src.usajobs_historic_api import import_historic
from src.ui_data import (
    alerts_dataframe,
    app_connection,
    database_status,
    dismiss_alert_workflow,
    manifests_dataframe,
    opm_datasets_dataframe,
    raw_responses_dataframe,
    run_alerts,
)


st.set_page_config(page_title="Data Admin", layout="wide")
st.title("Data Admin")

conn = app_connection()
cfg = load_config()
status = database_status(conn)

cols = st.columns(4)
cols[0].metric("Jobs", f"{status['jobs']:,}")
cols[1].metric("Raw Files", f"{status['raw_mb']} MB")
cols[2].metric("Database", f"{status['database_mb']} MB")
cols[3].metric("OPM Records", f"{status['opm_records']:,}")

child_cols = st.columns(4)
child_cols[0].metric("Locations", f"{status['job_locations']:,}")
child_cols[1].metric("Categories", f"{status['job_categories']:,}")
child_cols[2].metric("Hiring Paths", f"{status['job_hiring_paths']:,}")
child_cols[3].metric("Req Docs", f"{status['job_required_documents']:,}")

evidence_cols = st.columns(4)
evidence_cols[0].metric("Grades", f"{status['job_grades']:,}")
evidence_cols[1].metric("Salary Ranges", f"{status['job_salary_ranges']:,}")
evidence_cols[2].metric("Requirements", f"{status['job_requirements']:,}")
evidence_cols[3].metric("Qual Evidence", f"{status['job_qualification_requirements']:,}")

condition_cols = st.columns(4)
condition_cols[0].metric("Openings", f"{status['job_openings']:,}")
condition_cols[1].metric("Contacts", f"{status['job_contacts']:,}")
condition_cols[2].metric("Security", f"{status['job_security_clearances']:,}")
condition_cols[3].metric("Travel", f"{status['job_travel_requirements']:,}")

recommendation_cols = st.columns(4)
recommendation_cols[0].metric("Feedback", f"{status['job_feedback']:,}")
recommendation_cols[1].metric("Recommendation Runs", f"{status['recommendation_runs']:,}")
recommendation_cols[2].metric("Suggestions", f"{status['job_recommendations']:,}")
recommendation_cols[3].metric("Application Options", f"{status['job_application_options']:,}")

alert_cols = st.columns(4)
alert_cols[0].metric("Open Alerts", f"{status['open_alerts']:,}")
alert_cols[1].metric("Total Alerts", f"{status['alerts']:,}")
alert_cols[2].metric("Last Alert Run", status["last_alert_run"] or "Never")
if alert_cols[3].button("Run Alerts", type="primary", use_container_width=True):
    with st.spinner("Generating local alerts"):
        created = run_alerts(conn)
    st.success(f"Created {created:,} new alert(s).")

st.subheader("Alerts")
show_dismissed = st.checkbox("Show dismissed alerts", value=False)
alerts = alerts_dataframe(conn, include_dismissed=show_dismissed)
if alerts.empty:
    st.info("No alerts yet.")
else:
    st.dataframe(alerts, use_container_width=True, hide_index=True)
    st.download_button(
        "Download Alerts CSV",
        alerts.to_csv(index=False),
        file_name="govjobs_alerts.csv",
        mime="text/csv",
        use_container_width=True,
    )
    active_alerts = alerts[alerts["status"] != "dismissed"]
    if not active_alerts.empty:
        options = {
            f"{row.alert_type} | {row.job_title or row.title} | {row.id}": int(row.id)
            for row in active_alerts.itertuples()
        }
        selected_alert_id = options[st.selectbox("Dismiss alert", list(options))]
        if st.button("Dismiss Selected Alert", use_container_width=True):
            dismiss_alert_workflow(conn, selected_alert_id)
            st.success("Alert dismissed.")

st.subheader("OPM Workforce Import")
opm_left, opm_right = st.columns([2, 1])
with opm_left:
    uploaded_opm = st.file_uploader("OPM/FedScope file", type=["csv", "tsv", "txt", "xlsx", "xls", "zip"])
    opm_path = st.text_input("Or local file path")
with opm_right:
    opm_dataset = st.text_input("Dataset name", value="fedscope_employment")
    opm_max_rows = st.number_input("Max rows", min_value=0, value=10000, step=1000)
    opm_clear = st.checkbox("Replace existing rows for this dataset")
    run_opm = st.button("Import OPM File", use_container_width=True)

if run_opm:
    try:
        source_path = None
        if uploaded_opm is not None:
            opm_dir = cfg.raw_data_path / "opm_workforce"
            opm_dir.mkdir(parents=True, exist_ok=True)
            source_path = opm_dir / uploaded_opm.name
            source_path.write_bytes(uploaded_opm.getbuffer())
        elif opm_path:
            source_path = opm_path
        if source_path is None:
            st.error("Choose an uploaded OPM file or provide a local file path.")
        else:
            with st.spinner("Importing OPM workforce file"):
                result = import_opm_file(
                    conn,
                    cfg,
                    source_path,
                    dataset=opm_dataset,
                    max_rows=int(opm_max_rows) if opm_max_rows else None,
                    clear_existing=opm_clear,
                )
            st.success(f"Imported {result.records_imported:,} OPM row(s).")
    except Exception as exc:
        st.error(str(exc))

opm_sets = opm_datasets_dataframe(conn)
if not opm_sets.empty:
    st.dataframe(opm_sets, use_container_width=True, hide_index=True)

st.subheader("Filter-Scoped Historic Import")
left, dept, mid, ids = st.columns([1, 1, 1, 1])
with left:
    agency_codes = st.text_input("Agency codes", value="HSCB")
with dept:
    department_codes = st.text_input("Department codes")
with mid:
    series = st.text_input("Series")
with ids:
    announcement_numbers = st.text_input("Announcement numbers")
    control_numbers = st.text_input("USAJOBS control numbers")

dates = st.columns(5)
with dates[0]:
    start = st.date_input("Start date")
with dates[1]:
    end = st.date_input("End date")
with dates[2]:
    close_start = st.text_input("Close start YYYY-MM-DD")
with dates[3]:
    close_end = st.text_input("Close end YYYY-MM-DD")
with dates[4]:
    max_pages = st.number_input("Max pages", min_value=1, max_value=20, value=1, step=1)
    run = st.button("Run Historic", type="primary", use_container_width=True)

if run:
    params = {
        "HiringAgencyCodes": agency_codes,
        "StartPositionOpenDate": start.isoformat(),
        "EndPositionOpenDate": end.isoformat(),
    }
    if department_codes:
        params["HiringDepartmentCodes"] = department_codes
    if series:
        params["PositionSeries"] = series
    if announcement_numbers:
        params["AnnouncementNumbers"] = announcement_numbers
    if control_numbers:
        params["USAJOBSControlNumbers"] = control_numbers
    if close_start:
        params["StartPositionCloseDate"] = close_start
    if close_end:
        params["EndPositionCloseDate"] = close_end
    with st.spinner("Importing HistoricJoa slice"):
        try:
            result = import_historic(
                conn,
                cfg,
                params,
                max_pages=int(max_pages),
                download_mode="SAMPLE_ONLY",
            )
            st.success(f"Imported {result.records_imported:,} postings.")
        except Exception as exc:
            st.error(str(exc))

if st.button("Import Announcement Text For Same Filters", use_container_width=True):
    params = {
        "HiringAgencyCodes": agency_codes,
        "StartPositionOpenDate": start.isoformat(),
        "EndPositionOpenDate": end.isoformat(),
    }
    if department_codes:
        params["HiringDepartmentCodes"] = department_codes
    if series:
        params["PositionSeries"] = series
    if announcement_numbers:
        params["AnnouncementNumbers"] = announcement_numbers
    if control_numbers:
        params["USAJOBSControlNumbers"] = control_numbers
    if close_start:
        params["StartPositionCloseDate"] = close_start
    if close_end:
        params["EndPositionCloseDate"] = close_end
    with st.spinner("Importing selected AnnouncementText"):
        try:
            result = import_announcement_text_filters(
                conn,
                cfg,
                params,
                max_pages=int(max_pages),
                download_mode="SAMPLE_ONLY",
            )
            st.success(f"Imported text for {result.records_imported:,} postings.")
        except Exception as exc:
            st.error(str(exc))

st.subheader("Import Manifests")
st.dataframe(manifests_dataframe(conn), use_container_width=True, hide_index=True)

st.subheader("Raw API Responses")
st.dataframe(raw_responses_dataframe(conn), use_container_width=True, hide_index=True)

conn.close()
