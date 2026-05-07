from __future__ import annotations

import streamlit as st

from src.exports import dataframe_to_csv_bytes, dataframe_to_xlsx_bytes
from src.ui_data import (
    add_application_event_workflow,
    app_connection,
    application_events_dataframe,
    applications_dataframe,
    resume_versions_dataframe,
    saved_jobs_dataframe,
    upsert_application_workflow,
)


APPLICATION_STATUSES = [
    "Draft",
    "Submitted",
    "Referred",
    "Interview",
    "Selected",
    "Not selected",
    "Withdrawn",
    "Archived",
]


st.set_page_config(page_title="Application Tracker", layout="wide")
st.title("Application Tracker")

conn = app_connection()
applications = applications_dataframe(conn)
saved_jobs = saved_jobs_dataframe(conn)
resume_versions = resume_versions_dataframe(conn, active_only=True)

metric_cols = st.columns(4)
metric_cols[0].metric("Applications", f"{len(applications):,}")
metric_cols[1].metric(
    "Submitted+",
    f"{len(applications[applications['application_status'].isin(['Submitted', 'Referred', 'Interview', 'Selected', 'Not selected'])]):,}"
    if not applications.empty
    else "0",
)
metric_cols[2].metric(
    "Interviews",
    f"{len(applications[applications['application_status'] == 'Interview']):,}" if not applications.empty else "0",
)
metric_cols[3].metric(
    "Next Actions",
    f"{applications['next_action_due'].notna().sum():,}" if not applications.empty else "0",
)

st.subheader("Application Queue")
if applications.empty:
    st.info("No tracked applications yet. Start from a saved job below.")
else:
    st.dataframe(applications, use_container_width=True, hide_index=True)
    export_cols = st.columns(2)
    export_cols[0].download_button(
        "Download Applications CSV",
        dataframe_to_csv_bytes(applications),
        file_name="govjobs_applications.csv",
        mime="text/csv",
        use_container_width=True,
    )
    export_cols[1].download_button(
        "Download Applications Excel",
        dataframe_to_xlsx_bytes(applications, sheet_name="Applications", title="GovJobs Applications"),
        file_name="govjobs_applications.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.subheader("Create Or Update")
if saved_jobs.empty:
    st.info("Save a posting before tracking an application.")
else:
    saved_options = {
        f"{row.title} | {row.status} | {row.id}": int(row.id)
        for row in saved_jobs.itertuples()
    }
    selected_job_id = saved_options[st.selectbox("Saved posting", list(saved_options))]
    existing = applications[applications["job_id"] == selected_job_id]
    existing_row = existing.iloc[0].to_dict() if not existing.empty else {}

    left, right = st.columns(2)
    with left:
        default_status = existing_row.get("application_status") or "Draft"
        status = st.selectbox(
            "Application status",
            APPLICATION_STATUSES,
            index=APPLICATION_STATUSES.index(default_status)
            if default_status in APPLICATION_STATUSES
            else 0,
        )
        existing_resume = existing_row.get("resume_version") or ""
        resume_labels = resume_versions["label"].tolist() if not resume_versions.empty else []
        resume_options = ["Manual entry"] + resume_labels
        default_resume_index = resume_options.index(existing_resume) if existing_resume in resume_options else 0
        selected_resume = st.selectbox("Resume version", resume_options, index=default_resume_index)
        manual_resume_value = "" if selected_resume != "Manual entry" else existing_resume
        resume_version = (
            st.text_input("Manual resume version", value=manual_resume_value)
            if selected_resume == "Manual entry"
            else selected_resume
        )
        usajobs_application_id = st.text_input(
            "USAJOBS application/reference ID",
            value=existing_row.get("usajobs_application_id") or "",
        )
        application_url = st.text_input("Application URL", value=existing_row.get("application_url") or "")
        submitted_at = st.text_input("Submitted date YYYY-MM-DD", value=existing_row.get("submitted_at") or "")
        referred_at = st.text_input("Referred date YYYY-MM-DD", value=existing_row.get("referred_at") or "")
        interview_at = st.text_input("Interview date YYYY-MM-DD", value=existing_row.get("interview_at") or "")
    with right:
        outcome = st.text_input("Outcome", value=existing_row.get("outcome") or "")
        next_action = st.text_input("Next action", value=existing_row.get("next_action") or "")
        next_action_due = st.text_input("Next action due YYYY-MM-DD", value=existing_row.get("next_action_due") or "")
        contact_name = st.text_input("Contact name", value=existing_row.get("contact_name") or "")
        contact_email = st.text_input("Contact email", value=existing_row.get("contact_email") or "")
        notes = st.text_area("Application notes", value=existing_row.get("notes") or "", height=120)
        event_note = st.text_area("Add event note", height=90)

    if st.button("Save Application", type="primary", use_container_width=True):
        application_id = upsert_application_workflow(
            conn,
            job_id=selected_job_id,
            application_status=status,
            resume_version=resume_version,
            usajobs_application_id=usajobs_application_id,
            application_url=application_url,
            submitted_at=submitted_at,
            referred_at=referred_at,
            interview_at=interview_at,
            outcome=outcome,
            next_action=next_action,
            next_action_due=next_action_due,
            contact_name=contact_name,
            contact_email=contact_email,
            notes=notes,
            event_note=event_note,
        )
        st.success(f"Application {application_id} saved.")

if not applications.empty:
    st.subheader("Event History")
    app_options = {
        f"{row.application_status} | {row.title} | {row.application_id}": int(row.application_id)
        for row in applications.itertuples()
    }
    selected_application_id = app_options[st.selectbox("Tracked application", list(app_options))]
    events = application_events_dataframe(conn, selected_application_id)
    st.dataframe(events, use_container_width=True, hide_index=True)

    event_cols = st.columns([1, 1, 2])
    with event_cols[0]:
        event_type = st.text_input("Event type", value="note")
    with event_cols[1]:
        event_date = st.text_input("Event date YYYY-MM-DD")
    with event_cols[2]:
        event_notes = st.text_input("Event notes")
    if st.button("Add Event", use_container_width=True):
        add_application_event_workflow(
            conn,
            application_id=selected_application_id,
            event_type=event_type,
            event_date=event_date,
            notes=event_notes,
        )
        st.success("Event added.")

conn.close()
