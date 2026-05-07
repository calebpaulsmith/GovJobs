"""Local alert generation for saved searches and priority job signals."""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from src.database import init_schema, utc_now
from src.scoring import SCORING_VERSION


@dataclass(frozen=True)
class AlertCandidate:
    job_id: int | None
    alert_type: str
    severity: str
    title: str
    message: str
    details: dict[str, Any]
    dedupe_key: str
    source_search_id: int | None = None


def generate_alerts(
    conn: sqlite3.Connection,
    *,
    today: date | None = None,
    high_score_threshold: int = 75,
    closing_soon_days: int = 7,
) -> int:
    """Generate deduped local alerts and return the number of new rows created."""
    init_schema(conn)
    run_started = utc_now()
    run_id = _start_run(conn, run_started)
    today = today or datetime.now(timezone.utc).date()

    candidates: list[AlertCandidate] = []
    candidates.extend(_high_score_alerts(conn, high_score_threshold))
    candidates.extend(_closing_soon_alerts(conn, today=today, days=closing_soon_days))
    candidates.extend(_saved_search_alerts(conn))
    candidates.extend(_reposted_alerts(conn))

    created = 0
    for candidate in candidates:
        created += _record_alert(conn, candidate)

    conn.execute(
        "UPDATE alert_runs SET completed_at=?, alerts_created=?, notes=? WHERE id=?",
        (utc_now(), created, f"Generated {len(candidates)} candidates.", run_id),
    )
    conn.commit()
    return created


def dismiss_alert(conn: sqlite3.Connection, alert_id: int) -> None:
    conn.execute(
        "UPDATE alerts SET status='dismissed', dismissed_at=? WHERE id=?",
        (utc_now(), alert_id),
    )
    conn.commit()


def _start_run(conn: sqlite3.Connection, started_at: str) -> int:
    cur = conn.execute(
        "INSERT INTO alert_runs (started_at, notes) VALUES (?, ?)",
        (started_at, "running"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _record_alert(conn: sqlite3.Connection, candidate: AlertCandidate) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO alerts (
            job_id, alert_type, severity, title, message, details_json,
            source_search_id, dedupe_key, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
        """,
        (
            candidate.job_id,
            candidate.alert_type,
            candidate.severity,
            candidate.title,
            candidate.message,
            json.dumps(candidate.details, sort_keys=True),
            candidate.source_search_id,
            candidate.dedupe_key,
            utc_now(),
        ),
    )
    return int(cur.rowcount or 0)


def _high_score_alerts(conn: sqlite3.Connection, threshold: int) -> list[AlertCandidate]:
    rows = conn.execute(
        """
        SELECT j.id, j.title AS job_title, j.agency, j.series, j.grade_high, ms.score
        FROM jobs j
        JOIN (
            SELECT job_id, MAX(id) AS latest_score_id
            FROM match_scores
            GROUP BY job_id
        ) latest ON latest.job_id = j.id
        JOIN match_scores ms ON ms.id = latest.latest_score_id
        WHERE ms.score >= ?
        ORDER BY ms.score DESC
        """,
        (threshold,),
    ).fetchall()

    alerts: list[AlertCandidate] = []
    for row in rows:
        score = int(row["score"])
        alerts.append(
            AlertCandidate(
                job_id=int(row["id"]),
                alert_type="high_score",
                severity="high" if score >= 85 else "medium",
                title="High match score",
                message=f"{row['job_title'] or 'Untitled'} scored {score}.",
                details={
                    "score": score,
                    "threshold": threshold,
                    "agency": row["agency"],
                    "series": row["series"],
                    "grade_high": row["grade_high"],
                    "scoring_version": SCORING_VERSION,
                },
                dedupe_key=f"job:{row['id']}:score:{SCORING_VERSION}",
            )
        )
    return alerts


def _closing_soon_alerts(conn: sqlite3.Connection, *, today: date, days: int) -> list[AlertCandidate]:
    rows = conn.execute(
        """
        SELECT id, title AS job_title, agency, close_date, url
        FROM jobs
        WHERE close_date IS NOT NULL AND close_date != ''
        """
    ).fetchall()

    alerts: list[AlertCandidate] = []
    for row in rows:
        close_date = _parse_date(row["close_date"])
        if close_date is None:
            continue
        days_until_close = (close_date - today).days
        if days_until_close < 0 or days_until_close > days:
            continue
        severity = "high" if days_until_close <= 2 else "medium"
        alerts.append(
            AlertCandidate(
                job_id=int(row["id"]),
                alert_type="closing_soon",
                severity=severity,
                title="Closing soon",
                message=f"{row['job_title'] or 'Untitled'} closes in {days_until_close} day(s).",
                details={
                    "close_date": close_date.isoformat(),
                    "days_until_close": days_until_close,
                    "agency": row["agency"],
                    "url": row["url"],
                },
                dedupe_key=f"job:{row['id']}:close:{close_date.isoformat()}",
            )
        )
    return alerts


def _saved_search_alerts(conn: sqlite3.Connection) -> list[AlertCandidate]:
    searches = conn.execute(
        """
        SELECT id, name, query_params_json
        FROM saved_searches
        WHERE alert_enabled = 1
        ORDER BY id
        """
    ).fetchall()
    if not searches:
        return []

    job_rows = _job_match_rows(conn)
    alerts: list[AlertCandidate] = []
    for search in searches:
        params = _safe_json(search["query_params_json"])
        for job in job_rows:
            matched = _matched_saved_search_fields(job, params)
            if not matched:
                continue
            score = _int_or_none(job.get("score"))
            alerts.append(
                AlertCandidate(
                    job_id=int(job["id"]),
                    alert_type="saved_search_match",
                    severity="medium" if score is not None and score >= 75 else "low",
                    title="Saved search match",
                    message=f"{job['title'] or 'Untitled'} matches {search['name']}.",
                    details={
                        "saved_search_id": int(search["id"]),
                        "saved_search_name": search["name"],
                        "matched_fields": matched,
                        "score": score,
                        "query_params": params,
                    },
                    dedupe_key=f"search:{search['id']}:job:{job['id']}",
                    source_search_id=int(search["id"]),
                )
            )
    return alerts


def _reposted_alerts(conn: sqlite3.Connection) -> list[AlertCandidate]:
    detected = _detected_repost_alerts(conn)
    if detected:
        return detected
    groups = conn.execute(
        """
        SELECT lower(trim(title)) AS title_key,
               COALESCE(NULLIF(agency_code, ''), NULLIF(agency, ''), 'unknown') AS agency_key,
               COALESCE(NULLIF(series, ''), 'unknown') AS series_key,
               COUNT(*) AS postings,
               COUNT(DISTINCT COALESCE(usajobs_control_number, announcement_number, position_id, id)) AS controls
        FROM jobs
        WHERE title IS NOT NULL AND trim(title) != ''
        GROUP BY title_key, agency_key, series_key
        HAVING postings > 1 AND controls > 1
        """
    ).fetchall()

    alerts: list[AlertCandidate] = []
    for group in groups:
        row = conn.execute(
            """
            SELECT id, title AS job_title, agency, agency_code, series, announcement_number,
                   usajobs_control_number, updated_at
            FROM jobs
            WHERE lower(trim(title)) = ?
              AND COALESCE(NULLIF(agency_code, ''), NULLIF(agency, ''), 'unknown') = ?
              AND COALESCE(NULLIF(series, ''), 'unknown') = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (group["title_key"], group["agency_key"], group["series_key"]),
        ).fetchone()
        if row is None:
            continue
        alerts.append(
            AlertCandidate(
                job_id=int(row["id"]),
                alert_type="reposted",
                severity="low",
                title="Possible repost",
                message=f"{row['job_title'] or 'Untitled'} appears in multiple announcements.",
                details={
                    "postings": int(group["postings"]),
                    "distinct_controls": int(group["controls"]),
                    "agency": row["agency"],
                    "agency_code": row["agency_code"],
                    "series": row["series"],
                    "announcement_number": row["announcement_number"],
                    "usajobs_control_number": row["usajobs_control_number"],
                },
                dedupe_key=f"group:{group['title_key']}:{group['agency_key']}:{group['series_key']}:job:{row['id']}",
            )
        )
    return alerts


def _detected_repost_alerts(conn: sqlite3.Connection) -> list[AlertCandidate]:
    latest_run = conn.execute("SELECT MAX(id) AS id FROM repost_runs WHERE completed_at IS NOT NULL").fetchone()
    if latest_run is None or latest_run["id"] is None:
        return []
    rows = conn.execute(
        """
        SELECT rg.id AS group_id, rg.group_signature, rg.group_title, rg.agency_key,
               rg.series_key, rg.member_count, rg.confidence_score, rg.evidence_json,
               newest.job_id
        FROM repost_groups rg
        JOIN (
            SELECT rgm.group_id, rgm.job_id
            FROM repost_group_members rgm
            JOIN jobs j ON j.id = rgm.job_id
            JOIN (
                SELECT rgm2.group_id, MAX(COALESCE(j2.open_date, j2.updated_at, j2.imported_at)) AS newest_date
                FROM repost_group_members rgm2
                JOIN jobs j2 ON j2.id = rgm2.job_id
                GROUP BY rgm2.group_id
            ) ranked ON ranked.group_id = rgm.group_id
                    AND ranked.newest_date = COALESCE(j.open_date, j.updated_at, j.imported_at)
            GROUP BY rgm.group_id
        ) newest ON newest.group_id = rg.id
        WHERE rg.run_id = ?
        ORDER BY rg.confidence_score DESC, rg.member_count DESC
        """,
        (int(latest_run["id"]),),
    ).fetchall()
    alerts: list[AlertCandidate] = []
    for row in rows:
        evidence = _safe_json(row["evidence_json"])
        alerts.append(
            AlertCandidate(
                job_id=int(row["job_id"]),
                alert_type="reposted",
                severity="medium" if float(row["confidence_score"]) >= 0.94 else "low",
                title="Possible repost group",
                message=(
                    f"{row['group_title'] or 'Untitled'} appears in "
                    f"{int(row['member_count'])} similar announcements."
                ),
                details={
                    **evidence,
                    "repost_group_id": int(row["group_id"]),
                    "group_signature": row["group_signature"],
                    "member_count": int(row["member_count"]),
                    "confidence_score": float(row["confidence_score"]),
                    "agency_key": row["agency_key"],
                    "series_key": row["series_key"],
                },
                dedupe_key=f"group:{row['group_signature']}",
            )
        )
    return alerts


def _job_match_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT j.*, jt.summary, jt.duties, jt.qualifications, jt.raw_text,
               latest_score.score,
               COALESCE(series_rows.series_values, '') AS series_values,
               COALESCE(location_rows.location_values, '') AS location_values,
               COALESCE(hiring_path_rows.hiring_path_values, '') AS hiring_path_values,
               COALESCE(requirement_rows.requirement_values, '') AS requirement_values
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
            SELECT job_id, group_concat(COALESCE(location_text, '') || ' ' || COALESCE(city, '') || ' ' || COALESCE(state, ''), ' ') AS location_values
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
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _matched_saved_search_fields(job: Mapping[str, Any], params: Mapping[str, Any]) -> list[str]:
    checks = [
        ("Organization", lambda value: _matches_any(value, job.get("agency_code"), job.get("agency"))),
        ("HiringAgencyCodes", lambda value: _matches_any(value, job.get("agency_code"), job.get("agency"))),
        ("HiringDepartmentCodes", lambda value: _matches_any(value, job.get("department_code"), job.get("department"))),
        ("Department", lambda value: _matches_any(value, job.get("department_code"), job.get("department"))),
        ("JobCategoryCode", lambda value: _matches_series(value, job)),
        ("PositionSeries", lambda value: _matches_series(value, job)),
        ("PayPlan", lambda value: _matches_any(value, job.get("pay_plan"))),
        ("RemoteIndicator", lambda value: _matches_remote(value, job)),
        ("LocationName", lambda value: _matches_location(value, job)),
        ("Keyword", lambda value: _matches_keyword(value, job)),
        ("HiringPath", lambda value: _matches_text(value, job.get("hiring_path_values"))),
    ]
    matched: list[str] = []
    required_keys = [key for key in params if params.get(key) not in (None, "", [])]
    if not required_keys:
        return matched

    for key, checker in checks:
        if key not in params or params.get(key) in (None, "", []):
            continue
        if checker(params[key]):
            matched.append(key)
        else:
            return []

    if not _matches_grade_bounds(job, params):
        return []
    if not _matches_date_bounds(job, params):
        return []
    return matched or required_keys


def _matches_series(value: Any, job: Mapping[str, Any]) -> bool:
    series_values = " ".join(str(item or "") for item in (job.get("series"), job.get("series_values")))
    return any(_series_text(item) in series_values for item in _value_list(value) if _series_text(item))


def _matches_any(value: Any, *fields: Any) -> bool:
    field_values = {str(field or "").strip().upper() for field in fields if str(field or "").strip()}
    return any(str(item).strip().upper() in field_values for item in _value_list(value))


def _matches_remote(value: Any, job: Mapping[str, Any]) -> bool:
    values = {str(item).strip().lower() for item in _value_list(value)}
    remote_status = str(job.get("remote_status") or "").strip().lower()
    if not values:
        return True
    if values & {"true", "yes", "1", "remote"}:
        return remote_status == "remote"
    if values & {"false", "no", "0", "onsite"}:
        return remote_status != "remote"
    return remote_status in values


def _matches_location(value: Any, job: Mapping[str, Any]) -> bool:
    haystack = _combined_text(
        job,
        (
            "location_text",
            "city",
            "state",
            "location_values",
        ),
    )
    return _matches_text(value, haystack)


def _matches_keyword(value: Any, job: Mapping[str, Any]) -> bool:
    haystack = _combined_text(
        job,
        (
            "title",
            "agency",
            "department",
            "sub_agency",
            "summary",
            "duties",
            "qualifications",
            "raw_text",
            "requirement_values",
        ),
    )
    return _matches_text(value, haystack)


def _matches_text(value: Any, text: Any) -> bool:
    haystack = str(text or "").lower()
    return any(str(item).strip().lower() in haystack for item in _value_list(value) if str(item).strip())


def _matches_grade_bounds(job: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    lower = _int_or_none(params.get("PayGradeLow") or params.get("GradeLow"))
    upper = _int_or_none(params.get("PayGradeHigh") or params.get("GradeHigh"))
    if lower is None and upper is None:
        return True
    grade_low = _int_or_none(job.get("grade_low"))
    grade_high = _int_or_none(job.get("grade_high"))
    if grade_low is None and grade_high is None:
        return False
    job_low = grade_low if grade_low is not None else grade_high
    job_high = grade_high if grade_high is not None else grade_low
    if lower is not None and job_high is not None and job_high < lower:
        return False
    if upper is not None and job_low is not None and job_low > upper:
        return False
    return True


def _matches_date_bounds(job: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    comparisons = (
        ("StartPositionOpenDate", "open_date", "start"),
        ("EndPositionOpenDate", "open_date", "end"),
        ("StartPositionCloseDate", "close_date", "start"),
        ("EndPositionCloseDate", "close_date", "end"),
    )
    for param_key, job_key, direction in comparisons:
        if not params.get(param_key):
            continue
        param_date = _parse_date(params.get(param_key))
        job_date = _parse_date(job.get(job_key))
        if param_date is None or job_date is None:
            return False
        if direction == "start" and job_date < param_date:
            return False
        if direction == "end" and job_date > param_date:
            return False
    return True


def _combined_text(job: Mapping[str, Any], fields: tuple[str, ...]) -> str:
    return " ".join(str(job.get(field) or "") for field in fields).lower()


def _value_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,;|]", str(value)) if item.strip()]


def _series_text(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    return text.zfill(4) if text else ""


def _safe_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
