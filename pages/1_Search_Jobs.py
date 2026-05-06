from __future__ import annotations

import json

import streamlit as st

from config import load_config
from src.usajobs_current_api import import_search
from src.ui_data import (
    app_connection,
    feedback_dataframe,
    job_detail,
    jobs_dataframe,
    recommendations_dataframe,
    record_feedback_workflow,
    run_similar_jobs,
    save_job_workflow,
)


st.set_page_config(page_title="Search Jobs", layout="wide")
st.title("Search Jobs")

conn = app_connection()
cfg = load_config()

with st.sidebar:
    st.subheader("Live Search")
    keyword = st.text_input("Keyword")
    organization = st.text_input("Organization code", value="HSCB")
    location = st.text_input("Location")
    series = st.text_input("Series")
    pay_grade_low = st.text_input("Pay grade low")
    pay_grade_high = st.text_input("Pay grade high")
    salary_min = st.number_input("Salary minimum", min_value=0, value=0, step=5000)
    remote_only = st.checkbox("Remote only")
    max_pages = st.number_input("Pages", min_value=1, max_value=20, value=1, step=1)
    run = st.button("Run Search", type="primary", use_container_width=True)

    st.subheader("Local Filters")
    source = st.selectbox("Source", ["All", "usajobs_search", "usajobs_historic"])
    agency_code_filter = st.text_input("Agency code", value=organization)
    department_code_filter = st.text_input("Department code filter")
    agency_filter = st.text_input("Agency contains")
    state_filter = st.text_input("State", max_chars=2)
    pay_plan_filter = st.text_input("Pay plan")
    grade_low_filter = st.text_input("Min grade")
    grade_high_filter = st.text_input("Max grade")
    salary_min_filter = st.number_input("Local salary min", min_value=0, value=0, step=5000)
    salary_max_filter = st.number_input("Local salary max", min_value=0, value=0, step=5000)
    hiring_path_filter = st.text_input("Hiring path")
    remote_filter = st.selectbox("Remote status", ["All", "remote", "hybrid", "onsite", "unknown"])

if run:
    params: dict[str, object] = {"ResultsPerPage": 25, "Page": 1}
    if keyword:
        params["Keyword"] = keyword
    if organization:
        params["Organization"] = organization
    if location:
        params["LocationName"] = location
    if series:
        params["JobCategoryCode"] = series.zfill(4)
    if pay_grade_low:
        params["PayGradeLow"] = pay_grade_low
    if pay_grade_high:
        params["PayGradeHigh"] = pay_grade_high
    if salary_min:
        params["RemunerationMinimumAmount"] = int(salary_min)
    if remote_only:
        params["RemoteIndicator"] = "true"
    with st.spinner("Importing current listings"):
        try:
            result = import_search(conn, cfg, params, max_pages=int(max_pages))
            st.success(f"Imported {result.records_imported:,} current postings.")
        except Exception as exc:
            st.error(str(exc))

filters = {
    "source": source,
    "agency": agency_filter,
    "agency_code": agency_code_filter,
    "department_code": department_code_filter,
    "series": series,
    "pay_plan": pay_plan_filter.upper() if pay_plan_filter else "",
    "grade_low": grade_low_filter,
    "grade_high": grade_high_filter,
    "salary_min": salary_min_filter or None,
    "salary_max": salary_max_filter or None,
    "hiring_path": hiring_path_filter,
    "state": state_filter.upper() if state_filter else "All",
    "remote_status": remote_filter,
    "keyword": keyword,
}
df = jobs_dataframe(conn, filters)

st.subheader("Postings")
st.dataframe(df, use_container_width=True, hide_index=True)

if not df.empty:
    options = {
        f"{row.title} | {row.agency or 'Unknown'} | {row.id}": int(row.id)
        for row in df.itertuples()
    }
    selected_label = st.selectbox("Selected posting", list(options))
    selected_id = options[selected_label]
    detail = job_detail(conn, selected_id)

    if detail:
        left, right = st.columns([2, 1])
        with left:
            st.subheader(detail["title"] or "Untitled")
            st.write(f"{detail.get('agency') or 'Unknown agency'} | {detail.get('series') or '----'} | {detail.get('grade_low') or ''}-{detail.get('grade_high') or ''}")
            if detail.get("score") is not None:
                st.metric("Match score", f"{int(detail['score'])}/100")
                st.write(detail.get("score_explanation") or "")
                with st.expander("Score factors", expanded=False):
                    positives = json.loads(detail.get("positive_factors_json") or "[]")
                    negatives = json.loads(detail.get("negative_factors_json") or "[]")
                    missing = json.loads(detail.get("missing_info_json") or "[]")
                    if positives:
                        st.caption("Positive")
                        st.dataframe(positives, use_container_width=True, hide_index=True)
                    if negatives:
                        st.caption("Negative")
                        st.dataframe(negatives, use_container_width=True, hide_index=True)
                    if missing:
                        st.caption("Missing info")
                        st.dataframe(missing, use_container_width=True, hide_index=True)
            st.write(detail.get("summary") or "")
            if detail.get("qualifications"):
                with st.expander("Qualifications", expanded=False):
                    st.write(detail["qualifications"])
            if detail.get("duties"):
                with st.expander("Duties", expanded=False):
                    st.write(detail["duties"])
            if detail.get("url"):
                st.link_button("Open USAJOBS", detail["url"])

        with right:
            st.subheader("Save")
            status = st.selectbox(
                "Status",
                [
                    "New",
                    "Interested",
                    "Maybe",
                    "Applied",
                    "Referred",
                    "Interview",
                    "Selected",
                    "Not selected",
                    "Skip",
                    "Archived",
                ],
            )
            priority = st.number_input("Priority", min_value=1, max_value=5, value=3, step=1)
            tag = st.text_input("Tag")
            note = st.text_area("Note", height=120)
            if st.button("Save Posting", type="primary", use_container_width=True):
                save_job_workflow(
                    conn,
                    job_id=selected_id,
                    status=status,
                    priority=int(priority),
                    note=note,
                    tag=tag,
                )
                st.success("Saved.")

            st.subheader("Preference")
            feedback_options = {
                "Liked": "liked",
                "Disliked": "disliked",
                "More like this": "more_like_this",
                "Less like this": "less_like_this",
            }
            feedback_label = st.selectbox("Feedback", list(feedback_options))
            feedback_note = st.text_area("Why", height=90, key=f"feedback_note_{selected_id}")
            if st.button("Record Feedback", use_container_width=True):
                record_feedback_workflow(
                    conn,
                    job_id=selected_id,
                    feedback_type=feedback_options[feedback_label],
                    explanation=feedback_note,
                )
                st.success("Feedback recorded.")
            if st.button("Find Similar Jobs", use_container_width=True):
                run_id = run_similar_jobs(conn, seed_job_id=selected_id, limit=25)
                st.session_state["latest_recommendation_run_id"] = run_id
                st.success(f"Recommendation run {run_id} created.")

        feedback = feedback_dataframe(conn, selected_id)
        if not feedback.empty:
            with st.expander("Recorded feedback", expanded=False):
                st.dataframe(feedback, use_container_width=True, hide_index=True)

        latest_run_id = st.session_state.get("latest_recommendation_run_id")
        recommendations = recommendations_dataframe(conn, run_id=latest_run_id) if latest_run_id else recommendations_dataframe(conn)
        if not recommendations.empty:
            st.subheader("Similar Jobs")
            visible = recommendations.drop(columns=["factors_json"], errors="ignore")
            st.dataframe(visible, use_container_width=True, hide_index=True)
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

conn.close()
