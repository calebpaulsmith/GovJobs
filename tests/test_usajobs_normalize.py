from __future__ import annotations

from src.usajobs_normalize import (
    extract_specialized_experience,
    job_from_historic_record,
    job_from_search_item,
    job_text_from_announcement_text,
    job_text_from_search_descriptor,
)


def test_job_text_from_announcement_text_maps_summary_and_qualifications():
    text = job_text_from_announcement_text(
        {
            "summary": "This position supports mitigation grants.",
            "duties": "Review grant applications.",
            "requirementsQualifications": (
                "<p>To qualify for GS-13, applicants must have one year of "
                "specialized experience equivalent to the GS-12 level.</p>"
            ),
            "requirementsEducation": "Education cannot be substituted.",
            "requirementsConditionsOfEmployment": "Must be a U.S. citizen.",
            "evaluations": "Applicants will be evaluated on technical expertise.",
            "requiredDocuments": "Resume and transcripts.",
            "howToApply": "Apply through USAJOBS.",
        }
    )

    assert text["summary"] == "This position supports mitigation grants."
    assert "GS-12" in text["qualifications"]
    assert "<p>" not in text["qualifications"]
    assert "specialized experience" in text["specialized_experience"]
    assert "mitigation grants" in text["raw_text"]
    assert "Apply through USAJOBS" in text["raw_text"]
    assert text["required_document_rows"][0]["description"] == "Resume and transcripts."
    assert text["requirement_rows"][0]["label"] == "Citizenship"
    assert text["qualification_requirement_rows"][0]["requirement_type"] == "specialized_experience"
    assert text["duty_rows"][0]["text"] == "Review grant applications."
    assert text["evaluation_factor_rows"][0]["text"] == "Applicants will be evaluated on technical expertise."


def test_job_text_from_search_descriptor_uses_search_user_area_details():
    text = job_text_from_search_descriptor(
        {
            "QualificationSummary": "One year equivalent to GS-12 is required.",
            "UserArea": {
                "Details": {
                    "JobSummary": "Top summary from current Search.",
                    "MajorDuties": ["Coordinate response planning.", "Brief leadership."],
                    "Education": "No substitution.",
                    "RequiredDocuments": "Resume.",
                    "HowToApply": "Use the apply link.",
                    "Evaluations": "Category rating.",
                    "KeyRequirements": ["Background investigation required."],
                }
            },
        }
    )

    assert text["summary"] == "Top summary from current Search."
    assert "Coordinate response planning" in text["duties"]
    assert "GS-12" in text["specialized_experience"]
    assert "Background investigation" in text["conditions_of_employment"]


def test_extract_specialized_experience_is_conservative():
    assert extract_specialized_experience("General nice-to-have language.") is None
    hit = extract_specialized_experience(
        "Applicants need policy experience. Specialized experience includes "
        "analyzing disaster programs. This must be equivalent to GS-12."
    )
    assert "Specialized experience" in hit
    assert "GS-12" in hit


def test_job_from_search_item_normalizes_core_fields():
    job = job_from_search_item(
        {
            "MatchedObjectId": "123",
            "MatchedObjectDescriptor": {
                "PositionID": "FEMA-SEARCH",
                "PositionTitle": "Program Analyst",
                "PositionURI": "https://www.usajobs.gov/job/123",
                "DepartmentName": "Department of Homeland Security",
                "OrganizationName": "Federal Emergency Management Agency",
                "PositionLocationDisplay": "Chicago, Illinois",
                "PositionLocation": [{"CityName": "Chicago", "CountrySubDivisionCode": "IL"}],
            "JobCategory": {"Code": "343"},
            "JobGrade": {"Code": "GS"},
            "PositionRemuneration": [
                {
                    "MinimumRange": "100,000",
                    "MaximumRange": "150000",
                    "Description": "Per Year",
                }
            ],
                "UserArea": {"Details": {"LowGrade": "13", "HighGrade": "13"}},
            },
        },
        source_query_hash="abc",
        raw_json_path="raw.json",
    )

    assert job["source"] == "usajobs_search"
    assert job["usajobs_control_number"] == "123"
    assert job["series"] == "0343"
    assert job["salary_min"] == 100000
    assert job["state"] == "IL"
    assert job["grade_rows"][0]["pay_plan"] == "GS"
    assert job["salary_range_rows"][0]["minimum"] == 100000
    assert job["application_option_rows"][0]["apply_online_url"] == "https://www.usajobs.gov/job/123"


def test_job_from_historic_record_normalizes_core_fields():
    job = job_from_historic_record(
        {
            "usajobsControlNumber": "456",
            "announcementNumber": "FEMA-HIST",
            "positionTitle": "Emergency Management Specialist",
            "hiringDepartmentName": "Department of Homeland Security",
            "hiringAgencyName": "Federal Emergency Management Agency",
            "hiringAgencyCode": "HSCB",
            "hiringDepartmentCode": "HS",
            "payScale": "GS",
            "minimumGrade": "12",
            "maximumGrade": "13",
            "minimumSalary": 90000,
            "maximumSalary": 140000,
            "salaryType": "Per Year",
            "positionOpenDate": "2026-01-01",
            "positionCloseDate": "2026-01-15",
            "jobCategories": [{"series": "89"}, {"series": "343"}],
            "positionLocations": [
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
            "hiringPaths": [{"hiringPath": "The public"}],
            "teleworkEligible": "Y",
            "totalOpenings": "4",
            "securityClearance": "Not Required",
            "travelRequirement": "Occasional travel",
            "agencyContactEmail": "hr@example.test",
        }
    )

    assert job["source"] == "usajobs_historic"
    assert job["position_id"] == "456"
    assert job["announcement_number"] == "FEMA-HIST"
    assert job["series"] == "0089"
    assert job["state"] == "IL"
    assert job["agency_code"] == "HSCB"
    assert job["department_code"] == "HS"
    assert [row["state"] for row in job["locations"]] == ["IL", "TX"]
    assert [row["series"] for row in job["categories"]] == ["0089", "0343"]
    assert job["hiring_path_rows"][0]["label"] == "The public"
    assert job["grade_rows"][0]["grade_high"] == "13"
    assert job["salary_range_rows"][0]["maximum"] == 140000
    assert job["opening_rows"][0]["total_openings"] == 4
    assert job["security_clearance_rows"][0]["clearance"] == "Not Required"
    assert job["travel_requirement_rows"][0]["travel_required"] == "Occasional travel"
    assert job["contact_rows"][0]["email"] == "hr@example.test"
    assert job["url"] == "https://www.usajobs.gov/job/456"
    assert job["remote_status"] == "hybrid"


def test_job_from_historic_record_normalizes_puerto_rico():
    job = job_from_historic_record(
        {
            "usajobsControlNumber": "789",
            "announcementNumber": "FEMA-PR",
            "positionTitle": "Emergency Management Specialist",
            "hiringAgencyName": "Federal Emergency Management Agency",
            "positionlocations": {
                "positionLocationCity": "Guaynabo",
                "positionLocationState": "Puerto Rico",
                "positionLocationCountry": "United States",
            },
        }
    )
    assert job["state"] == "PR"
