from __future__ import annotations

import plotly.express as px
import streamlit as st

from src.ui_data import app_connection, grouped_counts, salary_by_series, trend_dataframe


st.set_page_config(page_title="Historical Trends", layout="wide")
st.title("Historical Trends")

conn = app_connection()

timeline = trend_dataframe(conn)
if timeline.empty:
    st.info("No dated postings available.")
else:
    fig = px.line(timeline, x="period", y="postings", markers=True)
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)
with left:
    agency = grouped_counts(conn, "agency", limit=15)
    if not agency.empty:
        fig = px.bar(agency.sort_values("postings"), x="postings", y="label", orientation="h")
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

with right:
    series = grouped_counts(conn, "series", limit=15)
    if not series.empty:
        fig = px.bar(series, x="label", y="postings")
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Series")
        st.plotly_chart(fig, use_container_width=True)

salary = salary_by_series(conn)
if not salary.empty:
    st.subheader("Salary by Series")
    st.dataframe(salary, use_container_width=True, hide_index=True)

conn.close()
