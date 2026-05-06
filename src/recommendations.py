"""Explainable local job recommendations for Phase 6.5."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.database import (
    create_recommendation_run,
    init_schema,
    record_job_recommendation,
)


RECOMMENDATION_VERSION = "v1.0"
POSITIVE_FEEDBACK = {"liked", "more_like_this"}
NEGATIVE_FEEDBACK = {"disliked", "less_like_this"}
TOPIC_PATTERNS = {
    "emergency management": r"emergency management",
    "mitigation": r"\bmitigation\b|hazard mitigation",
    "public assistance": r"public assistance",
    "grants": r"\bgrants?\b|grants management",
    "disaster recovery": r"disaster recovery|\brecovery\b",
    "policy analysis": r"policy analysis|\bpolicy\b",
    "program analysis": r"program analysis|management and program",
    "infrastructure": r"\binfrastructure\b",
    "resilience": r"\bresilien(ce|t)\b",
    "supervisory": r"\bsupervis(or|ory|e|ing)\b",
}


@dataclass(frozen=True)
class RecommendationResult:
    run_id: int
    recommendations_created: int


def generate_similar_jobs(
    conn: sqlite3.Connection,
    *,
    seed_job_id: int | None = None,
    limit: int = 25,
    include_dismissed: bool = False,
) -> RecommendationResult:
    """Generate deterministic recommendations and persist the run."""
    init_schema(conn)
    contexts = _job_contexts(conn)
    context_by_id = {int(job["id"]): job for job in contexts}
    seed = context_by_id.get(seed_job_id) if seed_job_id is not None else None
    if seed_job_id is not None and seed is None:
        raise ValueError(f"job_id does not exist: {seed_job_id}")

    dismissed_job_ids = set() if include_dismissed else _dismissed_job_ids(conn)
    feedback_profiles = _feedback_profiles(conn, context_by_id)
    run_id = create_recommendation_run(
        conn,
        run_type="similar_jobs",
        seed_job_id=seed_job_id,
        params={
            "version": RECOMMENDATION_VERSION,
            "limit": limit,
            "include_dismissed": include_dismissed,
        },
    )

    scored: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for candidate in contexts:
        candidate_id = int(candidate["id"])
        if candidate_id == seed_job_id or candidate_id in dismissed_job_ids:
            continue
        factors: list[dict[str, Any]] = []
        if seed is not None:
            factors.extend(_seed_similarity_factors(seed, candidate))
        factors.extend(_feedback_factors(candidate, feedback_profiles))
        score = sum(int(factor["weight"]) for factor in factors)
        if score <= 0:
            continue
        scored.append((min(score, 100), candidate, factors))

    scored.sort(key=lambda item: (item[0], _int_or_none(item[1].get("match_score")) or 0), reverse=True)
    created = 0
    for score, candidate, factors in scored[:limit]:
        record_job_recommendation(
            conn,
            run_id=run_id,
            job_id=int(candidate["id"]),
            score=score,
            explanation=_explanation(score, factors),
            factors=factors,
        )
        created += 1

    return RecommendationResult(run_id=run_id, recommendations_created=created)


def _job_contexts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT j.id, j.title, j.agency, j.department, j.agency_code, j.department_code,
               j.series, j.grade_low, j.grade_high, j.pay_plan, j.state, j.city,
               j.remote_status, j.hiring_paths, j.travel_required, j.security_clearance,
               j.location_text, j.supervisory_status, jt.summary, jt.duties,
               jt.qualifications, jt.specialized_experience, jt.conditions_of_employment,
               latest_score.score AS match_score,
               COALESCE(series_rows.series_values, '') AS series_values,
               COALESCE(grade_rows.grade_values, '') AS grade_values,
               COALESCE(location_rows.state_values, '') AS state_values,
               COALESCE(location_rows.location_values, '') AS location_values,
               COALESCE(hiring_path_rows.hiring_path_values, '') AS hiring_path_values,
               COALESCE(requirement_rows.requirement_values, '') AS requirement_values,
               COALESCE(duty_rows.duty_values, '') AS duty_values,
               COALESCE(qualification_rows.qualification_values, '') AS qualification_values,
               COALESCE(tag_rows.tag_values, '') AS tag_values
        FROM jobs j
        LEFT JOIN job_text jt ON jt.job_id = j.id
        LEFT JOIN (
            SELECT ms.job_id, ms.score
            FROM match_scores ms
            JOIN (
                SELECT job_id, MAX(id) AS latest_score_id
                FROM match_scores
                GROUP BY job_id
            ) latest ON latest.latest_score_id = ms.id
        ) latest_score ON latest_score.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(series, ' ') AS series_values
            FROM job_categories
            GROUP BY job_id
        ) series_rows ON series_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(
                COALESCE(pay_plan, '') || '-' || COALESCE(grade_low, '') || '-' || COALESCE(grade_high, ''),
                ' '
            ) AS grade_values
            FROM job_grades
            GROUP BY job_id
        ) grade_rows ON grade_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id,
                   group_concat(COALESCE(state, ''), ' ') AS state_values,
                   group_concat(COALESCE(location_text, '') || ' ' || COALESCE(city, '') || ' ' || COALESCE(state, ''), ' ') AS location_values
            FROM job_locations
            GROUP BY job_id
        ) location_rows ON location_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(COALESCE(code, '') || ' ' || COALESCE(label, ''), ' ') AS hiring_path_values
            FROM job_hiring_paths
            GROUP BY job_id
        ) hiring_path_rows ON hiring_path_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(COALESCE(description, ''), ' ') AS requirement_values
            FROM job_requirements
            GROUP BY job_id
        ) requirement_rows ON requirement_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(COALESCE(duty_text, ''), ' ') AS duty_values
            FROM job_duties
            GROUP BY job_id
        ) duty_rows ON duty_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(COALESCE(text, ''), ' ') AS qualification_values
            FROM job_qualification_requirements
            GROUP BY job_id
        ) qualification_rows ON qualification_rows.job_id = j.id
        LEFT JOIN (
            SELECT job_id, group_concat(tag, ' ') AS tag_values
            FROM job_tags
            GROUP BY job_id
        ) tag_rows ON tag_rows.job_id = j.id
        """
    ).fetchall()
    return [_normalize_context(dict(row)) for row in rows]


def _normalize_context(job: dict[str, Any]) -> dict[str, Any]:
    job["series_set"] = _series_set(job.get("series"), job.get("series_values"))
    job["grade_set"] = _grade_set(job.get("grade_low"), job.get("grade_high"), job.get("grade_values"))
    job["state_set"] = _state_set(job.get("state"), job.get("state_values"))
    job["hiring_path_set"] = _token_set(job.get("hiring_paths"), job.get("hiring_path_values"))
    job["tag_set"] = _token_set(job.get("tag_values"))
    job["topic_set"] = _topic_set(_recommendation_text(job))
    return job


def _seed_similarity_factors(seed: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    _same_value_factor(factors, "same agency code", 20, seed, candidate, "agency_code")
    _same_value_factor(factors, "same department code", 8, seed, candidate, "department_code")
    _shared_set_factor(factors, "shared series", 18, seed["series_set"], candidate["series_set"])
    _grade_factor(factors, seed["grade_set"], candidate["grade_set"])
    _same_value_factor(factors, "same remote status", 8, seed, candidate, "remote_status")
    _shared_set_factor(factors, "shared state", 8, seed["state_set"], candidate["state_set"])
    _shared_set_factor(factors, "shared hiring path", 5, seed["hiring_path_set"], candidate["hiring_path_set"])
    _shared_set_factor(factors, "shared user tag", 10, seed["tag_set"], candidate["tag_set"])
    _shared_set_factor(factors, "shared text theme", 4, seed["topic_set"], candidate["topic_set"], max_hits=4)
    _score_band_factor(factors, seed, candidate)
    return factors


def _feedback_profiles(
    conn: sqlite3.Connection,
    context_by_id: Mapping[int, Mapping[str, Any]],
) -> dict[str, Counter[str]]:
    profiles = {
        "positive": Counter(),
        "negative": Counter(),
    }
    rows = conn.execute(
        """
        SELECT job_id, feedback_type, explanation
        FROM job_feedback
        ORDER BY id
        """
    ).fetchall()
    for row in rows:
        job = context_by_id.get(int(row["job_id"]))
        if not job:
            continue
        bucket = "positive" if row["feedback_type"] in POSITIVE_FEEDBACK else "negative"
        for pattern in _profile_patterns(job):
            profiles[bucket][pattern] += 1
        for topic in _topic_set(row["explanation"] or ""):
            profiles[bucket][f"topic:{topic}"] += 1
    return profiles


def _feedback_factors(
    candidate: Mapping[str, Any],
    profiles: Mapping[str, Counter[str]],
) -> list[dict[str, Any]]:
    candidate_patterns = set(_profile_patterns(candidate))
    factors: list[dict[str, Any]] = []
    for pattern in sorted(candidate_patterns & set(profiles["positive"])):
        weight = min(10, 3 + profiles["positive"][pattern])
        factors.append(_factor("matches positive feedback", weight, _display_pattern(pattern)))
    for pattern in sorted(candidate_patterns & set(profiles["negative"])):
        weight = -min(18, 6 + profiles["negative"][pattern] * 3)
        factors.append(_factor("matches negative feedback", weight, _display_pattern(pattern)))
    return factors


def _profile_patterns(job: Mapping[str, Any]) -> list[str]:
    patterns: list[str] = []
    for key in ("agency_code", "department_code", "remote_status", "travel_required", "security_clearance"):
        value = _clean(job.get(key))
        if value:
            patterns.append(f"{key}:{value.lower()}")
    for series in job["series_set"]:
        patterns.append(f"series:{series}")
    for state in job["state_set"]:
        patterns.append(f"state:{state}")
    for grade in job["grade_set"]:
        patterns.append(f"grade:{grade}")
    for tag in job["tag_set"]:
        patterns.append(f"tag:{tag}")
    for topic in job["topic_set"]:
        patterns.append(f"topic:{topic}")
    return patterns


def _dismissed_job_ids(conn: sqlite3.Connection) -> set[int]:
    return {
        int(row["job_id"])
        for row in conn.execute(
            "SELECT DISTINCT job_id FROM job_recommendations WHERE dismissed=1"
        ).fetchall()
    }


def _same_value_factor(
    factors: list[dict[str, Any]],
    name: str,
    weight: int,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    key: str,
) -> None:
    left_value = _clean(left.get(key))
    right_value = _clean(right.get(key))
    if left_value and right_value and left_value.lower() == right_value.lower():
        factors.append(_factor(name, weight, left_value))


def _shared_set_factor(
    factors: list[dict[str, Any]],
    name: str,
    weight: int,
    left: set[str],
    right: set[str],
    *,
    max_hits: int = 1,
) -> None:
    shared = sorted(left & right)
    for value in shared[:max_hits]:
        factors.append(_factor(name, weight, value))


def _grade_factor(factors: list[dict[str, Any]], seed_grades: set[str], candidate_grades: set[str]) -> None:
    if not seed_grades or not candidate_grades:
        return
    shared = seed_grades & candidate_grades
    if shared:
        factors.append(_factor("shared grade", 12, ", ".join(sorted(shared))))
        return
    seed_ints = {_int_or_none(item) for item in seed_grades}
    candidate_ints = {_int_or_none(item) for item in candidate_grades}
    seed_ints.discard(None)
    candidate_ints.discard(None)
    if seed_ints and candidate_ints and min(abs(a - b) for a in seed_ints for b in candidate_ints) <= 1:
        factors.append(_factor("nearby grade", 6, f"{sorted(seed_grades)} vs {sorted(candidate_grades)}"))


def _score_band_factor(factors: list[dict[str, Any]], seed: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    seed_score = _int_or_none(seed.get("match_score"))
    candidate_score = _int_or_none(candidate.get("match_score"))
    if seed_score is None or candidate_score is None:
        return
    if abs(seed_score - candidate_score) <= 10:
        factors.append(_factor("similar match score", 4, f"{candidate_score}/100"))
    elif candidate_score >= 75:
        factors.append(_factor("high match score", 6, f"{candidate_score}/100"))


def _recommendation_text(job: Mapping[str, Any]) -> str:
    fields = (
        "title",
        "agency",
        "department",
        "summary",
        "duties",
        "qualifications",
        "specialized_experience",
        "conditions_of_employment",
        "requirement_values",
        "duty_values",
        "qualification_values",
    )
    return " ".join(str(job.get(field) or "") for field in fields).lower()


def _topic_set(text: str) -> set[str]:
    lowered = str(text or "").lower()
    return {
        topic
        for topic, pattern in TOPIC_PATTERNS.items()
        if re.search(pattern, lowered, flags=re.I)
    }


def _series_set(*values: Any) -> set[str]:
    series: set[str] = set()
    for value in values:
        for item in _value_list(value):
            digits = re.sub(r"\D", "", item)
            if digits:
                series.add(digits.zfill(4))
    return series


def _grade_set(*values: Any) -> set[str]:
    grades: set[str] = set()
    for value in values:
        for item in _value_list(value):
            for match in re.findall(r"\d{1,2}", item):
                grades.add(str(int(match)))
    return grades


def _state_set(*values: Any) -> set[str]:
    states: set[str] = set()
    for value in values:
        for item in _value_list(value):
            text = item.strip().upper()
            if len(text) == 2 and text.isalpha():
                states.add(text)
    return states


def _token_set(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for item in _value_list(value):
            normalized = re.sub(r"\s+", "-", item.strip().lower())
            if normalized:
                tokens.add(normalized)
    return tokens


def _value_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,;|\s]+", str(value)) if item.strip()]


def _factor(factor: str, weight: int, evidence: Any) -> dict[str, Any]:
    return {"factor": factor, "weight": weight, "evidence": str(evidence)[:240]}


def _display_pattern(pattern: str) -> str:
    name, _, value = pattern.partition(":")
    return f"{name.replace('_', ' ')} = {value}"


def _explanation(score: int, factors: list[dict[str, Any]]) -> str:
    positives = [factor for factor in factors if int(factor["weight"]) > 0]
    negatives = [factor for factor in factors if int(factor["weight"]) < 0]
    top = sorted(positives, key=lambda item: int(item["weight"]), reverse=True)[:4]
    pieces = ", ".join(f"{item['factor']} ({item['evidence']})" for item in top)
    if negatives:
        pieces += "; down-ranked by " + ", ".join(
            f"{item['factor']} ({item['evidence']})" for item in negatives[:2]
        )
    return f"Recommendation score {score}/100 from {pieces or 'stored preference signals'}."


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
