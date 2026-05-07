"""Deterministic repost detection for USAJOBS announcements."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from src.database import init_schema, utc_now


@dataclass(frozen=True)
class RepostDetectionResult:
    run_id: int
    groups_created: int
    members_created: int


@dataclass(frozen=True)
class _JobFingerprint:
    job_id: int
    title: str
    normalized_title: str
    agency_key: str
    series_key: str
    control: str
    open_date: str | None
    close_date: str | None
    text_hash: str | None


def detect_reposts(
    conn: sqlite3.Connection,
    *,
    title_threshold: float = 0.88,
    text_assist_threshold: float = 0.74,
) -> RepostDetectionResult:
    """Detect likely repost groups and persist an auditable run."""
    init_schema(conn)
    started_at = utc_now()
    params = {
        "title_threshold": title_threshold,
        "text_assist_threshold": text_assist_threshold,
        "algorithm": "agency_series_title_text_hash_v1",
    }
    run_id = _start_run(conn, started_at, params)
    fingerprints = _job_fingerprints(conn)
    components = _candidate_components(
        fingerprints,
        title_threshold=title_threshold,
        text_assist_threshold=text_assist_threshold,
    )

    groups_created = 0
    members_created = 0
    for members in components:
        if len(members) < 2:
            continue
        group_id = _insert_group(conn, run_id, members)
        groups_created += 1
        members_created += _insert_members(conn, group_id, members)

    conn.execute(
        """
        UPDATE repost_runs
        SET completed_at=?, groups_created=?, members_created=?, notes=?
        WHERE id=?
        """,
        (
            utc_now(),
            groups_created,
            members_created,
            f"Detected {groups_created} group(s) across {members_created} member row(s).",
            run_id,
        ),
    )
    conn.commit()
    return RepostDetectionResult(run_id, groups_created, members_created)


def _start_run(conn: sqlite3.Connection, started_at: str, params: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO repost_runs (started_at, params_json, notes)
        VALUES (?, ?, ?)
        """,
        (started_at, json.dumps(params, sort_keys=True), "running"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _job_fingerprints(conn: sqlite3.Connection) -> list[_JobFingerprint]:
    rows = conn.execute(
        """
        SELECT j.id, j.title, j.agency, j.agency_code, j.series,
               j.usajobs_control_number, j.announcement_number, j.position_id,
               j.open_date, j.close_date,
               jt.summary, jt.duties, jt.qualifications, jt.specialized_experience,
               jt.raw_text
        FROM jobs j
        LEFT JOIN job_text jt ON jt.job_id = j.id
        WHERE j.title IS NOT NULL AND trim(j.title) != ''
        ORDER BY j.id
        """
    ).fetchall()
    fingerprints: list[_JobFingerprint] = []
    for row in rows:
        normalized_title = _normalize_title(row["title"])
        if not normalized_title:
            continue
        text = " ".join(
            str(row[key] or "")
            for key in ("summary", "duties", "qualifications", "specialized_experience", "raw_text")
        )
        fingerprints.append(
            _JobFingerprint(
                job_id=int(row["id"]),
                title=row["title"],
                normalized_title=normalized_title,
                agency_key=_agency_key(row["agency_code"], row["agency"]),
                series_key=_series_key(row["series"]),
                control=_control_key(row),
                open_date=row["open_date"],
                close_date=row["close_date"],
                text_hash=_text_hash(text),
            )
        )
    return fingerprints


def _candidate_components(
    fingerprints: list[_JobFingerprint],
    *,
    title_threshold: float,
    text_assist_threshold: float,
) -> list[list[_JobFingerprint]]:
    by_block: dict[tuple[str, str], list[_JobFingerprint]] = defaultdict(list)
    for item in fingerprints:
        by_block[(item.agency_key, item.series_key)].append(item)

    components: list[list[_JobFingerprint]] = []
    for block_items in by_block.values():
        parent = {item.job_id: item.job_id for item in block_items}
        by_id = {item.job_id: item for item in block_items}
        for idx, left in enumerate(block_items):
            for right in block_items[idx + 1 :]:
                if left.control and left.control == right.control:
                    continue
                score = _title_similarity(left.normalized_title, right.normalized_title)
                text_match = bool(left.text_hash and left.text_hash == right.text_hash)
                if score >= title_threshold or (text_match and score >= text_assist_threshold):
                    _union(parent, left.job_id, right.job_id)
        grouped: dict[int, list[_JobFingerprint]] = defaultdict(list)
        for item in block_items:
            grouped[_find(parent, item.job_id)].append(by_id[item.job_id])
        components.extend(group for group in grouped.values() if len(group) > 1)
    return components


def _insert_group(conn: sqlite3.Connection, run_id: int, members: list[_JobFingerprint]) -> int:
    sorted_members = sorted(members, key=lambda item: (item.open_date or "", item.job_id))
    title = _representative_title(sorted_members)
    agency_key = sorted_members[0].agency_key
    series_key = sorted_members[0].series_key
    similarities = [
        _title_similarity(left.normalized_title, right.normalized_title)
        for idx, left in enumerate(sorted_members)
        for right in sorted_members[idx + 1 :]
    ]
    confidence = round(sum(similarities) / len(similarities), 3) if similarities else 1.0
    signature = _group_signature(agency_key, series_key, sorted_members)
    evidence = {
        "algorithm": "agency_series_title_text_hash_v1",
        "member_job_ids": [item.job_id for item in sorted_members],
        "controls": [item.control for item in sorted_members],
        "titles": list(dict.fromkeys(item.title for item in sorted_members)),
        "text_hashes": list(dict.fromkeys(item.text_hash for item in sorted_members if item.text_hash)),
        "open_dates": [item.open_date for item in sorted_members],
        "close_dates": [item.close_date for item in sorted_members],
        "average_title_similarity": confidence,
    }
    cur = conn.execute(
        """
        INSERT INTO repost_groups (
            run_id, group_signature, group_title, agency_key, series_key,
            member_count, confidence_score, evidence_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            signature,
            title,
            agency_key,
            series_key,
            len(sorted_members),
            confidence,
            json.dumps(evidence, sort_keys=True),
            utc_now(),
        ),
    )
    return int(cur.lastrowid)


def _insert_members(conn: sqlite3.Connection, group_id: int, members: list[_JobFingerprint]) -> int:
    sorted_members = sorted(members, key=lambda item: (item.open_date or "", item.job_id))
    baseline = sorted_members[0]
    rows = []
    for idx, member in enumerate(sorted_members):
        rows.append(
            (
                group_id,
                member.job_id,
                "original" if idx == 0 else "possible_repost",
                _title_similarity(baseline.normalized_title, member.normalized_title),
                member.text_hash,
                utc_now(),
            )
        )
    conn.executemany(
        """
        INSERT INTO repost_group_members (
            group_id, job_id, role, title_similarity, text_hash, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def _normalize_title(value: Any) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", str(value or "").lower())
    stopwords = {"the", "a", "an"}
    tokens = [token for token in text.split() if token not in stopwords]
    return " ".join(tokens)


def _title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens | right_tokens else 0.0
    return round((sequence * 0.65) + (jaccard * 0.35), 3)


def _text_hash(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    if len(normalized) < 80:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _agency_key(agency_code: Any, agency: Any) -> str:
    return str(agency_code or agency or "unknown").strip().upper() or "unknown"


def _series_key(series: Any) -> str:
    digits = re.sub(r"\D", "", str(series or ""))
    return digits.zfill(4) if digits else "unknown"


def _control_key(row: sqlite3.Row) -> str:
    return str(row["usajobs_control_number"] or row["announcement_number"] or row["position_id"] or row["id"])


def _representative_title(members: list[_JobFingerprint]) -> str:
    titles = [item.title for item in members if item.title]
    return max(titles, key=len) if titles else "Possible repost group"


def _group_signature(agency_key: str, series_key: str, members: list[_JobFingerprint]) -> str:
    normalized_titles = sorted(set(item.normalized_title for item in members))
    seed = "|".join([agency_key, series_key, *normalized_titles])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _find(parent: dict[int, int], item: int) -> int:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item


def _union(parent: dict[int, int], left: int, right: int) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[right_root] = left_root
