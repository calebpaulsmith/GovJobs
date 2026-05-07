from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from src.exports import dataframe_to_csv_bytes, dataframe_to_xlsx_bytes
from src.ui_data import (
    app_connection,
    grouped_counts,
    recommendations_dataframe,
    record_feedback_workflow,
    run_match_scores,
    run_similar_jobs,
    scorecard_dataframe,
)


st.set_page_config(page_title="Scorecards", layout="wide")
st.title("Scorecards")

conn = app_connection()

force = st.checkbox("Re-score existing v1 scores")
if st.button("Refresh Scores", type="primary"):
    created = run_match_scores(conn, force=force)
    st.success(f"Scored {created:,} postings.")

scores = scorecard_dataframe(conn)
if scores.empty:
    st.info("No scores recorded yet.")
else:
    st.dataframe(scores, use_container_width=True, hide_index=True)
    export_cols = st.columns(2)
    export_cols[0].download_button(
        "Download Scorecards CSV",
        dataframe_to_csv_bytes(scores),
        file_name="govjobs_scorecards.csv",
        mime="text/csv",
        use_container_width=True,
    )
    export_cols[1].download_button(
        "Download Scorecards Excel",
        dataframe_to_xlsx_bytes(scores, sheet_name="Scorecards", title="GovJobs Scorecards"),
        file_name="govjobs_scorecards.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    selected = st.selectbox(
        "Score detail",
        [f"{row.score} | {row.title} | {row.id}" for row in scores.itertuples()],
    )
    selected_id = int(selected.rsplit("|", 1)[-1].strip())
    detail = conn.execute(
        """
        SELECT positive_factors_json, negative_factors_json, missing_info_json
        FROM match_scores
        WHERE job_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (selected_id,),
    ).fetchone()
    if detail:
        with st.expander("Score factors", expanded=False):
            positives = json.loads(detail["positive_factors_json"] or "[]")
            negatives = json.loads(detail["negative_factors_json"] or "[]")
            missing = json.loads(detail["missing_info_json"] or "[]")
            if positives:
                st.caption("Positive")
                st.dataframe(positives, use_container_width=True, hide_index=True)
            if negatives:
                st.caption("Negative")
                st.dataframe(negatives, use_container_width=True, hide_index=True)
            if missing:
                st.caption("Missing info")
                st.dataframe(missing, use_container_width=True, hide_index=True)

    feedback_options = {
        "Liked": "liked",
        "Disliked": "disliked",
        "More like this": "more_like_this",
        "Less like this": "less_like_this",
    }
    control_left, control_right = st.columns([1, 2])
    with control_left:
        feedback_label = st.selectbox("Feedback", list(feedback_options))
    with control_right:
        feedback_note = st.text_input("Why")
    if st.button("Record Scorecard Feedback"):
        record_feedback_workflow(
            conn,
            job_id=selected_id,
            feedback_type=feedback_options[feedback_label],
            explanation=feedback_note,
        )
        st.success("Feedback recorded.")

    if st.button("Find Similar To Scorecard Selection"):
        run_id = run_similar_jobs(conn, seed_job_id=selected_id, limit=25)
        st.session_state["scorecard_recommendation_run_id"] = run_id
        st.success(f"Recommendation run {run_id} created.")

    run_id = st.session_state.get("scorecard_recommendation_run_id")
    if run_id:
        recommendations = recommendations_dataframe(conn, run_id=run_id)
        if not recommendations.empty:
            st.subheader("Similar jobs")
            st.dataframe(
                recommendations.drop(columns=["factors_json"], errors="ignore"),
                use_container_width=True,
                hide_index=True,
            )
            picked = st.selectbox(
                "Why suggested",
                [
                    f"{row.recommendation_score} | {row.title} | {row.recommendation_id}"
                    for row in recommendations.itertuples()
                ],
            )
            recommendation_id = int(picked.rsplit("|", 1)[-1].strip())
            rec_row = recommendations[recommendations["recommendation_id"] == recommendation_id].iloc[0]
            factors = json.loads(rec_row["factors_json"] or "[]")
            st.dataframe(factors, use_container_width=True, hide_index=True)

left, right = st.columns(2)
with left:
    agencies = grouped_counts(conn, "agency", limit=10)
    if not agencies.empty:
        fig = px.bar(agencies.sort_values("postings"), x="postings", y="label", orientation="h")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

with right:
    grades = grouped_counts(conn, "grade_high", limit=10)
    if not grades.empty:
        fig = px.bar(grades, x="label", y="postings")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Grade")
        st.plotly_chart(fig, use_container_width=True)

conn.close()
