# FIELD_DICTIONARY.md

Definitions for every normalized field the app stores. When in doubt, this is the source of truth — not the API docs and not the column comments in the SQL DDL.

---

## Identity

| Field | Definition |
| --- | --- |
| `source` | Which API the row came from. Allowed: `usajobs_search`, `usajobs_historic`, `usajobs_announcement_text`, `opm`. |
| `usajobs_control_number` | USAJOBS control number. Used to connect compact HistoricJoa rows to long-form AnnouncementText rows. |
| `position_id` | USAJOBS PositionID. Stable per JOA. |
| `announcement_number` | The announcement number (sometimes called control number). Combined with `position_id` and `source`, forms the dedup key. |
| `agency_code` | Four-character agency/subelement code used for structured filtering. FEMA is `HSCB`. Search uses `Organization`; HistoricJoa and AnnouncementText use `HiringAgencyCodes`. |
| `department_code` | Parent department code used for broader structured filtering. DHS is `HS`; HistoricJoa and AnnouncementText use `HiringDepartmentCodes`. |

## Job basics

| Field | Definition |
| --- | --- |
| `title` | Job title as posted. Stored verbatim. |
| `department` | Cabinet-level department, e.g. `Department of Homeland Security`. |
| `agency` | Sub-cabinet agency, e.g. `FEMA`. |
| `sub_agency` | Office within the agency, when present. |

## Classification

| Field | Definition |
| --- | --- |
| `series` | 4-digit OPM occupational series code. **Stored as text** to preserve leading zeros (e.g. `0089`, not `89`). |
| `grade_low` | Lowest GS / equivalent grade announced. |
| `grade_high` | Highest GS / equivalent grade announced. |
| `pay_plan` | Pay-plan code, e.g. `GS`, `ES`, `WG`, `IT`. |
| `promotion_potential` | Highest grade reachable from this position without competition. |

Occupational series can repeat on some JOAs. The `job_categories` child table preserves every parsed series while `jobs.series` remains the summary/index value.

## Compensation

| Field | Definition |
| --- | --- |
| `salary_min` | Minimum advertised salary, base, in USD (`REAL`). |
| `salary_max` | Maximum advertised salary, base, in USD (`REAL`). |
| `salary_type` | Period: `per_year`, `per_hour`, `per_diem`, `flat`. |

## Location

| Field | Definition |
| --- | --- |
| `location_text` | Original location string. |
| `state` | Two-letter US state postal code (`IL`, `DC`, …). `null` for foreign or unknown. |
| `city` | Normalized city name; `null` if not parseable. |
| `remote_status` | One of: `remote` (anywhere), `hybrid`, `onsite`, `unknown`. |
| `telework_status` | The free-text telework string from the JOA, untransformed. |

A JOA may list multiple cities and states. In V1 we store a representative `state` for the row plus the original `location_text`. Multi-location handling for the map is described in `docs/PRODUCT_SPEC.md` §State map.

SIF and observed REST data both show location as a repeated structure. The `job_locations` child table preserves every parsed location for filtering, maps, remote/hybrid handling, and regional analytics.

## Schedule and tenure

| Field | Definition |
| --- | --- |
| `appointment_type` | e.g. permanent, term, temporary, intermittent. |
| `work_schedule` | Full-time / part-time / job share / etc. |
| `supervisory_status` | Yes / No / Unknown. |
| `travel_required` | Free text from JOA. |
| `security_clearance` | Free text from JOA. |
| `hiring_paths` | JSON array of USAJOBS hiring-path codes (public, status, vet, etc.). |

Hiring paths are also repeated structures. The `job_hiring_paths` child table supports eligibility filtering without parsing a JSON blob in the UI.

## Dates

| Field | Definition |
| --- | --- |
| `open_date` | Posting open date (ISO `YYYY-MM-DD`). |
| `close_date` | Posting close date. May be empty for open-continuous postings. |
| `imported_at` | UTC ISO-8601 timestamp the row was first written. |
| `updated_at` | UTC ISO-8601 timestamp of the last upsert. |

## Provenance

| Field | Definition |
| --- | --- |
| `url` | Public USAJOBS link to the JOA. |
| `source_endpoint` | Specific URL path, e.g. `/api/Search`. |
| `source_query_hash` | Hex digest of the request params; lets us trace which query produced the row. |
| `raw_json_path` | Relative path under `data/raw/...` to the JSON file containing this record. |

---

## Long-form text (`job_text`)

| Field | Definition |
| --- | --- |
| `summary` | The top-of-announcement description of what the job is. From AnnouncementText `summary` or Search `UserArea.Details.JobSummary`. |
| `duties` | "Duties" section. |
| `qualifications` | Full "Qualifications" section, including grade-equivalency language such as "must have one year equivalent to GS-12 for this GS-13 position." |
| `specialized_experience` | Specialized-experience requirement text when parseable. Often the most useful field for matching. |
| `education` | Education requirements. |
| `required_documents` | Documents the applicant must submit. |
| `how_to_apply` | Application instructions. |
| `evaluation_criteria` | Evaluation / "How you will be evaluated". |
| `conditions_of_employment` | Conditions section. |
| `raw_text` | Concatenation of the above; convenient for V3 embeddings. |

---

## Parsed evidence child tables

These tables copy evidence out of structured fields and long-form announcement text. They do not infer user qualifications; they preserve announcement language in smaller, queryable pieces.

| Table | Definition |
| --- | --- |
| `job_grades` | Pay plan, low grade, high grade, and promotion potential rows. Used for GS-13/14/15 filters and ladder analysis. |
| `job_salary_ranges` | Salary min/max, salary basis, currency, and locality/location hint rows. |
| `job_requirements` | Conditions of employment and standard requirement rows, such as citizenship, background investigation, drug testing, travel, or financial disclosure. |
| `job_qualification_requirements` | Qualifications and specialized-experience evidence snippets, including parsed GS grade references when present. |
| `job_duties` | Duty bullets or paragraphs copied from the announcement. |
| `job_evaluation_factors` | Evaluation / category-rating / assessment factor bullets or paragraphs copied from the announcement. |
| `job_openings` | Vacancy/opening counts, including location-level and total-opening counts when provided. |
| `job_contacts` | Public contact name/email/phone/url rows when available. |
| `job_security_clearances` | Clearance, position sensitivity, and adjudication fields. |
| `job_travel_requirements` | Travel requirement and travel-percentage fields. |
| `job_application_options` | Apply URL and application-option flags such as uploaded-resume/document acceptance. |

---

## Match scoring (`match_scores`)

| Field | Definition |
| --- | --- |
| `score` | Integer 0–100. Deterministic from the rule weights and the job fields. |
| `explanation` | One-paragraph human-readable explanation. |
| `positive_factors_json` | JSON array of `{factor, weight, evidence}`. |
| `negative_factors_json` | JSON array of `{factor, weight, evidence}`. |
| `missing_info_json` | JSON array of fields the score could have used but were missing. |
| `scoring_version` | Semantic version of the rules (e.g. `v1.0`). |

---

## Local alerts (`alerts`, `alert_runs`)

| Field | Definition |
| --- | --- |
| `alerts.alert_type` | Trigger category: `saved_search_match`, `high_score`, `closing_soon`, or `reposted`. |
| `alerts.severity` | UI priority: `high`, `medium`, `low`, or `info`. |
| `alerts.details_json` | Machine-readable evidence behind the alert. Saved-search alerts include matched filter fields; high-score alerts include score/scoring version; closing-soon alerts include close date and days remaining; repost alerts include duplicate counts and identifiers. |
| `alerts.dedupe_key` | Stable key paired with `alert_type` to prevent repeat alerts across manual runs. |
| `alerts.status` | `new` or `dismissed`. Dismissed alerts stay in the database for audit/history. |
| `alert_runs` | One row per manual alert-generation run, with timestamps and inserted-alert count. |

V1 alerts are local and manually generated from the app. They do not send email or push notifications.

---

## Preference feedback and recommendations

| Field / table | Definition |
| --- | --- |
| `job_feedback.feedback_type` | User preference signal: `liked`, `disliked`, `more_like_this`, or `less_like_this`. |
| `job_feedback.explanation` | Short user-entered reason for the feedback. Used for later review and future recommendation tuning. |
| `recommendation_runs` | A generated set of similar-job suggestions, optionally tied to a seed job. |
| `job_recommendations.score` | Deterministic similarity/recommendation score. Separate from `match_scores.score`. |
| `job_recommendations.explanation` | Short explanation of why the job was suggested. |
| `job_recommendations.factors_json` | Exact structured fields, text signals, and feedback patterns behind the suggestion; powers the "why suggested" view. |

Every recommendation must be inspectable. Do not show a suggested job without a user-visible explanation path.

---

## Application status (`saved_jobs.status`)

Allowed enum values, in suggested order:

`New` → `Interested` → `Maybe` → `Applied` → `Referred` → `Interview` → `Selected` / `Not selected` → `Skip` → `Archived`.

---

## Tags (`job_tags.tag`)

Free text. Conventions:

- Lowercase, kebab-case (`fema-region-5`, `policy-shop`).
- One concept per tag.
- Use a `goal:` prefix for personal-goal tags (`goal:gs14-this-year`).

---

## OPM fields

OPM datasets vary. `src/opm_data.py` imports downloaded CSV, TSV, Excel, or ZIP files and normalizes common FedScope/data.opm.gov column names into `opm_workforce_records`.

| Field | Definition |
| --- | --- |
| `dataset` | Local dataset label supplied during import, such as `fedscope_employment`, `accessions`, or `separations`. |
| `period_year` / `period_quarter` | Reporting year and quarter parsed from common year/period/quarter columns. |
| `agency` / `sub_agency` | OPM agency and sub-agency/bureau labels as provided in the file. |
| `occupation_series` | Occupational series, stored as four-character text when numeric. |
| `grade` / `pay_plan` | Workforce grade and pay-plan fields when available. |
| `location_state` / `location_metro` | State and metro/duty-station location fields. State is normalized to a two-letter postal code when possible. |
| `employment_count` | OPM workforce/headcount value. This is not a USAJOBS posting count. |
| `accessions_count` | OPM accession/new-hire count. This is a hire/workforce movement metric, not a posting count. |
| `separations_count` | OPM separation count. |
| `salary_avg` | Average salary/compensation value when provided. |
| `raw_row_path` | Source file plus row marker for audit/debug. |

When OPM names diverge from USAJOBS names, the UI labels OPM data as workforce/accessions/separations and does not present it as posting activity.
