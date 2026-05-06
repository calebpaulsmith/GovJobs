"""Transparent rule-based job match scoring for V1."""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.database import record_match_score


SCORING_VERSION = "v1.0"

TARGET_AGENCY_CODES = {"HSCB", "HS"}
PRIORITY_SERIES = {
    "0089": 10,
    "0343": 8,
    "0301": 8,
    "1109": 8,
    "0020": 5,
    "0101": 5,
    "0110": 5,
    "0300": 5,
    "0501": 5,
    "0560": 5,
}
MIDWEST_STATES = {"IL", "WI", "IN", "MI", "MN", "MO", "IA", "OH"}


@dataclass(frozen=True)
class ScoringResult:
    score: int
    explanation: str
    positive_factors: list[dict[str, Any]]
    negative_factors: list[dict[str, Any]]
    missing_info: list[dict[str, Any]]
    scoring_version: str = SCORING_VERSION


def score_job(job: Mapping[str, Any]) -> ScoringResult:
    positives: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    text = _combined_text(job)
    agency_text = _combined_text_fields(job, ("agency", "department", "sub_agency", "title"))
    series = _series_values(job)
    grades = _grade_values(job)
    states = _state_values(job)

    _score_agency(job, agency_text, positives, missing)
    _score_series(series, positives, missing)
    _score_grades(grades, positives, negatives, missing)
    if not _long_text(job).strip():
        missing.append({"field": "job_text", "reason": "No summary/duties/qualifications text available."})
    _score_topics(text, positives, missing)
    _score_location(job, text, states, positives, negatives, missing)
    _score_work_style(job, positives, missing)
    _score_supervisory(job, text, positives)

    if not positives:
        negatives.append(
            _factor("weak target match", -10, "No FEMA/DHS, priority-series, target-grade, location, or domain signal found.")
        )

    raw_score = sum(int(factor["weight"]) for factor in positives + negatives)
    score = max(0, min(100, raw_score))
    explanation = _explanation(score, positives, negatives, missing)
    return ScoringResult(
        score=score,
        explanation=explanation,
        positive_factors=positives,
        negative_factors=negatives,
        missing_info=missing,
    )


def score_all_jobs(conn: sqlite3.Connection, *, force: bool = False) -> int:
    sql = "SELECT id FROM jobs"
    if not force:
        sql += """
        WHERE id NOT IN (
            SELECT job_id FROM match_scores WHERE scoring_version=?
        )
        """
        rows = conn.execute(sql, (SCORING_VERSION,)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()

    scored = 0
    for row in rows:
        job_id = int(row["id"])
        result = score_job(scoring_context(conn, job_id))
        record_match_score(
            conn,
            job_id=job_id,
            score=result.score,
            scoring_version=result.scoring_version,
            explanation=result.explanation,
            positive_factors=result.positive_factors,
            negative_factors=result.negative_factors,
            missing_info=result.missing_info,
        )
        scored += 1
    return scored


def scoring_context(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT j.*, jt.summary, jt.duties, jt.qualifications, jt.specialized_experience,
               jt.education, jt.required_documents, jt.evaluation_criteria,
               jt.conditions_of_employment
        FROM jobs j
        LEFT JOIN job_text jt ON jt.job_id = j.id
        WHERE j.id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"job_id does not exist: {job_id}")
    context = dict(row)
    context["series_values"] = [
        item["series"]
        for item in conn.execute(
            "SELECT series FROM job_categories WHERE job_id=? ORDER BY is_primary DESC, series",
            (job_id,),
        )
    ]
    context["grades"] = [
        dict(item)
        for item in conn.execute(
            """
            SELECT pay_plan, grade_low, grade_high, promotion_potential
            FROM job_grades
            WHERE job_id=?
            """,
            (job_id,),
        )
    ]
    context["locations"] = [
        dict(item)
        for item in conn.execute(
            "SELECT city, state, location_text, remote_indicator FROM job_locations WHERE job_id=?",
            (job_id,),
        )
    ]
    context["requirements"] = _text_list(
        conn,
        "SELECT description FROM job_requirements WHERE job_id=? ORDER BY sequence, id",
        job_id,
    )
    context["qualification_requirements"] = _text_list(
        conn,
        "SELECT text FROM job_qualification_requirements WHERE job_id=? ORDER BY sequence, id",
        job_id,
    )
    context["duty_rows"] = _text_list(
        conn,
        "SELECT duty_text FROM job_duties WHERE job_id=? ORDER BY sequence, id",
        job_id,
    )
    context["evaluation_factors"] = _text_list(
        conn,
        "SELECT factor_text FROM job_evaluation_factors WHERE job_id=? ORDER BY sequence, id",
        job_id,
    )
    return context


def _score_agency(
    job: Mapping[str, Any],
    agency_text: str,
    positives: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    agency_code = str(job.get("agency_code") or "").upper()
    department_code = str(job.get("department_code") or "").upper()
    if agency_code == "HSCB" or "federal emergency management agency" in agency_text or "fema" in agency_text:
        positives.append(_factor("FEMA", 20, _evidence(agency_text, "fema") or "FEMA/HSCB"))
    elif department_code == "HS" or "department of homeland security" in agency_text:
        positives.append(_factor("DHS", 12, _evidence(agency_text, "homeland security") or "DHS/HS"))
    elif agency_code in TARGET_AGENCY_CODES:
        positives.append(_factor("target agency code", 8, agency_code))
    elif not agency_text.strip() and not agency_code:
        missing.append({"field": "agency", "reason": "Agency name/code is missing."})


def _score_series(
    series_values: set[str],
    positives: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    if not series_values:
        missing.append({"field": "series", "reason": "Occupational series is missing."})
        return
    for series, weight in PRIORITY_SERIES.items():
        if series in series_values:
            positives.append(_factor("priority series", weight, series))
            return


def _score_grades(
    grades: set[int],
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    if not grades:
        missing.append({"field": "grade", "reason": "Grade range is missing."})
        return
    if grades & {13, 14, 15}:
        highest = max(grades & {13, 14, 15})
        positives.append(_factor("target grade", {13: 10, 14: 12, 15: 12}[highest], f"GS-{highest}"))
    elif max(grades) == 12:
        positives.append(_factor("near target grade", 4, "GS-12"))
    elif max(grades) < 12:
        negatives.append(_factor("below target grade", -8, f"highest grade GS-{max(grades)}"))


def _score_topics(text: str, positives: list[dict[str, Any]], missing: list[dict[str, Any]]) -> None:
    if not text.strip():
        return
    topic_rules = [
        ("emergency management", 10, r"emergency management"),
        ("mitigation", 9, r"\bmitigation\b|hazard mitigation"),
        ("public assistance", 8, r"public assistance"),
        ("grants management", 8, r"grants? management|\bgrant(s)?\b"),
        ("disaster recovery", 8, r"disaster recovery|\brecovery\b"),
        ("policy/program analysis", 8, r"policy analysis|program analysis|management and program"),
        ("infrastructure", 6, r"\binfrastructure\b"),
        ("resilience", 6, r"\bresilien(ce|t)\b"),
    ]
    for factor, weight, pattern in topic_rules:
        match = re.search(pattern, text, flags=re.I)
        if match:
            positives.append(_factor(factor, weight, _window(text, match.start(), match.end())))


def _score_location(
    job: Mapping[str, Any],
    text: str,
    states: set[str],
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    city = str(job.get("city") or "").lower()
    location_text = " ".join(
        str(value or "")
        for value in (job.get("location_text"), job.get("city"), job.get("state"), text[:500])
    ).lower()
    if "chicago" in city or "chicago" in location_text:
        positives.append(_factor("Chicago", 8, _evidence(location_text, "chicago") or "Chicago"))
    elif states & MIDWEST_STATES:
        positives.append(_factor("Midwest", 5, ", ".join(sorted(states & MIDWEST_STATES))))
    elif not states and not str(job.get("remote_status") or "") == "remote":
        missing.append({"field": "location", "reason": "No state/remote location signal."})
    elif states and not (states & MIDWEST_STATES):
        negatives.append(_factor("outside Midwest", -3, ", ".join(sorted(states))))


def _score_work_style(
    job: Mapping[str, Any],
    positives: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    remote = str(job.get("remote_status") or "").lower()
    telework = str(job.get("telework_status") or "").lower()
    if remote == "remote":
        positives.append(_factor("remote", 8, "remote"))
    elif remote == "hybrid" or "telework" in telework or telework in {"yes", "y", "true"}:
        positives.append(_factor("telework/hybrid", 4, telework or remote))
    elif remote == "unknown":
        missing.append({"field": "remote_status", "reason": "Remote/telework status is unknown."})


def _score_supervisory(job: Mapping[str, Any], text: str, positives: list[dict[str, Any]]) -> None:
    supervisory = str(job.get("supervisory_status") or "").lower()
    if supervisory in {"yes", "true", "y"} or re.search(r"\bsupervis(or|ory|e|ing)\b", text, flags=re.I):
        positives.append(_factor("supervisory", 5, job.get("supervisory_status") or "supervisory text"))


def _series_values(job: Mapping[str, Any]) -> set[str]:
    values = set()
    for raw in (job.get("series"), *(job.get("series_values") or [])):
        if raw:
            digits = re.sub(r"\D", "", str(raw))
            values.add(digits.zfill(4) if digits else str(raw))
    return values


def _grade_values(job: Mapping[str, Any]) -> set[int]:
    values: set[int] = set()
    for raw in (job.get("grade_low"), job.get("grade_high")):
        grade = _grade_int(raw)
        if grade is not None:
            values.add(grade)
    for grade_row in job.get("grades") or []:
        for key in ("grade_low", "grade_high", "promotion_potential"):
            grade = _grade_int(grade_row.get(key))
            if grade is not None:
                values.add(grade)
    return values


def _state_values(job: Mapping[str, Any]) -> set[str]:
    values = {str(job.get("state") or "").upper()} if job.get("state") else set()
    for location in job.get("locations") or []:
        state = str(location.get("state") or "").upper()
        if len(state) == 2:
            values.add(state)
    return values


def _combined_text(job: Mapping[str, Any]) -> str:
    pieces = [
        _combined_text_fields(job, ("title", "agency", "department", "sub_agency")),
        _combined_text_fields(
            job,
            (
                "summary",
                "duties",
                "qualifications",
                "specialized_experience",
                "conditions_of_employment",
                "evaluation_criteria",
            ),
        ),
        " ".join(str(item) for item in job.get("requirements") or []),
        " ".join(str(item) for item in job.get("qualification_requirements") or []),
        " ".join(str(item) for item in job.get("duty_rows") or []),
        " ".join(str(item) for item in job.get("evaluation_factors") or []),
    ]
    return " ".join(piece for piece in pieces if piece).lower()


def _long_text(job: Mapping[str, Any]) -> str:
    pieces = [
        _combined_text_fields(
            job,
            (
                "summary",
                "duties",
                "qualifications",
                "specialized_experience",
                "conditions_of_employment",
                "evaluation_criteria",
            ),
        ),
        " ".join(str(item) for item in job.get("requirements") or []),
        " ".join(str(item) for item in job.get("qualification_requirements") or []),
        " ".join(str(item) for item in job.get("duty_rows") or []),
        " ".join(str(item) for item in job.get("evaluation_factors") or []),
    ]
    return " ".join(piece for piece in pieces if piece).lower()


def _combined_text_fields(job: Mapping[str, Any], fields: tuple[str, ...]) -> str:
    return " ".join(str(job.get(field) or "") for field in fields).lower()


def _factor(factor: str, weight: int, evidence: Any) -> dict[str, Any]:
    return {"factor": factor, "weight": weight, "evidence": str(evidence)[:240]}


def _grade_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d{1,2}", str(value))
    return int(match.group(0)) if match else None


def _text_list(conn: sqlite3.Connection, sql: str, job_id: int) -> list[str]:
    rows = conn.execute(sql, (job_id,)).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def _evidence(text: str, needle: str) -> str | None:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return None
    return _window(text, idx, idx + len(needle))


def _window(text: str, start: int, end: int) -> str:
    left = max(0, start - 80)
    right = min(len(text), end + 80)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _explanation(
    score: int,
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> str:
    top = sorted(positives, key=lambda item: int(item["weight"]), reverse=True)[:4]
    top_text = ", ".join(f"{item['factor']} (+{item['weight']})" for item in top) or "no strong positive signals"
    negative_text = ""
    if negatives:
        worst = sorted(negatives, key=lambda item: int(item["weight"]))[:2]
        negative_text = "; watch-outs: " + ", ".join(
            f"{item['factor']} ({item['weight']})" for item in worst
        )
    missing_text = ""
    if missing:
        missing_text = f"; missing {len(missing)} useful field(s)"
    return f"Score {score}/100 from {top_text}{negative_text}{missing_text}."
