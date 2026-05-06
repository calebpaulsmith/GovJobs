from __future__ import annotations

import streamlit as st

from src.ui_data import alerts_dataframe, app_connection, job_detail, notes_dataframe, saved_jobs_dataframe, tags_for_job


st.set_page_config(page_title="Saved Jobs", layout="wide")
st.title("Saved Jobs")

conn = app_connection()
alerts = alerts_dataframe(conn)
if not alerts.empty:
    st.subheader("Open Alerts")
    st.dataframe(alerts.head(25), use_container_width=True, hide_index=True)

df = saved_jobs_dataframe(conn)

if df.empty:
    st.info("No saved postings yet.")
else:
    st.dataframe(df, use_container_width=True, hide_index=True)
    options = {f"{row.title} | {row.status} | {row.id}": int(row.id) for row in df.itertuples()}
    selected_id = options[st.selectbox("Selected saved posting", list(options))]
    detail = job_detail(conn, selected_id)
    if detail:
        left, right = st.columns([2, 1])
        with left:
            st.subheader(detail["title"] or "Untitled")
            st.write(f"{detail.get('agency') or 'Unknown agency'} | {detail.get('series') or '----'} | {detail.get('state') or '--'}")
            st.write(detail.get("summary") or "")
            if detail.get("qualifications"):
                with st.expander("Qualifications", expanded=False):
                    st.write(detail["qualifications"])
            if detail.get("url"):
                st.link_button("Open USAJOBS", detail["url"])
        with right:
            st.subheader("Tags")
            tags = tags_for_job(conn, selected_id)
            st.write(", ".join(tags) if tags else "None")
            st.subheader("Notes")
            notes = notes_dataframe(conn, selected_id)
            st.dataframe(notes, use_container_width=True, hide_index=True)

conn.close()
