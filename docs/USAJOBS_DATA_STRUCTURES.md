# USAJOBS Data Structures

This file reconciles three sources:

- Official REST API docs at `developer.usajobs.gov`.
- Local SIF documents in the repo:
  - `opm sif guide v3.0.docx`
  - `data dictionary -all sif schemas.xlsx`
  - `data dictionary -all sif schemas uat.xlsx`
- Observed live API responses saved under `data/raw/`.

## Source-Of-Truth Rule

For API calls, the official REST docs are canonical. The local SIF guide and SIF data dictionaries are useful for understanding field semantics, validation, repeatability, and why the data is shaped the way it is, but they are not the source of truth for REST query parameter names.

Before changing an importer or adding a filter, check the current official API docs first:

- Search: <https://developer.usajobs.gov/api-reference/get-api-search>
- HistoricJoa: <https://developer.usajobs.gov/api-reference/get-api-historicjoa>
- AnnouncementText: <https://developer.usajobs.gov/api-reference/get-api-AnnouncementText>
- Code lists: <https://developer.usajobs.gov/api-reference/>

## Endpoint Roles

| Endpoint | Purpose | Auth | Import strategy |
| --- | --- | --- | --- |
| `/api/Search` | Current live postings | API key required | Current listings and alerts |
| `/api/historicjoa` | Compact current + past posting archive | Public | Main structured historical backbone |
| `/api/historicjoa/announcementtext` | Long-form text for current + past postings | Public | Filtered text import by agency/date/series |

## Canonical Filters

Search and HistoricJoa do **not** use the same agency parameter name.

| Intent | Search API | HistoricJoa / AnnouncementText |
| --- | --- | --- |
| Agency / subelement | `Organization` | `HiringAgencyCodes` |
| Department | no direct equivalent in our current UI | `HiringDepartmentCodes` |
| Occupational series | `JobCategoryCode` | `PositionSeries` |
| Announcement number | `PositionID` / keyword-ish behavior varies | `AnnouncementNumbers` |
| USAJOBS control number | `MatchedObjectId` in response | `USAJOBSControlNumbers` |
| Opening date range | `DatePosted` only for recent current postings | `StartPositionOpenDate`, `EndPositionOpenDate` |
| Closing date range | limited Search sorting/filtering | `StartPositionCloseDate`, `EndPositionCloseDate` |
| Remote | `RemoteIndicator` | no equivalent observed in HistoricJoa filters |

For FEMA:

```text
Search current listings:
  Organization=HSCB

Historic structured records:
  HiringAgencyCodes=HSCB

Announcement text:
  HiringAgencyCodes=HSCB
```

Avoid using `Keyword=FEMA` as the primary way to target FEMA. It is useful for discovery, but it returns false positives because keyword search scans broader announcement text.

## FEMA Live Check

As of the live check on 2026-05-05:

| Query | Result |
| --- | ---: |
| `GET /api/historicjoa?HiringAgencyCodes=HSCB` | `26,479` total FEMA records |
| `GET /api/historicjoa/announcementtext?HiringAgencyCodes=HSCB` | `26,479` total FEMA text records |
| Sample imported locally, `2026-01-01` to `2026-05-05` | `41` historic rows |
| Current Search imported with `Organization=HSCB` / FEMA current rows | `3` current rows |

The earlier `44` FEMA count was not the full history. It was a bounded local sample: `41` historic rows plus `3` current Search rows.

## SIF Dictionary Findings

The SIF data dictionaries are more detailed than the REST API docs in these ways:

- They show many fields as required, conditional, repeating, or unbounded.
- They confirm that locations, occupational series, required documents, and key requirements are often repeated structures, not scalar fields.
- They identify the agency subelement as a four-character `OrganizationID`; this maps well to Search `Organization` and HistoricJoa `HiringAgencyCodes`.
- They make clear that `JobSummary`, `MajorDuties`, `Requirements`, `Evaluations`, `Qualifications`, `RequiredDocuments`, and `HowToApply` are distinct text regions.
- They distinguish announcement identifiers:
  - JOA control number / `DocumentID` / USAJOBS control number.
  - Agency announcement number / `PositionID`.
- They show that `Pay Plan`, `Pay Grade Low`, `Pay Grade High`, salary min/max, salary basis, appointment type, schedule, travel, supervisory status, security clearance, and telework eligibility are structured fields.

Especially useful SIF fields for this app:

| Concept | SIF/schema wording | Current normalized target |
| --- | --- | --- |
| USAJOBS control number | `JOA Control Number`, `DocumentID` | `jobs.usajobs_control_number` |
| Announcement number | `Job Announcement Number`, `PositionID` | `jobs.announcement_number` / `position_id` |
| Agency code | `Hiring Organization Agency Subelement`, `OrganizationID` | future `agency_code`; currently query/filter provenance |
| Title | `PositionTitle` | `jobs.title` |
| Series | `JobCategoryCode`, occupation code | `jobs.series`; future `job_categories` child table |
| Pay plan | `JobGradeCode` | `jobs.pay_plan` |
| Grade range | `GOVT_PayGradeLow`, `GOVT_PayGradeHigh` | `jobs.grade_low`, `jobs.grade_high` |
| Location | `PositionLocation`, `LocationID`, `LocationName` | `jobs.location_text`, `state`, `city`; future `job_locations` child table |
| Telework | `GOVT_TeleworkEligibility` | `jobs.telework_status`, `remote_status` |
| Summary | `JobSummary` | `job_text.summary` |
| Duties | `MajorDuties` | `job_text.duties` |
| Qualifications | `Qualifications` / `requirementsQualifications` | `job_text.qualifications` |
| Requirements | `Requirements` | `job_text.conditions_of_employment` or separate future field |
| Evaluation | `Evaluations` | `job_text.evaluation_criteria` |
| Required docs | `RequiredDocuments`, `RequiredStandardDocuments` | `job_text.required_documents`; future structured documents |

## Database Shape Concerns

The current `jobs` table is intentionally flattened for early UI speed, but the data is more structured than one row can faithfully represent.

Fields that should likely become child tables before the app gets much larger:

| Child table | Why |
| --- | --- |
| `job_locations` | JOAs can have multiple locations; a single `state` distorts maps and filters. Current Search can also provide latitude/longitude for zoomable point maps. |
| `job_categories` | JOAs can include multiple occupational series. |
| `job_hiring_paths` | Hiring paths are repeated and useful for eligibility filtering. |
| `job_required_documents` | Standard document codes and free text should be queryable. |
| `agency_codes` | Agency/subelement codes should drive filters and labels. |
| `code_lists` | Pay plans, schedules, travel, security clearance, location codes, etc. should be populated from official code lists. |
| `job_import_scopes` or richer `saved_searches` | Import scopes should be structured around agency codes, series, grades, dates, and location, not free-text keywords. |

Recommendation: keep the flattened `jobs` table as the searchable summary table, but add child tables for repeated structures. That gives the UI fast scanning while preserving the real shape of the API.

## Parsing Approach

Treat each announcement as a structured document with a summary row plus repeated children:

1. Parse identity first: source endpoint, USAJOBS control number, announcement number, position id, URL, and raw JSON path.
2. Parse agency and classification using codes, not display names, wherever possible.
3. Parse repeated arrays into child records before reducing anything into `jobs`.
4. Populate `jobs` with stable summary values for fast tables and charts.
5. Preserve original text fields in `job_text`, with HTML stripped for display but raw JSON retained for replay.
6. Keep provenance on every import scope so a row can be traced back to exact endpoint params and raw response.
7. Preserve location coordinates when the API provides them. Do not infer street addresses or silently geocode city/state-only records.

Avoid parsing display strings when the API provides structured values. Display strings are still stored, but they should not be the basis for agency filtering, series filtering, or deduplication.

## Filter-First UI Direction

The UI should favor structured filters over generic keyword search:

- Agency code / agency name selector.
- Department code selector.
- Series selector.
- Grade/pay-plan filters.
- Date range filters.
- Location/state/remote filters.
- Work-location point map when latitude/longitude are available, plus a state-count fallback.
- Multi-location postings can appear in each listed location, but the UI must let the user filter them out. Remote-anywhere postings stay separate below the map.
- Hiring path filters.
- Security clearance / travel / supervisory filters.

Keyword search should remain available, but as a secondary "contains text" tool, not the primary way to define an import or dashboard slice.

## Immediate Implementation Implications

1. Initial agency/code lookup tables now exist, seeded with FEMA `HSCB`, DHS `HS`, and priority series. Next step: load the full official code lists.
2. Import forms now favor agency-code/date/series controls. Next step: add grade/pay-plan, location, remote, hiring-path, travel, security-clearance, and supervisory filters.
3. HistoricJoa and AnnouncementText imports use the same filter params so text and structured rows can stay aligned.
4. Schema support now exists for multi-location, multi-series, hiring paths, and required documents.
5. Use SIF dictionaries to guide field semantics, but verify every REST query parameter against the official docs before coding.
