from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import Config
from src.database import connect, init_schema, upsert_job
from src.data_import import MissingCredentialsError, normalize_historic_params
from src.usajobs_announcement_text_api import (
    import_announcement_text,
    import_announcement_text_filters,
)
from src.usajobs_current_api import import_search
from src.usajobs_historic_api import import_historic


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        usajobs_user_agent="user@example.test",
        usajobs_authorization_key="secret-key",
        database_path=tmp_path / "federal_jobs.sqlite",
        raw_data_path=tmp_path / "raw",
        processed_data_path=tmp_path / "processed",
        max_full_download_gb=5.0,
        max_database_gb=10.0,
        max_full_download_rows=5_000_000,
        max_import_hours=8.0,
        log_level="WARNING",
        log_file=tmp_path / "app.log",
    )


@pytest.fixture
def conn(cfg: Config):
    db = connect(cfg.database_path)
    init_schema(db)
    try:
        yield db
    finally:
        db.close()


def _no_creds(cfg: Config) -> Config:
    return Config(
        usajobs_user_agent=None,
        usajobs_authorization_key=None,
        database_path=cfg.database_path,
        raw_data_path=cfg.raw_data_path,
        processed_data_path=cfg.processed_data_path,
        max_full_download_gb=cfg.max_full_download_gb,
        max_database_gb=cfg.max_database_gb,
        max_full_download_rows=cfg.max_full_download_rows,
        max_import_hours=cfg.max_import_hours,
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )


def test_import_search_requires_credentials(conn, cfg):
    with pytest.raises(MissingCredentialsError):
        import_search(conn, _no_creds(cfg), {"Keyword": "FEMA"}, max_pages=1)

    manifest = conn.execute("SELECT * FROM import_manifests").fetchone()
    assert manifest["status"] == "failed"
    assert "requires USAJOBS_USER_AGENT" in manifest["notes"]


def test_import_search_writes_jobs_text_raw_and_manifest(conn, cfg, monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url == "https://data.usajobs.gov/api/Search"
        assert params["Organization"] == "HSCB"
        assert headers["Authorization-Key"] == "secret-key"
        return FakeResponse(
            {
            "SearchResult": {
                "SearchResultCountAll": 1,
                "SearchResultCount": 1,
                "SearchResultItems": [
                    {
                        "MatchedObjectId": "777777777",
                        "MatchedObjectDescriptor": {
                            "PositionID": "FEMA-SEARCH-1",
                            "PositionTitle": "Program Analyst",
                            "PositionURI": "https://www.usajobs.gov/job/777777777",
                            "DepartmentName": "Department of Homeland Security",
                            "OrganizationName": "Federal Emergency Management Agency",
                            "PositionLocationDisplay": "Chicago, Illinois",
                            "PositionLocation": [
                                {
                                    "CityName": "Chicago",
                                    "CountrySubDivisionCode": "IL",
                                }
                            ],
                            "JobCategory": {"Code": "0343"},
                            "JobGrade": {"Code": "GS"},
                            "PositionRemuneration": {
                                "MinimumRange": "100000",
                                "MaximumRange": "150000",
                                "Description": "Per Year",
                            },
                            "ApplicationCloseDate": "2026-05-30T23:59:59.0000",
                            "UserArea": {
                                "Details": {
                                    "JobSummary": "Top description for the live posting.",
                                    "LowGrade": "13",
                                    "HighGrade": "13",
                                    "HiringPath": ["public"],
                                    "Requirements": (
                                        "Applicants must have one year of specialized "
                                        "experience equivalent to GS-12."
                                    ),
                                    "RequiredDocuments": "Resume.",
                                }
                            },
                        },
                    }
                ],
            }
            }
        )

    monkeypatch.setattr("src.data_import.requests.get", fake_get)

    result = import_search(conn, cfg, {"Organization": "HSCB"}, max_pages=1)

    assert result.records_imported == 1
    job = conn.execute("SELECT * FROM jobs").fetchone()
    text = conn.execute("SELECT * FROM job_text WHERE job_id=?", (job["id"],)).fetchone()
    raw = conn.execute("SELECT * FROM raw_api_responses").fetchone()
    manifest = conn.execute("SELECT * FROM import_manifests").fetchone()

    assert job["source"] == "usajobs_search"
    assert job["agency_code"] == "HSCB"
    assert job["series"] == "0343"
    assert job["state"] == "IL"
    assert text["summary"] == "Top description for the live posting."
    assert "GS-12" in text["qualifications"]
    assert conn.execute("SELECT COUNT(*) FROM job_locations").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_categories").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_required_documents").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_grades").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_salary_ranges").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_qualification_requirements").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_import_scopes").fetchone()[0] == 1
    assert Path(raw["response_path"]).exists()
    assert json.loads(Path(raw["response_path"]).read_text(encoding="utf-8"))["SearchResult"]
    assert manifest["status"] == "completed"


def test_import_historic_follows_continuation_and_upserts(conn, cfg, monkeypatch):
    calls: list[str] = []

    def fake_get(url, params, headers, timeout):
        calls.append(url + "?" + "&".join(f"{key}={value}" for key, value in params.items()))
        if len(calls) == 1:
            payload = {
                "paging": {
                    "metadata": {"totalCount": 2, "pageSize": 1, "continuationToken": "abc"},
                    "next": "/api/historicjoa?continuationtoken=abc",
                },
                "data": [_historic_record("100", "HIST-1")],
            }
        else:
            payload = {
                "paging": {"metadata": {"totalCount": 2, "pageSize": 1}},
                "data": [_historic_record("101", "HIST-2")],
            }
        return FakeResponse(payload)

    monkeypatch.setattr("src.data_import.requests.get", fake_get)

    result = import_historic(
        conn,
        cfg,
        {"StartPositionOpenDate": "2026-01-01", "EndPositionOpenDate": "2026-01-31"},
        max_pages=2,
        download_mode="STAGED_DOWNLOAD",
    )

    assert result.pages_completed == 2
    assert result.records_imported == 2
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM job_locations").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM job_categories").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM job_grades").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM job_salary_ranges").fetchone()[0] == 2
    assert conn.execute("SELECT agency_code FROM jobs LIMIT 1").fetchone()[0] == "HSCB"
    assert conn.execute("SELECT COUNT(*) FROM raw_api_responses").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM job_import_scopes").fetchone()[0] == 1
    assert "continuationtoken=abc" in calls[1]


def test_historic_params_are_canonicalized_and_validated():
    assert normalize_historic_params(
        {"HiringAgencyCode": "HSCB", "startpositionopendate": "2026-01-01"}
    ) == {"HiringAgencyCodes": "HSCB", "StartPositionOpenDate": "2026-01-01"}
    with pytest.raises(ValueError, match="Unsupported HistoricJoa"):
        normalize_historic_params({"Keyword": "FEMA"})


def test_import_announcement_text_for_selected_jobs(conn, cfg, monkeypatch):
    job_id = upsert_job(
        conn,
        {
            "source": "usajobs_historic",
            "usajobs_control_number": "200",
            "position_id": "200",
            "announcement_number": "HIST-200",
            "title": "Emergency Management Specialist",
        },
    )
    def fake_get(url, params, headers, timeout):
        assert url == "https://data.usajobs.gov/api/historicjoa/announcementtext"
        assert params["USAJOBSControlNumbers"] == "200"
        return FakeResponse(
            {
            "paging": {"metadata": {"totalCount": 1, "pageSize": 500}},
            "data": [
                {
                    "usajobsControlNumber": "200",
                    "summary": "This job manages disaster recovery programs.",
                    "requirementsQualifications": (
                        "To qualify at GS-13, applicants must have one year of "
                        "specialized experience equivalent to the GS-12 level."
                    ),
                    "duties": "Coordinate recovery policy.",
                }
            ],
            }
        )

    monkeypatch.setattr("src.data_import.requests.get", fake_get)

    result = import_announcement_text(
        conn,
        cfg,
        [{"id": job_id, "usajobs_control_number": "200"}],
        batch_size=10,
    )

    text = conn.execute("SELECT * FROM job_text WHERE job_id=?", (job_id,)).fetchone()
    assert result.records_imported == 1
    assert text["summary"] == "This job manages disaster recovery programs."
    assert "GS-12" in text["qualifications"]
    assert "specialized experience" in text["specialized_experience"]
    assert conn.execute(
        "SELECT COUNT(*) FROM job_qualification_requirements WHERE job_id=?", (job_id,)
    ).fetchone()[0] == 1
    assert conn.execute("SELECT status FROM import_manifests").fetchone()["status"] == "completed"


def test_import_announcement_text_by_filters_uses_one_filtered_request(conn, cfg, monkeypatch):
    job_id = upsert_job(
        conn,
        {
            "source": "usajobs_historic",
            "usajobs_control_number": "300",
            "position_id": "300",
            "announcement_number": "HIST-300",
            "title": "Emergency Management Specialist",
        },
    )

    calls: list[dict] = []

    def fake_get(url, params, headers, timeout):
        calls.append(dict(params))
        assert url == "https://data.usajobs.gov/api/historicjoa/announcementtext"
        assert params["HiringAgencyCodes"] == "HSCB"
        assert params["StartPositionOpenDate"] == "2026-01-01"
        return FakeResponse(
            {
                "paging": {"metadata": {"totalCount": 1, "pageSize": 500}},
                "data": [
                    {
                        "usajobsControlNumber": "300",
                        "summary": "This job manages mitigation programs.",
                        "requirementsQualifications": "One year equivalent to GS-12.",
                    }
                ],
            }
        )

    monkeypatch.setattr("src.data_import.requests.get", fake_get)

    result = import_announcement_text_filters(
        conn,
        cfg,
        {
            "HiringAgencyCode": "HSCB",
            "startpositionopendate": "2026-01-01",
            "EndPositionOpenDate": "2026-01-31",
        },
        max_pages=1,
    )

    text = conn.execute("SELECT * FROM job_text WHERE job_id=?", (job_id,)).fetchone()
    assert len(calls) == 1
    assert result.records_imported == 1
    assert text["summary"] == "This job manages mitigation programs."


def _historic_record(control: str, announcement: str) -> dict:
    return {
        "usajobsControlNumber": control,
        "announcementNumber": announcement,
        "positionTitle": "Emergency Management Specialist",
        "hiringDepartmentName": "Department of Homeland Security",
        "hiringAgencyName": "Federal Emergency Management Agency",
        "hiringAgencyCode": "HSCB",
        "hiringDepartmentCode": "HS",
        "payScale": "GS",
        "minimumGrade": "13",
        "maximumGrade": "13",
        "minimumSalary": 100000,
        "maximumSalary": 150000,
        "salaryType": "Per Year",
        "positionOpenDate": "2026-01-01",
        "positionCloseDate": "2026-01-15",
        "jobcategories": [{"series": "0089"}, {"series": "0343"}],
        "positionlocations": [
            {
                "positionLocationCity": "Chicago",
                "positionLocationState": "Illinois",
                "positionLocationCountry": "United States",
            },
            {
                "positionLocationCity": "Denton",
                "positionLocationState": "Texas",
                "positionLocationCountry": "United States",
            },
        ],
        "hiringpaths": {"hiringPath": "public"},
    }
