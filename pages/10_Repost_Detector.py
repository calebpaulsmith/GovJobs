from __future__ import annotations

import json

import streamlit as st

from src.exports import dataframe_to_csv_bytes, dataframe_to_xlsx_bytes
from src.ui_data import (
    app_connection,
    repost_group_members_dataframe,
    repost_groups_dataframe,
    run_repost_detection,
)


st.set_page_config(page_title="Repost Detector", layout="wide")
st.title("Repost Detector")

conn = app_connection()

if st.button("Run Repost Detector", type="primary", use_container_width=True):
    with st.spinner("Comparing titles, agency/series blocks, and text fingerprints"):
        groups_created = run_repost_detection(conn)
    st.success(f"Detected {groups_created:,} possible repost group(s).")

groups = repost_groups_dataframe(conn)
members = repost_group_members_dataframe(conn)

metric_cols = st.columns(3)
metric_cols[0].metric("Groups", f"{len(groups):,}")
metric_cols[1].metric("Member Rows", f"{len(members):,}")
metric_cols[2].metric(
    "Highest Confidence",
    f"{groups['confidence_score'].max():.2f}" if not groups.empty else "n/a",
)

st.subheader("Possible Repost Groups")
if groups.empty:
    st.info("No repost detector run has found groups yet.")
else:
    visible_groups = groups.drop(columns=["evidence_json"], errors="ignore")
    st.dataframe(visible_groups, use_container_width=True, hide_index=True)
    export_cols = st.columns(2)
    export_cols[0].download_button(
        "Download Groups CSV",
        dataframe_to_csv_bytes(visible_groups),
        file_name="govjobs_repost_groups.csv",
        mime="text/csv",
        use_container_width=True,
    )
    export_cols[1].download_button(
        "Download Groups Excel",
        dataframe_to_xlsx_bytes(visible_groups, sheet_name="Repost Groups", title="GovJobs Repost Groups"),
        file_name="govjobs_repost_groups.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    options = {
        f"{row.group_title} | {row.member_count} postings | {row.group_id}": int(row.group_id)
        for row in groups.itertuples()
    }
    selected_group_id = options[st.selectbox("Inspect group", list(options))]
    selected_members = repost_group_members_dataframe(conn, selected_group_id)
    st.subheader("Group Members")
    st.dataframe(selected_members, use_container_width=True, hide_index=True)

    selected_group = groups[groups["group_id"] == selected_group_id].iloc[0]
    with st.expander("Detection Evidence", expanded=False):
        try:
            evidence = json.loads(selected_group["evidence_json"])
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        st.json(evidence)

conn.close()
