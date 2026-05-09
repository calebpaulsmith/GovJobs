# Schema Expansion Plan

This file lists the ancillary tables we have, the tables we probably need, and the tables we should avoid unless a real app feature needs them.

## Current Ancillary Tables

These already exist in SQLite.

| Table | Status | Why it exists |
| --- | --- | --- |
| `agency_codes` | Exists | Agency/subelement codes should drive imports and filters. FEMA is `HSCB`; DHS is `HS`. |
| `code_lists` | Exists | Shared lookup table for pay plans, schedules, travel, clearance, series labels, hiring paths, etc. Currently seeded lightly; needs full official-code loading. |
| `job_locations` | Exists | JOAs can list multiple locations; one `jobs.state` is not enough for maps or location filters. |
| `job_categories` | Exists | JOAs can list multiple occupational series. |
| `job_hiring_paths` | Exists | Hiring paths repeat and are useful for eligibility filtering. |
| `job_required_documents` | Exists | Required documents need to be queryable for application planning. |

## Needed Next

These should be implemented before a broad historical import or serious scoring.

| Table | Priority | Necessary? | Why |
| --- | --- | --- | --- |
| `job_grades` | Implemented | Yes | Grade/pay-plan ranges are central to GS-13/14/15 targeting. The flat row has `pay_plan`, `grade_low`, `grade_high`, but a child table lets us preserve multiple grade/pay structures and query exact ladders. |
| `job_salary_ranges` | Implemented | Yes | Salary min/max, basis, locality hints, and location-specific salary can vary. Useful for salary filters, remote/locality comparison, and later locality normalization. |
| `job_telework_remote` | High | Maybe separate | Remote, telework, and location are related but not identical. This can stay on `jobs` plus `job_locations` for now, but a separate table becomes useful if the API exposes multiple remote/telework qualifiers per JOA. |
| `job_requirements` | Implemented | Yes | Conditions of employment and key/standard requirements are repeated and filter-worthy: citizenship, background check, drug test, financial disclosure, probation, travel card, etc. |
| `job_qualification_requirements` | Implemented | Yes | The app needs grade-equivalency and specialized-experience text. `job_text.qualifications` stores the blob; this table stores parsed evidence snippets by grade/requirement type. |
| `job_duties` | Implemented | Yes | Duties are often repeated bullets. Useful for scoring and future resume/application strategy, especially separating grants, mitigation, recovery, policy, supervisory, and field-response duties. |
| `job_evaluation_factors` | Implemented | Yes | Evaluation criteria can signal what to emphasize in a resume. It starts as parsed bullets from `job_text.evaluation_criteria`. |
| `job_standard_documents` | Medium | Already partly covered | We have `job_required_documents`; improve it to distinguish official standard-document code, free-text requirement, and optional/required status. |
| `job_contacts` | Implemented | Yes for apply workflow | HR/contact fields are not core for scoring, but are useful once saved jobs/application tracking matters. |
| `job_openings` | Implemented | Yes | Number of vacancies/openings affects opportunity value and should be queryable when available. |
| `job_security_clearances` | Implemented | Maybe | Security clearance is currently scalar. A child table is useful if we want code-list labels, clearance level, position sensitivity, and adjudication type separately. |
| `job_travel_requirements` | Implemented | Maybe | Travel percentage is a structured code and matters to user preference. |
| `job_application_options` | Implemented | Maybe | Apply-online disabled, uploaded resumes accepted, attached documents accepted, application count shown. Useful for admin/debug and later application UX, not scoring. |
| `job_media` | Low | Maybe | Video URLs repeat in SIF. Not important for matching or analytics. Store only if observed in useful records. |
| `job_cyber_work_roles` | Low | Probably not for this app | Repeated cyber roles are structured, but likely irrelevant unless targeting cyber jobs. |
| `job_mission_critical_codes` | Low | Maybe later | Could help agency workforce analysis, but not central to current FEMA/DHS job targeting. |
| `job_bargaining_unit` | Low | Maybe | Relevant to job conditions, not core career-intel scoring. Keep scalar/code-list until needed. |
| `job_relocation` | Low | Maybe | Relocation assistance is useful but can likely remain scalar unless used in filters. |
| `job_financial_disclosure` | Low | Maybe | Useful as a condition flag; can be part of `job_requirements` instead of its own table. |
| `job_import_scopes` | Implemented | Yes | Saved/import scopes are structured around agency codes, department codes, series, grade, date, location, remote, and other filters. `saved_searches` stores JSON, but a real table makes reuse and auditing cleaner. |

## Probably Not Needed

These appear in SIF but do not support the current app tasks enough to deserve first-class tables.

| Concept | Why not first-class yet |
| --- | --- |
| SIF transaction metadata (`CreationDateTime`, `BODID`, action expressions) | Useful for agency-to-USAJOBS transaction integrity, not for analyzing posted jobs. Raw JSON already preserves provenance. |
| Posting requestor/internal/external contact communication channels | Too admin-heavy for V1. If needed, fold useful public contact data into `job_contacts`. |
| Cancel/acknowledge/change transaction tables | We consume public Search/HistoricJoa snapshots, not agency transaction feeds. |
| Candidate/resume/document SIF schemas | Out of scope unless the app becomes an applicant-tracking/document-management tool. |
| Vendor IDs and TAS integration fields | Not useful for the user's career filtering, scoring, or analytics. |
| Full HTML announcement rendering structure | Raw JSON and normalized `job_text` are enough; preserve source text, do not rebuild the USAJOBS page. |

## Recommended Implementation Order

1. Done: `job_import_scopes`, one scope object shared by Search, HistoricJoa, and AnnouncementText.
2. Done: `job_grades` and `job_salary_ranges`, making grade/pay/salary filters honest.
3. Done: `job_requirements`, structured conditions of employment and standard requirements.
4. Done: `job_qualification_requirements`, parsed grade-equivalency and specialized-experience snippets.
5. Done: `job_duties` and `job_evaluation_factors`, scoring/application strategy evidence.
6. Next: improve `job_required_documents` into standard-code plus free-text rows.
7. Done: add `job_contacts`, `job_openings`, `job_security_clearances`, `job_travel_requirements`, and `job_application_options`.
8. Next: scalar/code-list refinements for relocation, financial disclosure, bargaining unit, and full official code-list sync if observed data quality supports it.
9. Done: Public-map D.5.4 added `zip_centroids` (ZCTA/ZIP → lat/lon/county_fips). Repeats per ZIP, code-list backed, used for offline geocoding and FRPP county joins. Default source: Census ZCTA Gazetteer; SimpleMaps US ZIPs can be used as an override when city/state/county labels are needed.
10. Public-map D.5: add `federal_properties` (one row per GSA-reported asset). Repeats per locality, joins to `agency_codes` and `counties`, drives the federal-properties layer and agency-aware filtering. Source: GSA FRPP. Tracked under `data_source_status.gsa_frpp` per ADR-0018.

## Design Rule

Do not create one table for every SIF field. Create a table when at least one of these is true:

- The field repeats per job.
- The field needs code-list labels or official code validation.
- The UI should filter/group by it.
- Scoring or application strategy needs citation-grade evidence from it.
- It cannot be safely represented as one scalar on `jobs`.
