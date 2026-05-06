from __future__ import annotations

import streamlit as st

from src.ui_data import app_connection, database_status, grouped_counts, jobs_dataframe


st.set_page_config(
    page_title="Federal Jobs Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    st.title("Federal Jobs Intelligence")
    conn = app_connection()
    status = database_status(conn)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Jobs", f"{status['jobs']:,}")
    metric_cols[1].metric("Current", f"{status['current_jobs']:,}")
    metric_cols[2].metric("Historic", f"{status['historic_jobs']:,}")
    metric_cols[3].metric("Saved", f"{status['saved_jobs']:,}")
    metric_cols[4].metric("Job Text", f"{status['job_text']:,}")
    metric_cols[5].metric("Suggestions", f"{status['job_recommendations']:,}")

    st.divider()
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Recent Postings")
        df = jobs_dataframe(conn)
        st.dataframe(df.head(25), use_container_width=True, hide_index=True)

    with right:
        st.subheader("Freshness")
        st.write(f"Last import: `{status['last_import'] or 'none'}`")
        st.write(f"Last API request: `{status['last_api_request'] or 'none'}`")
        st.write(f"Database: `{status['database_mb']} MB`")
        st.write(f"Raw files: `{status['raw_mb']} MB`")

        by_source = grouped_counts(conn, "source")
        if not by_source.empty:
            st.bar_chart(by_source.set_index("label"))

    conn.close()


if __name__ == "__main__":
    main()
