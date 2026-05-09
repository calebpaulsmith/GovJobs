"""Normalize USAJOBS API payloads into database-ready dictionaries."""
from __future__ import annotations

import re
from html import unescape
from collections.abc import Mapping
from typing import Any

from src.database import build_raw_job_text


STATE_NAMES = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "Puerto Rico": "PR",
    "Guam": "GU",
    "American Samoa": "AS",
    "Northern Mariana Islands": "MP",
    "U.S. Virgin Islands": "VI",
    "Virgin Islands": "VI",
}


def job_from_search_item(
    item: Mapping[str, Any],
    *,
    source_query_hash: str | None = None,
    raw_json_path: str | None = None,
    default_agency_code: str | None = None,
    default_department_code: str | None = None,
) -> dict[str, Any]:
    descriptor = _mapping(item.get("MatchedObjectDescriptor"))
    details = _mapping(_mapping(descriptor.get("UserArea")).get("Details"))
    location = _first(descriptor.get("PositionLocation"))
    remuneration = _first(descriptor.get("PositionRemuneration"))
    category = _first(descriptor.get("JobCategory"))
    grade = _first(descriptor.get("JobGrade"))

    parsed_dept, parsed_sub = _parse_organization_codes(
        details.get("OrganizationCodes") or descriptor.get("OrganizationCodes")
    )

    return {
        "source": "usajobs_search",
        "usajobs_control_number": _text(item.get("MatchedObjectId")),
        "position_id": _text(descriptor.get("PositionID") or item.get("MatchedObjectId")),
        "announcement_number": _text(descriptor.get("PositionID") or item.get("MatchedObjectId")),
        "title": _text(descriptor.get("PositionTitle")),
        "department": _text(descriptor.get("DepartmentName")),
        "agency": _text(descriptor.get("OrganizationName")),
        "sub_agency": _text(details.get("SubAgencyName")),
        "agency_code": _text(
            descriptor.get("OrganizationCode")
            or descriptor.get("OrganizationID")
            or details.get("OrganizationCode")
            or details.get("OrganizationID")
            or parsed_sub
            or default_agency_code
        ),
        "department_code": _text(
            descriptor.get("DepartmentCode")
            or details.get("DepartmentCode")
            or parsed_dept
            or default_department_code
        ),
        "series": _series(category.get("Code")),
        "grade_low": _text(details.get("LowGrade")),
        "grade_high": _text(details.get("HighGrade")),
        "pay_plan": _text(grade.get("Code")),
        "salary_min": _float(remuneration.get("MinimumRange")),
        "salary_max": _float(remuneration.get("MaximumRange")),
        "salary_type": _salary_type(
            remuneration.get("Description") or remuneration.get("RateIntervalCode")
        ),
        "location_text": _text(descriptor.get("PositionLocationDisplay")),
        "state": _state_from_location(location),
        "city": _text(location.get("CityName") or location.get("LocationName")),
        "remote_status": _remote_status(details.get("RemoteIndicator"), details.get("TeleworkEligible")),
        "telework_status": _text(details.get("TeleworkEligible")),
        "open_date": _date(descriptor.get("PublicationStartDate") or descriptor.get("PositionStartDate")),
        "close_date": _date(descriptor.get("ApplicationCloseDate") or descriptor.get("PositionEndDate")),
        "hiring_paths": details.get("HiringPath"),
        "appointment_type": _name_or_text(descriptor.get("PositionOfferingType")),
        "work_schedule": _name_or_text(descriptor.get("PositionSchedule")),
        "supervisory_status": _text(details.get("SupervisoryStatus")),
        "travel_required": _text(details.get("TravelCode")),
        "security_clearance": _text(details.get("SecurityClearance")),
        "promotion_potential": _text(details.get("PromotionPotential")),
        "url": _text(descriptor.get("PositionURI")),
        "source_endpoint": "/api/Search",
        "source_query_hash": source_query_hash,
        "raw_json_path": raw_json_path,
        "locations": search_locations(descriptor),
        "categories": search_categories(descriptor),
        "hiring_path_rows": hiring_path_rows(details.get("HiringPath")),
        "grade_rows": grade_rows(
            pay_plan=_text(grade.get("Code")),
            grade_low=_text(details.get("LowGrade")),
            grade_high=_text(details.get("HighGrade")),
            promotion_potential=_text(details.get("PromotionPotential")),
        ),
        "salary_range_rows": search_salary_ranges(descriptor),
        "opening_rows": search_openings(descriptor),
        "contact_rows": contact_rows(details),
        "security_clearance_rows": security_clearance_rows(details),
        "travel_requirement_rows": travel_requirement_rows(details),
        "application_option_rows": application_option_rows(descriptor, details),
    }


def job_from_historic_record(
    record: Mapping[str, Any],
    *,
    source_query_hash: str | None = None,
    raw_json_path: str | None = None,
) -> dict[str, Any]:
    location = _first(_get(record, "positionLocations", "positionlocations"))
    category = _first(_get(record, "jobCategories", "jobcategories"))
    return {
        "source": "usajobs_historic",
        "usajobs_control_number": _text(record.get("usajobsControlNumber")),
        "position_id": _text(record.get("usajobsControlNumber")),
        "announcement_number": _text(record.get("announcementNumber")),
        "title": _text(record.get("positionTitle")),
        "department": _text(record.get("hiringDepartmentName")),
        "agency": _text(record.get("hiringAgencyName")),
        "sub_agency": _text(record.get("hiringSubelementName")),
        "agency_code": _text(record.get("hiringAgencyCode")),
        "department_code": _text(record.get("hiringDepartmentCode")),
        "series": _series(category.get("series")),
        "grade_low": _text(record.get("minimumGrade")),
        "grade_high": _text(record.get("maximumGrade")),
        "pay_plan": _text(record.get("payScale")),
        "salary_min": _float(record.get("minimumSalary")),
        "salary_max": _float(record.get("maximumSalary")),
        "salary_type": _salary_type(record.get("salaryType")),
        "location_text": _historic_location_text(location),
        "state": _state_from_location(location),
        "city": _text(location.get("positionLocationCity")),
        "remote_status": _remote_status(None, record.get("teleworkEligible")),
        "telework_status": _text(record.get("teleworkEligible")),
        "open_date": _date(record.get("positionOpenDate")),
        "close_date": _date(record.get("positionCloseDate")),
        "hiring_paths": _get(record, "hiringPaths", "hiringpaths"),
        "appointment_type": _text(record.get("appointmentType")),
        "work_schedule": _text(record.get("workSchedule")),
        "supervisory_status": _text(record.get("supervisoryStatus")),
        "travel_required": _text(record.get("travelRequirement")),
        "security_clearance": _text(record.get("securityClearance")),
        "promotion_potential": _text(record.get("promotionPotential")),
        "url": _historic_url(record.get("usajobsControlNumber")),
        "source_endpoint": "/api/historicjoa",
        "source_query_hash": source_query_hash,
        "raw_json_path": raw_json_path,
        "locations": historic_locations(record),
        "categories": historic_categories(record),
        "hiring_path_rows": hiring_path_rows(_get(record, "hiringPaths", "hiringpaths")),
        "grade_rows": grade_rows(
            pay_plan=_text(record.get("payScale")),
            grade_low=_text(record.get("minimumGrade")),
            grade_high=_text(record.get("maximumGrade")),
            promotion_potential=_text(record.get("promotionPotential")),
        ),
        "salary_range_rows": historic_salary_ranges(record),
        "opening_rows": historic_openings(record),
        "contact_rows": contact_rows(record),
        "security_clearance_rows": security_clearance_rows(record),
        "travel_requirement_rows": travel_requirement_rows(record),
        "application_option_rows": application_option_rows(record, record),
    }


def job_text_from_announcement_text(record: Mapping[str, Any]) -> dict[str, str | None]:
    """Map HistoricJoa AnnouncementText fields into the `job_text` schema."""
    qualifications = _text(record.get("requirementsQualifications"))
    result: dict[str, str | None] = {
        "summary": _text(record.get("summary")),
        "duties": _text(record.get("duties") or record.get("majorDutiesList")),
        "qualifications": qualifications,
        "specialized_experience": extract_specialized_experience(qualifications or ""),
        "education": _text(record.get("requirementsEducation")),
        "required_documents": _text(
            record.get("requiredDocuments") or record.get("requiredStandardDocuments")
        ),
        "how_to_apply": _text(record.get("howToApply")),
        "evaluation_criteria": _text(record.get("evaluations")),
        "conditions_of_employment": _text(
            record.get("requirementsConditionsOfEmployment") or record.get("requirements")
        ),
        "raw_json_path": None,
        "required_document_rows": required_document_rows(
            record.get("requiredStandardDocuments") or record.get("requiredDocuments")
        ),
        "requirement_rows": requirement_rows(
            record.get("requirementsConditionsOfEmployment") or record.get("requirements"),
            source_field="conditions_of_employment",
        ),
        "qualification_requirement_rows": qualification_requirement_rows(qualifications),
        "duty_rows": text_rows(record.get("duties") or record.get("majorDutiesList"), "duties"),
        "evaluation_factor_rows": text_rows(record.get("evaluations"), "evaluation_criteria"),
    }
    result["raw_text"] = build_raw_job_text(result)
    return result


def job_text_from_search_descriptor(descriptor: Mapping[str, Any]) -> dict[str, str | None]:
    """Extract long-ish text already present in a Search API result."""
    details = _mapping(descriptor.get("UserArea")).get("Details", {})
    details = _mapping(details)
    qualifications = _text(descriptor.get("QualificationSummary") or details.get("Requirements"))
    result: dict[str, str | None] = {
        "summary": _text(details.get("JobSummary")),
        "duties": _text(details.get("MajorDuties")),
        "qualifications": qualifications,
        "specialized_experience": extract_specialized_experience(qualifications or ""),
        "education": _text(details.get("Education")),
        "required_documents": _text(details.get("RequiredDocuments")),
        "how_to_apply": _text(details.get("HowToApply")),
        "evaluation_criteria": _text(details.get("Evaluations")),
        "conditions_of_employment": _text(details.get("KeyRequirements")),
        "raw_json_path": None,
        "required_document_rows": required_document_rows(details.get("RequiredDocuments")),
        "requirement_rows": requirement_rows(details.get("KeyRequirements"), source_field="conditions_of_employment"),
        "qualification_requirement_rows": qualification_requirement_rows(qualifications),
        "duty_rows": text_rows(details.get("MajorDuties"), "duties"),
        "evaluation_factor_rows": text_rows(details.get("Evaluations"), "evaluation_criteria"),
    }
    result["raw_text"] = build_raw_job_text(result)
    return result


def search_locations(descriptor: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for location in _as_list(descriptor.get("PositionLocation")):
        loc = _mapping(location)
        row = {
            "location_text": _text(
                loc.get("LocationName")
                or loc.get("DisplayName")
                or descriptor.get("PositionLocationDisplay")
            ),
            "city": _text(loc.get("CityName") or loc.get("LocationName")),
            "state": _state_from_location(loc),
            "country": _text(loc.get("CountryCode") or loc.get("CountryName")),
            "location_code": _text(
                loc.get("LocationID") or loc.get("GeoLocationCode") or loc.get("Code")
            ),
            "latitude": _float(
                loc.get("Latitude")
                or loc.get("latitude")
                or loc.get("PositionLocationLatitude")
            ),
            "longitude": _float(
                loc.get("Longitude")
                or loc.get("longitude")
                or loc.get("PositionLocationLongitude")
            ),
            "remote_indicator": _remote_status(
                _mapping(_mapping(descriptor.get("UserArea")).get("Details")).get("RemoteIndicator"),
                _mapping(_mapping(descriptor.get("UserArea")).get("Details")).get("TeleworkEligible"),
            ),
        }
        if any(row.values()):
            rows.append(row)
    if not rows and descriptor.get("PositionLocationDisplay"):
        rows.append({"location_text": _text(descriptor.get("PositionLocationDisplay"))})
    return rows


def historic_locations(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for location in _as_list(_get(record, "positionLocations", "positionlocations")):
        loc = _mapping(location)
        row = {
            "location_text": _historic_location_text(loc),
            "city": _text(loc.get("positionLocationCity")),
            "state": _state_from_location(loc),
            "country": _text(loc.get("positionLocationCountry")),
            "location_code": _text(loc.get("positionLocationCode") or loc.get("locationCode")),
            "latitude": _float(
                loc.get("positionLocationLatitude")
                or loc.get("latitude")
                or loc.get("Latitude")
            ),
            "longitude": _float(
                loc.get("positionLocationLongitude")
                or loc.get("longitude")
                or loc.get("Longitude")
            ),
            "remote_indicator": _remote_status(None, record.get("teleworkEligible")),
        }
        if any(row.values()):
            rows.append(row)
    return rows


def search_categories(descriptor: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category in _as_list(descriptor.get("JobCategory")):
        cat = _mapping(category)
        series = _series(cat.get("Code") or cat.get("Series"))
        if series:
            rows.append({"series": series, "name": _text(cat.get("Name"))})
    return rows


def historic_categories(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category in _as_list(_get(record, "jobCategories", "jobcategories")):
        cat = _mapping(category)
        series = _series(cat.get("series") or cat.get("Series"))
        if series:
            rows.append({"series": series, "name": _text(cat.get("name") or cat.get("Name"))})
    return rows


def hiring_path_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            label = _text(item.get("hiringPath") or item.get("HiringPath") or item.get("Name"))
            code = _text(item.get("code") or item.get("Code") or item.get("hiringPathCode") or label)
        else:
            label = _text(item)
            code = label
        if code or label:
            rows.append({"code": code, "label": label})
    return rows


def required_document_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            label = _text(item.get("description") or item.get("label") or item.get("Name"))
            rows.append(
                {
                    "code": _text(item.get("code") or item.get("Code")),
                    "label": label,
                    "description": _text(item.get("text") or item.get("description") or label),
                    "required": item.get("required") or item.get("Required"),
                }
            )
        else:
            text = _text(item)
            if text:
                rows.append({"code": None, "label": text[:120], "description": text, "required": None})
    return rows


def grade_rows(
    *,
    pay_plan: str | None,
    grade_low: str | None,
    grade_high: str | None,
    promotion_potential: str | None,
) -> list[dict[str, Any]]:
    if not any((pay_plan, grade_low, grade_high, promotion_potential)):
        return []
    return [
        {
            "pay_plan": pay_plan,
            "grade_low": grade_low,
            "grade_high": grade_high,
            "promotion_potential": promotion_potential,
            "is_primary": True,
        }
    ]


def search_salary_ranges(descriptor: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(_as_list(descriptor.get("PositionRemuneration"))):
        remuneration = _mapping(item)
        row = {
            "minimum": _float(remuneration.get("MinimumRange")),
            "maximum": _float(remuneration.get("MaximumRange")),
            "salary_type": _salary_type(
                remuneration.get("Description") or remuneration.get("RateIntervalCode")
            ),
            "currency": _text(remuneration.get("CurrencyCode")) or "USD",
            "location_text": _text(descriptor.get("PositionLocationDisplay")),
            "is_primary": idx == 0,
        }
        if row["minimum"] is not None or row["maximum"] is not None:
            rows.append(row)
    return rows


def historic_salary_ranges(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    minimum = _float(record.get("minimumSalary"))
    maximum = _float(record.get("maximumSalary"))
    if minimum is None and maximum is None:
        return []
    return [
        {
            "minimum": minimum,
            "maximum": maximum,
            "salary_type": _salary_type(record.get("salaryType")),
            "currency": _text(record.get("salaryCurrency")) or "USD",
            "location_text": None,
            "is_primary": True,
        }
    ]


def search_openings(descriptor: Mapping[str, Any]) -> list[dict[str, Any]]:
    details = _mapping(_mapping(descriptor.get("UserArea")).get("Details"))
    total = _int_value(
        details.get("TotalOpenings")
        or details.get("GOVT_TotalOpenings")
        or descriptor.get("TotalOpenings")
    )
    rows: list[dict[str, Any]] = []
    for location in _as_list(descriptor.get("PositionLocation")):
        loc = _mapping(location)
        openings = _int_value(
            loc.get("Openings")
            or _mapping(loc.get("UserArea")).get("GOVT_Openings")
            or loc.get("GOVT_Openings")
        )
        if openings is not None or total is not None:
            rows.append(
                {
                    "location_text": _text(
                        loc.get("LocationName")
                        or loc.get("DisplayName")
                        or descriptor.get("PositionLocationDisplay")
                    ),
                    "openings": openings,
                    "total_openings": total,
                    "source_field": "PositionLocation",
                }
            )
    if not rows and total is not None:
        rows.append(
            {
                "location_text": _text(descriptor.get("PositionLocationDisplay")),
                "openings": None,
                "total_openings": total,
                "source_field": "TotalOpenings",
            }
        )
    return rows


def historic_openings(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    total = _int_value(
        record.get("totalOpenings")
        or record.get("totalopenings")
        or record.get("GOVT_TotalOpenings")
    )
    rows: list[dict[str, Any]] = []
    for location in _as_list(_get(record, "positionLocations", "positionlocations")):
        loc = _mapping(location)
        openings = _int_value(
            loc.get("positionLocationOpenings")
            or loc.get("openings")
            or loc.get("GOVT_Openings")
        )
        if openings is not None or total is not None:
            rows.append(
                {
                    "location_text": _historic_location_text(loc),
                    "openings": openings,
                    "total_openings": total,
                    "source_field": "positionLocations",
                }
            )
    if not rows and total is not None:
        rows.append({"total_openings": total, "source_field": "totalOpenings"})
    return rows


def contact_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    name = _text(
        source.get("AgencyContactName")
        or source.get("agencyContactName")
        or source.get("ContactName")
        or source.get("contactName")
    )
    email = _text(
        source.get("AgencyContactEmail")
        or source.get("agencyContactEmail")
        or source.get("ContactEmail")
        or source.get("contactEmail")
    )
    phone = _text(
        source.get("AgencyContactPhone")
        or source.get("agencyContactPhone")
        or source.get("ContactPhone")
        or source.get("contactPhone")
    )
    url = _text(
        source.get("AgencyContactWebsite")
        or source.get("agencyContactWebsite")
        or source.get("ContactURL")
        or source.get("contactUrl")
    )
    if not any((name, email, phone, url)):
        return []
    return [
        {
            "contact_type": "public",
            "name": name,
            "email": email,
            "phone": phone,
            "url": url,
            "source_field": "contact",
        }
    ]


def security_clearance_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    clearance = _text(
        source.get("SecurityClearance")
        or source.get("securityClearance")
        or source.get("GOVT_SecurityClearanceRequired")
    )
    sensitivity = _text(
        source.get("PositionSensitivity")
        or source.get("positionSensitivity")
        or source.get("GOVT_PositionSensitivity")
    )
    adjudication = _text(
        source.get("AdjudicationType")
        or source.get("adjudicationType")
        or source.get("GOVT_AdjudicationType")
    )
    if not any((clearance, sensitivity, adjudication)):
        return []
    return [
        {
            "clearance": clearance,
            "position_sensitivity": sensitivity,
            "adjudication_type": adjudication,
            "source_field": "security",
        }
    ]


def travel_requirement_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    travel = _text(
        source.get("TravelCode")
        or source.get("travelRequirement")
        or source.get("TravelRequired")
        or source.get("travelRequired")
    )
    percentage = _text(
        source.get("TravelPercentage")
        or source.get("travelPercentage")
        or source.get("TravelPreference")
    )
    if not any((travel, percentage)):
        return []
    return [
        {
            "travel_required": travel,
            "travel_percentage": percentage,
            "source_field": "travel",
        }
    ]


def application_option_rows(source: Mapping[str, Any], details: Mapping[str, Any]) -> list[dict[str, Any]]:
    row = {
        "apply_online_url": _text(
            details.get("ApplyOnlineUrl")
            or details.get("applyOnlineUrl")
            or source.get("ApplyOnlineUrl")
            or source.get("PositionURI")
            or source.get("positionUri")
        ),
        "disable_apply_online": _optional_truthy(
            details.get("DisableApplyOnline")
            or details.get("GOVT_DisableApplyOnline")
            or source.get("disableApplyOnline")
        ),
        "accepts_uploaded_resumes": _optional_truthy(
            details.get("AcceptUploadedResumes")
            or details.get("GOVT_AcceptUploadedResumes")
            or source.get("acceptUploadedResumes")
        ),
        "accepts_attached_documents": _optional_truthy(
            details.get("AcceptAttachedDocuments")
            or details.get("GOVT_AcceptAttachedDocuments")
            or source.get("acceptAttachedDocuments")
        ),
        "show_application_count": _optional_truthy(
            details.get("ShowApplicationCount")
            or details.get("GOVT_ShowApplicationCount")
            or source.get("showApplicationCount")
        ),
        "source_field": "application_options",
    }
    if not any(value is not None for key, value in row.items() if key != "source_field"):
        return []
    return [row]


def requirement_rows(value: Any, *, source_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, part in enumerate(_text_items(value)):
        rows.append(
            {
                "requirement_type": "condition",
                "label": _requirement_label(part),
                "description": part,
                "required": True,
                "source_field": source_field,
                "sequence": idx,
            }
        )
    return rows


def qualification_requirement_rows(qualifications: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, part in enumerate(_text_items(qualifications)):
        lower = part.lower()
        if (
            "specialized experience" not in lower
            and "equivalent to" not in lower
            and "to qualify" not in lower
            and "gs-" not in lower
            and "gs " not in lower
        ):
            continue
        rows.append(
            {
                "grade": _grade_from_text(part),
                "requirement_type": "specialized_experience"
                if "specialized experience" in lower
                else "qualification",
                "text": part,
                "source_field": "qualifications",
                "sequence": idx,
            }
        )
    return rows


def text_rows(value: Any, source_field: str) -> list[dict[str, Any]]:
    return [
        {"text": part, "source_field": source_field, "sequence": idx}
        for idx, part in enumerate(_text_items(value))
    ]


def extract_specialized_experience(qualifications: str) -> str | None:
    """Pull the most useful specialized-experience paragraphs when present.

    This is deliberately conservative: it only copies text that is already in
    the announcement, because later scoring must cite evidence, not infer it.
    """
    paragraphs = [
        p.strip()
        for p in re.split(r"(?:\r?\n){2,}|(?<=\.)\s+(?=[A-Z])", qualifications)
        if p.strip()
    ]
    hits = [
        p
        for p in paragraphs
        if re.search(r"specialized experience|equivalent to (?:the )?GS-?\d+", p, re.I)
    ]
    return "\n\n".join(hits) if hits else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _get(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _first(value: Any) -> Mapping[str, Any]:
    if isinstance(value, list) and value:
        return _mapping(value[0])
    return _mapping(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = "\n".join(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</\s*p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _name_or_text(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _text(value.get("Name") or value.get("Code"))
    return _text(value)


def _series(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    return digits.zfill(4) if digits else text


def _float(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _int_value(value: Any) -> int | None:
    text = _text(value)
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    return int(digits)


def _date(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text[:10]


def _salary_type(value: Any) -> str | None:
    text = (_text(value) or "").lower()
    if not text:
        return None
    if "hour" in text or text == "ph":
        return "per_hour"
    if "year" in text or text in {"pa", "per year"}:
        return "per_year"
    if "day" in text:
        return "per_diem"
    return text.replace(" ", "_")


def _remote_status(remote_indicator: Any, telework_eligible: Any) -> str:
    if _truthy(remote_indicator):
        return "remote"
    if _truthy(telework_eligible):
        return "hybrid"
    if remote_indicator is None and telework_eligible is None:
        return "unknown"
    return "onsite"


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "t", "yes", "y", "1"}


def _optional_truthy(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _text_items(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    pieces = re.split(r"(?:\r?\n)+|(?:^|\s)[*-]\s+", text)
    cleaned = [re.sub(r"\s+", " ", piece).strip(" ;") for piece in pieces]
    return [piece for piece in cleaned if len(piece) >= 5]


def _grade_from_text(text: str) -> str | None:
    match = re.search(r"\bGS[-\s]?(\d{1,2})\b", text, flags=re.I)
    return match.group(1).zfill(2) if match else None


def _requirement_label(text: str) -> str:
    lower = text.lower()
    if "citizen" in lower:
        return "Citizenship"
    if "background" in lower or "investigation" in lower:
        return "Background investigation"
    if "drug" in lower:
        return "Drug test"
    if "financial disclosure" in lower:
        return "Financial disclosure"
    if "travel" in lower:
        return "Travel"
    return text[:80]


def _state_from_location(location: Mapping[str, Any]) -> str | None:
    state = _text(
        location.get("CountrySubDivisionCode")
        or location.get("positionLocationState")
        or location.get("State")
    )
    if state is None:
        return None
    if len(state) == 2:
        return state.upper()
    return STATE_NAMES.get(state, state[:2].upper() if len(state) > 2 else state)


def _historic_location_text(location: Mapping[str, Any]) -> str | None:
    parts = [
        _text(location.get("positionLocationCity")),
        _text(location.get("positionLocationState")),
        _text(location.get("positionLocationCountry")),
    ]
    return ", ".join(part for part in parts if part) or None


def _historic_url(control_number: Any) -> str | None:
    control = _text(control_number)
    if control is None:
        return None
    return f"https://www.usajobs.gov/job/{control}"


def _parse_organization_codes(value: Any) -> tuple[str | None, str | None]:
    """Parse the USAJOBS Search `OrganizationCodes` string.

    The Search API returns it as `DEPT/SUBELEMENT` (e.g. `HS/HSCB` for FEMA,
    `VA/VATA` for the Veterans Health Administration). Returns
    ``(department_code, sub_element_code)``; when only one segment is present
    the parser returns it as the sub-element so it can populate `agency_code`.
    """
    text = _text(value)
    if not text:
        return None, None
    parts = [piece.strip() for piece in text.split("/") if piece.strip()]
    if not parts:
        return None, None
    if len(parts) == 1:
        return None, parts[0].upper()
    return parts[0].upper(), parts[-1].upper()
