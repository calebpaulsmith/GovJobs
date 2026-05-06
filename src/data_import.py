"""Shared USAJOBS import plumbing.

Endpoint-specific modules are thin wrappers around this file. This module owns
HTTP retries, paging, raw JSON persistence, manifest updates, and DB writes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import requests

from config import Config
from src.database import (
    complete_manifest,
    create_job_import_scope,
    init_schema,
    record_raw_response,
    start_manifest,
    update_manifest,
    upsert_job,
    upsert_job_text,
)
from src.usajobs_normalize import (
    job_from_historic_record,
    job_from_search_item,
    job_text_from_announcement_text,
    job_text_from_search_descriptor,
)

logger = logging.getLogger(__name__)

USAJOBS_HOST = "https://data.usajobs.gov"
SEARCH_ENDPOINT = "/api/Search"
HISTORIC_ENDPOINT = "/api/historicjoa"
ANNOUNCEMENT_TEXT_ENDPOINT = "/api/historicjoa/announcementtext"

HISTORIC_FILTER_PARAMS = {
    "HiringAgencyCodes",
    "HiringDepartmentCodes",
    "PositionSeries",
    "AnnouncementNumbers",
    "USAJOBSControlNumbers",
    "StartPositionOpenDate",
    "EndPositionOpenDate",
    "StartPositionCloseDate",
    "EndPositionCloseDate",
    "continuationtoken",
}

HISTORIC_PARAM_ALIASES = {
    "HiringAgencyCode": "HiringAgencyCodes",
    "hiringAgencyCode": "HiringAgencyCodes",
    "hiringagencycode": "HiringAgencyCodes",
    "hiringagencycodes": "HiringAgencyCodes",
    "HiringDepartmentCode": "HiringDepartmentCodes",
    "hiringDepartmentCode": "HiringDepartmentCodes",
    "hiringdepartmentcode": "HiringDepartmentCodes",
    "hiringdepartmentcodes": "HiringDepartmentCodes",
    "positionseries": "PositionSeries",
    "announcementnumbers": "AnnouncementNumbers",
    "usajobscontrolnumbers": "USAJOBSControlNumbers",
    "StartPositionOpenDate": "StartPositionOpenDate",
    "startPositionOpenDate": "StartPositionOpenDate",
    "startpositionopendate": "StartPositionOpenDate",
    "EndPositionOpenDate": "EndPositionOpenDate",
    "endPositionOpenDate": "EndPositionOpenDate",
    "endpositionopendate": "EndPositionOpenDate",
    "StartPositionCloseDate": "StartPositionCloseDate",
    "startPositionCloseDate": "StartPositionCloseDate",
    "startpositionclosedate": "StartPositionCloseDate",
    "EndPositionCloseDate": "EndPositionCloseDate",
    "endPositionCloseDate": "EndPositionCloseDate",
    "endpositionclosedate": "EndPositionCloseDate",
    "ContinuationToken": "continuationtoken",
    "continuationToken": "continuationtoken",
}


class UsaJobsImportError(RuntimeError):
    """Base exception for USAJOBS importer failures."""


class MissingCredentialsError(UsaJobsImportError):
    """Raised when an endpoint needs USAJOBS Search credentials."""


@dataclass(frozen=True)
class PageResult:
    page_number: int
    payload: dict[str, Any]
    status_code: int
    response_path: str | None
    record_count: int


@dataclass(frozen=True)
class ImportResult:
    pages_completed: int
    records_imported: int
    manifest_id: int | None


def import_current_search(
    conn,
    config: Config,
    query_params: Mapping[str, Any] | None = None,
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> ImportResult:
    init_schema(conn)
    params = {"ResultsPerPage": 500, "Page": 1, **dict(query_params or {})}
    manifest_id = start_manifest(
        conn,
        source="usajobs_search",
        endpoint=SEARCH_ENDPOINT,
        download_mode="SAMPLE_ONLY" if dry_run else "FULL_DOWNLOAD",
        filters=params,
    )
    create_job_import_scope(
        conn,
        name="Current Search",
        source="usajobs_search",
        endpoint=SEARCH_ENDPOINT,
        query_params=params,
        download_mode="SAMPLE_ONLY" if dry_run else "FULL_DOWNLOAD",
    )
    imported = 0
    pages = 0
    try:
        for page in fetch_pages(
            config,
            endpoint=SEARCH_ENDPOINT,
            source="usajobs_search",
            params=params,
            conn=conn,
            max_pages=max_pages,
            auth_required=True,
            dry_run=dry_run,
        ):
            pages += 1
            source_query_hash = query_hash(params)
            for item in _search_items(page.payload):
                descriptor = item.get("MatchedObjectDescriptor", {})
                job_id = upsert_job(
                    conn,
                    job_from_search_item(
                        item,
                        source_query_hash=source_query_hash,
                        raw_json_path=page.response_path,
                        default_agency_code=params.get("Organization"),
                        default_department_code=params.get("Department"),
                    ),
                )
                text = job_text_from_search_descriptor(descriptor)
                text["raw_json_path"] = page.response_path
                upsert_job_text(conn, job_id, text)
                imported += 1
            update_manifest(
                conn,
                manifest_id,
                pages_completed=pages,
                actual_records=imported,
            )
    except Exception as exc:
        complete_manifest(conn, manifest_id, status="failed", actual_records=imported, notes=str(exc))
        raise
    complete_manifest(conn, manifest_id, actual_records=imported)
    return ImportResult(pages, imported, manifest_id)


def import_historic_joa(
    conn,
    config: Config,
    query_params: Mapping[str, Any] | None = None,
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
    download_mode: str = "SAMPLE_ONLY",
) -> ImportResult:
    init_schema(conn)
    params = normalize_historic_params(query_params or {})
    manifest_id = start_manifest(
        conn,
        source="usajobs_historic",
        endpoint=HISTORIC_ENDPOINT,
        download_mode=download_mode,
        filters=params,
    )
    create_job_import_scope(
        conn,
        name="HistoricJoa Filter Scope",
        source="usajobs_historic",
        endpoint=HISTORIC_ENDPOINT,
        query_params=params,
        download_mode=download_mode,
    )
    imported = 0
    pages = 0
    try:
        for page in fetch_pages(
            config,
            endpoint=HISTORIC_ENDPOINT,
            source="usajobs_historic",
            params=params,
            conn=conn,
            max_pages=max_pages,
            auth_required=False,
            dry_run=dry_run,
        ):
            pages += 1
            source_query_hash = query_hash(params)
            for record in _historic_records(page.payload):
                upsert_job(
                    conn,
                    job_from_historic_record(
                        record,
                        source_query_hash=source_query_hash,
                        raw_json_path=page.response_path,
                    ),
                )
                imported += 1
            update_manifest(
                conn,
                manifest_id,
                pages_completed=pages,
                actual_records=imported,
            )
    except Exception as exc:
        complete_manifest(conn, manifest_id, status="failed", actual_records=imported, notes=str(exc))
        raise
    complete_manifest(conn, manifest_id, actual_records=imported)
    return ImportResult(pages, imported, manifest_id)


def import_announcement_text_for_jobs(
    conn,
    config: Config,
    jobs: Iterable[Mapping[str, Any]],
    *,
    batch_size: int = 1,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> ImportResult:
    init_schema(conn)
    job_map = {
        str(job["usajobs_control_number"]): int(job["id"])
        for job in jobs
        if job.get("id") is not None and job.get("usajobs_control_number")
    }
    manifest_id = start_manifest(
        conn,
        source="usajobs_announcement_text",
        endpoint=ANNOUNCEMENT_TEXT_ENDPOINT,
        download_mode="FOCUSED_FULL_DOWNLOAD",
        filters={"selected_control_numbers": list(job_map)},
        estimated_records=len(job_map),
    )
    create_job_import_scope(
        conn,
        name="AnnouncementText Selected Jobs",
        source="usajobs_announcement_text",
        endpoint=ANNOUNCEMENT_TEXT_ENDPOINT,
        query_params={"USAJOBSControlNumbers": ",".join(job_map)},
        download_mode="FOCUSED_FULL_DOWNLOAD",
    )
    imported = 0
    pages = 0
    try:
        for batch in _batches(list(job_map), batch_size):
            params = {"USAJOBSControlNumbers": ",".join(batch)}
            for page in fetch_pages(
                config,
                endpoint=ANNOUNCEMENT_TEXT_ENDPOINT,
                source="usajobs_announcement_text",
                params=params,
                conn=conn,
                max_pages=max_pages,
                auth_required=False,
                dry_run=dry_run,
            ):
                pages += 1
                for record in _historic_records(page.payload):
                    control = str(record.get("usajobsControlNumber") or "")
                    job_id = job_map.get(control)
                    if job_id is None:
                        continue
                    text = job_text_from_announcement_text(record)
                    text["raw_json_path"] = page.response_path
                    upsert_job_text(conn, job_id, text)
                    imported += 1
                update_manifest(
                    conn,
                    manifest_id,
                    pages_completed=pages,
                    actual_records=imported,
                )
    except Exception as exc:
        complete_manifest(conn, manifest_id, status="failed", actual_records=imported, notes=str(exc))
        raise
    complete_manifest(conn, manifest_id, actual_records=imported)
    return ImportResult(pages, imported, manifest_id)


def import_announcement_text_by_filters(
    conn,
    config: Config,
    query_params: Mapping[str, Any],
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
    download_mode: str = "FOCUSED_FULL_DOWNLOAD",
) -> ImportResult:
    """Import AnnouncementText with the same documented filters as HistoricJoa.

    This is the fast path for agency/date/series slices. It avoids one request
    per control number and attaches text to already-imported jobs by control
    number.
    """
    init_schema(conn)
    params = normalize_historic_params(query_params)
    manifest_id = start_manifest(
        conn,
        source="usajobs_announcement_text",
        endpoint=ANNOUNCEMENT_TEXT_ENDPOINT,
        download_mode=download_mode,
        filters=params,
    )
    create_job_import_scope(
        conn,
        name="AnnouncementText Filter Scope",
        source="usajobs_announcement_text",
        endpoint=ANNOUNCEMENT_TEXT_ENDPOINT,
        query_params=params,
        download_mode=download_mode,
    )
    imported = 0
    skipped = 0
    pages = 0
    try:
        for page in fetch_pages(
            config,
            endpoint=ANNOUNCEMENT_TEXT_ENDPOINT,
            source="usajobs_announcement_text",
            params=params,
            conn=conn,
            max_pages=max_pages,
            auth_required=False,
            dry_run=dry_run,
        ):
            pages += 1
            for record in _historic_records(page.payload):
                control = str(record.get("usajobsControlNumber") or "")
                job_id = _job_id_for_control(conn, control)
                if job_id is None:
                    skipped += 1
                    continue
                text = job_text_from_announcement_text(record)
                text["raw_json_path"] = page.response_path
                upsert_job_text(conn, job_id, text)
                imported += 1
            update_manifest(
                conn,
                manifest_id,
                pages_completed=pages,
                actual_records=imported,
                notes=f"Skipped {skipped} text records without matching imported jobs.",
            )
    except Exception as exc:
        complete_manifest(conn, manifest_id, status="failed", actual_records=imported, notes=str(exc))
        raise
    complete_manifest(
        conn,
        manifest_id,
        actual_records=imported,
        notes=f"Skipped {skipped} text records without matching imported jobs.",
    )
    return ImportResult(pages, imported, manifest_id)


def fetch_pages(
    config: Config,
    *,
    endpoint: str,
    source: str,
    params: Mapping[str, Any] | None = None,
    conn=None,
    max_pages: int | None = None,
    auth_required: bool,
    dry_run: bool = False,
    sleep_seconds: float = 0.0,
) -> Iterable[PageResult]:
    if auth_required and not config.has_usajobs_credentials and not dry_run:
        raise MissingCredentialsError(
            "USAJOBS Search requires USAJOBS_USER_AGENT and USAJOBS_AUTHORIZATION_KEY in .env"
        )

    base_params = (
        normalize_historic_params(params or {})
        if endpoint in {HISTORIC_ENDPOINT, ANNOUNCEMENT_TEXT_ENDPOINT}
        else dict(params or {})
    )
    current_params = dict(base_params)
    page_number = int(current_params.get("Page") or 1)
    pages_yielded = 0
    while True:
        if max_pages is not None and pages_yielded >= max_pages:
            break
        if dry_run:
            payload = _dry_run_payload(endpoint)
            status_code = 200
        else:
            payload, status_code = request_json(
                endpoint,
                current_params,
                config,
                auth_required=auth_required,
            )

        record_count = _record_count(payload, endpoint)
        response_path = save_raw_payload(
            config.raw_data_path,
            source=source,
            endpoint=endpoint,
            params=current_params,
            page_number=page_number,
            payload=payload,
        )
        if conn is not None:
            record_raw_response(
                conn,
                source=source,
                endpoint=endpoint,
                query_params=current_params,
                response_path=response_path,
                status_code=status_code,
                record_count=record_count,
                page_number=page_number,
            )

        yield PageResult(page_number, payload, status_code, response_path, record_count)
        pages_yielded += 1

        next_params = next_page_params(endpoint, payload, base_params, current_params)
        if not next_params:
            break
        current_params = next_params
        page_number += 1
        if sleep_seconds:
            time.sleep(sleep_seconds)


def request_json(
    endpoint: str,
    params: Mapping[str, Any],
    config: Config,
    *,
    auth_required: bool,
    max_retries: int = 5,
) -> tuple[dict[str, Any], int]:
    url = USAJOBS_HOST + endpoint
    headers = usajobs_headers(config, include_auth=auth_required)
    for attempt in range(max_retries + 1):
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 429 and attempt < max_retries:
            time.sleep(_retry_sleep(response, attempt))
            continue
        if response.status_code >= 500 and attempt < max_retries:
            time.sleep(_retry_sleep(response, attempt))
            continue
        if response.status_code == 204:
            return {}, response.status_code
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise UsaJobsImportError(f"{endpoint} failed with HTTP {response.status_code}") from exc
        return response.json(), response.status_code
    raise UsaJobsImportError(f"{endpoint} failed after {max_retries} retries")


def usajobs_headers(config: Config, *, include_auth: bool) -> dict[str, str]:
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": config.usajobs_user_agent or "GovJobs local importer",
    }
    if include_auth:
        headers["Authorization-Key"] = config.usajobs_authorization_key or ""
    return headers


def save_raw_payload(
    raw_root: Path,
    *,
    source: str,
    endpoint: str,
    params: Mapping[str, Any],
    page_number: int,
    payload: Mapping[str, Any],
) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    endpoint_slug = endpoint.strip("/").replace("/", "_").lower()
    digest = query_hash(params)
    out = raw_root / source / endpoint_slug / day / f"{digest}_{page_number:05d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(out)


def query_hash(params: Mapping[str, Any]) -> str:
    encoded = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def next_page_params(
    endpoint: str,
    payload: Mapping[str, Any],
    base_params: Mapping[str, Any],
    current_params: Mapping[str, Any],
) -> dict[str, Any] | None:
    if endpoint == SEARCH_ENDPOINT:
        items = _search_items(payload)
        if not items:
            return None
        search_result = payload.get("SearchResult", {})
        total = int(search_result.get("SearchResultCountAll") or search_result.get("SearchResultCount") or 0)
        per_page = int(current_params.get("ResultsPerPage") or len(items) or 1)
        current_page = int(current_params.get("Page") or 1)
        if current_page * per_page >= total:
            return None
        return {**dict(current_params), "Page": current_page + 1}

    paging = payload.get("paging") or payload.get("Paging") or {}
    next_url = paging.get("next") if isinstance(paging, Mapping) else None
    if next_url:
        parsed = urlparse(next_url)
        parsed_params = dict(parse_qsl(parsed.query))
        if endpoint in {HISTORIC_ENDPOINT, ANNOUNCEMENT_TEXT_ENDPOINT}:
            parsed_params = normalize_historic_params(parsed_params)
        return parsed_params or None
    metadata = paging.get("metadata", {}) if isinstance(paging, Mapping) else {}
    token = metadata.get("continuationToken") or metadata.get("ContinuationToken")
    if token:
        return {**dict(base_params), "continuationtoken": token}
    return None


def _search_items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = payload.get("SearchResult", {}) if isinstance(payload, Mapping) else {}
    items = result.get("SearchResultItems", []) if isinstance(result, Mapping) else []
    return items if isinstance(items, list) else []


def _historic_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = payload.get("data") or payload.get("Data") or []
    return records if isinstance(records, list) else []


def normalize_historic_params(params: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    invalid: list[str] = []
    for key, value in params.items():
        canonical = HISTORIC_PARAM_ALIASES.get(key, key)
        if canonical not in HISTORIC_FILTER_PARAMS:
            invalid.append(key)
            continue
        if value is None or value == "":
            continue
        normalized[canonical] = value
    if invalid:
        valid = ", ".join(sorted(HISTORIC_FILTER_PARAMS - {"continuationtoken"}))
        raise ValueError(f"Unsupported HistoricJoa filter(s): {invalid}. Use: {valid}.")
    return normalized


def _job_id_for_control(conn, control_number: str) -> int | None:
    if not control_number:
        return None
    row = conn.execute(
        """
        SELECT id FROM jobs
        WHERE usajobs_control_number=?
        ORDER BY CASE source WHEN 'usajobs_historic' THEN 0 ELSE 1 END, id
        LIMIT 1
        """,
        (control_number,),
    ).fetchone()
    return int(row["id"]) if row else None


def _record_count(payload: Mapping[str, Any], endpoint: str) -> int:
    if endpoint == SEARCH_ENDPOINT:
        return len(_search_items(payload))
    return len(_historic_records(payload))


def _retry_sleep(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(30.0, 2.0**attempt)


def _dry_run_payload(endpoint: str) -> dict[str, Any]:
    if endpoint == SEARCH_ENDPOINT:
        return {
            "SearchResult": {
                "SearchResultCountAll": 1,
                "SearchResultCount": 1,
                "SearchResultItems": [
                    {
                        "MatchedObjectId": "DRYRUN-SEARCH-1",
                        "MatchedObjectDescriptor": {
                            "PositionID": "DRYRUN-SEARCH-1",
                            "PositionTitle": "Dry Run Program Analyst",
                            "DepartmentName": "Department of Homeland Security",
                            "OrganizationName": "Federal Emergency Management Agency",
                            "PositionLocationDisplay": "Chicago, Illinois",
                            "PositionLocation": [
                                {"CityName": "Chicago", "CountrySubDivisionCode": "IL"}
                            ],
                            "JobCategory": {"Code": "0343"},
                            "JobGrade": {"Code": "GS"},
                            "PositionRemuneration": {
                                "MinimumRange": "100000",
                                "MaximumRange": "150000",
                                "Description": "Per Year",
                            },
                            "ApplicationCloseDate": "2026-12-31T23:59:59.0000",
                            "UserArea": {
                                "Details": {
                                    "JobSummary": "Dry-run current job summary.",
                                    "LowGrade": "13",
                                    "HighGrade": "13",
                                    "HiringPath": ["public"],
                                }
                            },
                        },
                    }
                ],
            }
        }
    record = {
        "usajobsControlNumber": "900000001",
        "announcementNumber": "DRY-HIST-1",
        "positionTitle": "Dry Run Emergency Management Specialist",
        "hiringDepartmentName": "Department of Homeland Security",
        "hiringAgencyName": "Federal Emergency Management Agency",
        "payScale": "GS",
        "minimumGrade": "13",
        "maximumGrade": "13",
        "minimumSalary": 100000,
        "maximumSalary": 150000,
        "salaryType": "Per Year",
        "positionOpenDate": "2026-01-01",
        "positionCloseDate": "2026-01-15",
        "jobcategories": {"series": "0089"},
        "positionlocations": {
            "positionLocationCity": "Chicago",
            "positionLocationState": "Illinois",
            "positionLocationCountry": "United States",
        },
    }
    if endpoint == ANNOUNCEMENT_TEXT_ENDPOINT:
        record.update(
            {
                "summary": "Dry-run announcement summary.",
                "requirementsQualifications": (
                    "Applicants must have one year of specialized experience "
                    "equivalent to the GS-12 level."
                ),
            }
        )
    return {"paging": {"metadata": {"totalCount": 1, "pageSize": 500}}, "data": [record]}


def _batches(values: list[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]
