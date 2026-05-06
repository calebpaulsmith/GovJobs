from __future__ import annotations

import json

import streamlit as st

from config import load_config
from src.ui_data import app_connection, create_saved_search, saved_searches_dataframe


st.set_page_config(page_title="Settings", layout="wide")
st.title("Settings")

cfg = load_config()
conn = app_connection()

left, right = st.columns(2)
with left:
    st.subheader("Paths")
    st.write(f"Database: `{cfg.database_path}`")
    st.write(f"Raw data: `{cfg.raw_data_path}`")
    st.write(f"Processed data: `{cfg.processed_data_path}`")
    st.write(f"USAJOBS credentials: `{'present' if cfg.has_usajobs_credentials else 'missing'}`")

with right:
    st.subheader("Saved Search")
    name = st.text_input("Name")
    keyword = st.text_input("Keyword")
    location = st.text_input("Location")
    series = st.text_input("Series")
    alerts = st.checkbox("Alert enabled")
    if st.button("Create Saved Search", type="primary"):
        params = {
            key: value
            for key, value in {
                "Keyword": keyword,
                "LocationName": location,
                "JobCategoryCode": series.zfill(4) if series else "",
            }.items()
            if value
        }
        create_saved_search(conn, name=name or keyword or "Saved search", query_params=params, alert_enabled=alerts)
        st.success("Saved.")

st.subheader("Saved Searches")
searches = saved_searches_dataframe(conn)
if not searches.empty:
    display = searches.copy()
    display["query_params_json"] = display["query_params_json"].apply(
        lambda value: json.dumps(json.loads(value), indent=2)
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info("No saved searches.")

conn.close()
