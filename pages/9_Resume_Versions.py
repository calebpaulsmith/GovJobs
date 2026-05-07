from __future__ import annotations

import streamlit as st

from src.exports import dataframe_to_csv_bytes, dataframe_to_xlsx_bytes
from src.ui_data import (
    app_connection,
    resume_versions_dataframe,
    set_resume_version_active_workflow,
    upsert_resume_version_workflow,
)


st.set_page_config(page_title="Resume Versions", layout="wide")
st.title("Resume Versions")

conn = app_connection()
versions = resume_versions_dataframe(conn)

metric_cols = st.columns(3)
metric_cols[0].metric("Resume Versions", f"{len(versions):,}")
metric_cols[1].metric("Active", f"{int(versions['active'].sum()) if not versions.empty else 0:,}")
metric_cols[2].metric("Archived", f"{len(versions[versions['active'] == 0]) if not versions.empty else 0:,}")

st.subheader("Version Library")
if versions.empty:
    st.info("No resume versions recorded yet.")
else:
    st.dataframe(versions, use_container_width=True, hide_index=True)
    export_cols = st.columns(2)
    export_cols[0].download_button(
        "Download Resume Versions CSV",
        dataframe_to_csv_bytes(versions),
        file_name="govjobs_resume_versions.csv",
        mime="text/csv",
        use_container_width=True,
    )
    export_cols[1].download_button(
        "Download Resume Versions Excel",
        dataframe_to_xlsx_bytes(versions, sheet_name="Resume Versions", title="GovJobs Resume Versions"),
        file_name="govjobs_resume_versions.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.subheader("Create Or Update")
with st.form("resume_version_form"):
    left, right = st.columns(2)
    with left:
        label = st.text_input("Version label", placeholder="fema-gs13-mitigation-v3")
        file_name = st.text_input("File name", placeholder="Caleb_FEMA_GS13_Mitigation_v3.pdf")
        file_path = st.text_input("Local file path")
        version_date = st.text_input("Version date YYYY-MM-DD")
    with right:
        target_series = st.text_input("Target series", placeholder="0089, 0343")
        target_grade = st.text_input("Target grade", placeholder="GS-13")
        active = st.checkbox("Active", value=True)
        notes = st.text_area("Notes", height=120)
    submitted = st.form_submit_button("Save Resume Version", type="primary", use_container_width=True)

if submitted:
    try:
        version_id = upsert_resume_version_workflow(
            conn,
            label=label,
            file_name=file_name,
            file_path=file_path,
            version_date=version_date,
            target_series=target_series,
            target_grade=target_grade,
            notes=notes,
            active=active,
        )
        st.success(f"Resume version {version_id} saved.")
    except ValueError as exc:
        st.error(str(exc))

if not versions.empty:
    st.subheader("Archive Or Restore")
    version_options = {f"{row.label} | {'active' if row.active else 'archived'} | {row.id}": int(row.id) for row in versions.itertuples()}
    selected_version_id = version_options[st.selectbox("Resume version", list(version_options))]
    action = st.radio("Status", ["Active", "Archived"], horizontal=True)
    if st.button("Update Status", use_container_width=True):
        set_resume_version_active_workflow(conn, selected_version_id, active=action == "Active")
        st.success("Resume version status updated.")

conn.close()
