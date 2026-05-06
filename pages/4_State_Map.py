from __future__ import annotations

import plotly.express as px
import streamlit as st

from src.ui_data import app_connection, opm_state_counts, remote_counts, state_counts


st.set_page_config(page_title="State Map", layout="wide")
st.title("State Map")

conn = app_connection()
source_layer = st.radio(
    "Data source",
    ["USAJOBS postings", "OPM workforce"],
    horizontal=True,
)

if source_layer == "USAJOBS postings":
    states = state_counts(conn)
    color_column = "postings"
    legend = "USAJOBS postings"
    title = "USAJOBS postings by state"
else:
    metric = st.selectbox("OPM metric", ["employment", "accessions", "separations"])
    states = opm_state_counts(conn, metric=metric)
    color_column = {
        "employment": "workforce_count",
        "accessions": "accessions",
        "separations": "separations",
    }[metric]
    legend = {
        "employment": "OPM workforce count",
        "accessions": "OPM accessions",
        "separations": "OPM separations",
    }[metric]
    title = f"{legend} by state"

if states.empty:
    st.info(f"No state-normalized {source_layer.lower()} data available.")
else:
    st.caption(title)
    fig = px.choropleth(
        states,
        locations="state",
        locationmode="USA-states",
        color=color_column,
        scope="usa",
        color_continuous_scale="Teal",
        labels={color_column: legend},
    )
    fig.update_layout(height=540, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(states, use_container_width=True, hide_index=True)

if source_layer == "USAJOBS postings":
    remote = remote_counts(conn)
    if not remote.empty:
        st.subheader("Remote And Telework")
        st.bar_chart(remote.set_index("label"))
else:
    st.caption("OPM workforce, accessions, and separations are not USAJOBS postings.")

conn.close()
