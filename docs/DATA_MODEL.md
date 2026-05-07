# DATA_MODEL.md

SQLite schema for V1. All tables live in `data/federal_jobs.sqlite`. Times are ISO-8601 UTC strings; JSON blobs are stored as `TEXT` and validated at write time.

## Conventions

- Primary keys: `id INTEGER PRIMARY KEY AUTOINCREMENT` unless noted.
- All tables get `imported_at` / `updated_at` columns where data is mutable.
- Dedup key for jobs is `(source, position_id, announcement_number)`; enforced by a UNIQUE index.
- Foreign keys are declared with `ON DELETE CASCADE` for child tables (`job_text`, `match_scores`, `alerts`, `job_notes`, `job_tags`, `saved_jobs`).
- Use `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` at startup.

---

## Tables

Design note: `jobs` is currently a flattened summary table for fast scanning. USAJOBS/SIF data is more structured than this table: locations, series, hiring paths, required documents, and key requirements can repeat. Before broad imports and serious scoring, add child tables for repeated structures while keeping `jobs` as the summary/index table. See `docs/USAJOBS_DATA_STRUCTURES.md`.

### `jobs`

Normalized announcement record (small fields only — long text lives in `job_text`).

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| source | TEXT NOT NULL | `usajobs_search` \| `usajobs_historic` |
| usajobs_control_number | TEXT | USAJOBS control number; primary join key for HistoricJoa AnnouncementText |
| position_id | TEXT | USAJOBS PositionID |
| announcement_number | TEXT | |
| title | TEXT | |
| department | TEXT | |
| agency | TEXT | |
| sub_agency | TEXT | |
| series | TEXT | 4-digit series code, stored as text to preserve leading zeros |
| grade_low | TEXT | |
| grade_high | TEXT | |
| pay_plan | TEXT | GS, ES, etc. |
| salary_min | REAL | |
| salary_max | REAL | |
| salary_type | TEXT | per-year / per-hour / etc. |
| location_text | TEXT | original location string |
| state | TEXT | 2-letter, normalized |
| city | TEXT | |
| remote_status | TEXT | `remote` \| `hybrid` \| `onsite` \| `unknown` |
| telework_status | TEXT | |
| open_date | TEXT | ISO date |
| close_date | TEXT | ISO date |
| hiring_paths | TEXT | JSON array |
| appointment_type | TEXT | |
| work_schedule | TEXT | |
| supervisory_status | TEXT | |
| travel_required | TEXT | |
| security_clearance | TEXT | |
| promotion_potential | TEXT | |
| url | TEXT | link to the JOA on usajobs.gov |
| source_endpoint | TEXT | which API produced this row |
| source_query_hash | TEXT | hash of query params for traceability |
| raw_json_path | TEXT | path under `data/raw/...` |
| imported_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |

Indexes: `(source, position_id, announcement_number)` UNIQUE; `(source, usajobs_control_number)` UNIQUE when present; `(state)`, `(agency)`, `(series)`, `(close_date)`, `(open_date)`.

### Repeated-structure tables

Phase 4.5 introduced these tables before broad imports. They preserve source structure while leaving `jobs` as the fast summary table.

`init_schema()` also backfills these child tables from existing flat `jobs` / `job_text` rows when possible, so older local imports remain usable after migration. Backfilled rows preserve only the summary values that already existed; newly imported rows can preserve multiple locations, series, hiring paths, and required-document records.

#### `agency_codes`

| Column | Type | Notes |
| --- | --- | --- |
| code | TEXT PK | Four-character agency/subelement code; FEMA = `HSCB` |
| name | TEXT | Display name |
| department_code | TEXT | Parent department code; DHS = `HS` |
| department_name | TEXT | |
| active | INTEGER | 0/1 when available |
| source | TEXT | Official code list / observed API / manual seed |
| updated_at | TEXT | |

#### `code_lists`

| Column | Type | Notes |
| --- | --- | --- |
| list_name | TEXT | e.g. `position_schedule`, `pay_plan`, `security_clearance`, `travel_required` |
| code | TEXT | |
| label | TEXT | |
| description | TEXT | |
| source | TEXT | Official USAJOBS code list or SIF dictionary |
| updated_at | TEXT | |

PK: `(list_name, code)`.

#### `job_locations`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| location_text | TEXT | Original location display |
| city | TEXT | |
| state | TEXT | Two-letter postal code when parseable |
| country | TEXT | |
| location_code | TEXT | USAJOBS/SIF location code when provided |
| latitude | REAL | Work-location latitude when provided by the API |
| longitude | REAL | Work-location longitude when provided by the API |
| remote_indicator | TEXT | remote / hybrid / onsite / unknown when derivable |

USAJOBS Search can include coordinate-level location data. HistoricJoa commonly provides city/state/country without coordinates. The app stores coordinates when present and otherwise keeps city/state data for state-level maps and filters. Do not invent coordinates or geocode addresses silently. Current postings without mappable coordinates remain reviewable in a zoom-scoped table on the map page.

#### `job_categories`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK -> jobs.id | |
| series | TEXT | 4-digit occupational series |
| name | TEXT | Series label when available |
| is_primary | INTEGER | 0/1 summary row indicator |

PK: `(job_id, series)`.

#### `job_hiring_paths`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK -> jobs.id | |
| code | TEXT | USAJOBS hiring path code |
| label | TEXT | Display label when available |

PK: `(job_id, code)`.

#### `job_required_documents`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| code | TEXT | Standard document code when present |
| label | TEXT | Display label |
| description | TEXT | Free text / instructions |
| required | INTEGER | 0/1/null when unknown |

#### `job_import_scopes`

Structured import/search scopes shared by Search, HistoricJoa, and AnnouncementText.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| name | TEXT | User/display label |
| source | TEXT | Import source |
| endpoint | TEXT | API endpoint |
| download_mode | TEXT | Download mode used |
| agency_codes | TEXT | Comma/semicolon-delimited codes for now |
| department_codes | TEXT | |
| series | TEXT | |
| grade_low | TEXT | |
| grade_high | TEXT | |
| pay_plan | TEXT | |
| location_query | TEXT | |
| state | TEXT | |
| remote_status | TEXT | |
| hiring_paths | TEXT | |
| start_open_date / end_open_date | TEXT | ISO dates |
| start_close_date / end_close_date | TEXT | ISO dates |
| query_params_json | TEXT | Original API params |

#### `job_grades`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK -> jobs.id | |
| pay_plan | TEXT | GS, WG, etc. |
| grade_low | TEXT | |
| grade_high | TEXT | |
| promotion_potential | TEXT | |
| is_primary | INTEGER | 0/1 |

#### `job_salary_ranges`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| minimum | REAL | |
| maximum | REAL | |
| salary_type | TEXT | per_year, per_hour, etc. |
| currency | TEXT | Usually USD |
| location_text | TEXT | Location/locality hint when provided |
| is_primary | INTEGER | 0/1 |

#### `job_requirements`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| requirement_type | TEXT | condition, standard requirement, etc. |
| code | TEXT | Official code when present |
| label | TEXT | Short display label |
| description | TEXT | Evidence text copied from announcement |
| required | INTEGER | 0/1/null |
| source_field | TEXT | Where this came from |
| sequence | INTEGER | Source order |

#### `job_qualification_requirements`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| grade | TEXT | Parsed GS grade when present |
| requirement_type | TEXT | specialized_experience / qualification |
| text | TEXT | Evidence text copied from announcement |
| source_field | TEXT | qualifications / specialized_experience |
| sequence | INTEGER | Source order |

#### `job_duties`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| duty_text | TEXT | Evidence text copied from announcement |
| sequence | INTEGER | Source order |
| source_field | TEXT | Usually duties |

#### `job_evaluation_factors`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| factor_text | TEXT | Evidence text copied from announcement |
| sequence | INTEGER | Source order |
| source_field | TEXT | Usually evaluation_criteria |

#### `job_openings`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| location_text | TEXT | Location tied to the vacancy count when provided |
| openings | INTEGER | Location-level openings |
| total_openings | INTEGER | JOA-level openings |
| source_field | TEXT | Source field/path hint |

#### `job_contacts`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| contact_type | TEXT | public/internal/external when known |
| name | TEXT | |
| email | TEXT | |
| phone | TEXT | |
| url | TEXT | |
| source_field | TEXT | Source field/path hint |

#### `job_security_clearances`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK -> jobs.id | PK |
| clearance | TEXT | Clearance requirement |
| position_sensitivity | TEXT | Sensitivity level when provided |
| adjudication_type | TEXT | Adjudication type when provided |
| source_field | TEXT | Source field/path hint |

#### `job_travel_requirements`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK -> jobs.id | PK |
| travel_required | TEXT | Travel requirement label/code |
| travel_percentage | TEXT | Percent/range when provided |
| source_field | TEXT | Source field/path hint |

#### `job_application_options`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK -> jobs.id | PK |
| apply_online_url | TEXT | Apply URL when provided |
| disable_apply_online | INTEGER | 0/1/null |
| accepts_uploaded_resumes | INTEGER | 0/1/null |
| accepts_attached_documents | INTEGER | 0/1/null |
| show_application_count | INTEGER | 0/1/null |
| source_field | TEXT | Source field/path hint |

### `job_text`

Long-form fields. Separated so we can lazy-import only for high-value jobs.

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK → jobs.id | PK |
| summary | TEXT | Top-of-announcement overview / "what this job is" text |
| duties | TEXT | |
| qualifications | TEXT | Full qualifications text, including grade-equivalency language such as "one year equivalent to GS-12" |
| specialized_experience | TEXT | Extracted/duplicated specialized-experience requirements when parseable |
| education | TEXT | |
| required_documents | TEXT | |
| how_to_apply | TEXT | |
| evaluation_criteria | TEXT | |
| conditions_of_employment | TEXT | |
| raw_text | TEXT | full concatenated text for future RAG |
| raw_json_path | TEXT | |
| imported_at | TEXT NOT NULL | |

### `saved_jobs`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK → jobs.id | PK |
| status | TEXT NOT NULL | enum: New \| Interested \| Maybe \| Applied \| Referred \| Interview \| Selected \| Not selected \| Skip \| Archived |
| priority | INTEGER | 1–5 |
| saved_at | TEXT NOT NULL | |
| last_reviewed_at | TEXT | |

### `applications`

Local application tracker records. These are tracking-only; the app never submits applications or signs into USAJOBS.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | Unique; one current tracker row per posting |
| application_status | TEXT | Draft, Submitted, Referred, Interview, Selected, Not selected, Withdrawn, Archived |
| resume_version | TEXT | User-entered resume/package version label |
| usajobs_application_id | TEXT | USAJOBS or agency reference identifier |
| application_url | TEXT | User-entered application/status URL |
| submitted_at | TEXT | ISO date |
| referred_at | TEXT | ISO date |
| interview_at | TEXT | ISO date |
| outcome | TEXT | Final or interim outcome text |
| next_action | TEXT | User-entered next step |
| next_action_due | TEXT | ISO date |
| contact_name / contact_email | TEXT | Optional HR/contact details |
| notes | TEXT | Local notes |
| created_at / updated_at | TEXT | |

### `application_events`

Timestamped history for application activity.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| application_id | INTEGER FK -> applications.id | |
| event_type | TEXT | e.g. Submitted, Referred, Interview, note |
| event_date | TEXT | ISO date when known |
| notes | TEXT | Local event note |
| created_at | TEXT | |

### `resume_versions`

Local résumé-version library. Stores labels and file metadata only; no résumé contents are parsed or copied into the database.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| label | TEXT | Unique user-facing version label |
| file_name | TEXT | Filename as stored locally |
| file_path | TEXT | Optional local path reference |
| version_date | TEXT | ISO date or user-entered date label |
| target_series | TEXT | Optional target series/scope |
| target_grade | TEXT | Optional target grade/scope |
| notes | TEXT | Local notes about positioning/use |
| active | INTEGER | 1 active, 0 archived |
| created_at / updated_at | TEXT | |

### `job_feedback`

Explicit user preference signals. Short explanations are first-class because they are useful for later review and recommendation tuning.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | |
| feedback_type | TEXT | `liked` \| `disliked` \| `more_like_this` \| `less_like_this` |
| explanation | TEXT | Short user-entered reason |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |

### `recommendation_runs`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| run_type | TEXT | e.g. `similar_jobs` |
| seed_job_id | INTEGER FK -> jobs.id | Optional seed job |
| params_json | TEXT | Filter/scope used |
| created_at | TEXT NOT NULL | |

### `job_recommendations`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| run_id | INTEGER FK -> recommendation_runs.id | |
| job_id | INTEGER FK -> jobs.id | Suggested job |
| score | INTEGER | Similarity/recommendation score |
| explanation | TEXT | Short summary |
| factors_json | TEXT | Exact shared fields/text signals/feedback patterns |
| dismissed | INTEGER | 0/1 |
| created_at | TEXT NOT NULL | |

### `repost_runs`

One row per manual repost-detection run.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| started_at / completed_at | TEXT | Run timing |
| groups_created | INTEGER | Number of detected repost groups |
| members_created | INTEGER | Number of group-member rows |
| params_json | TEXT | Detector thresholds/algorithm metadata |
| notes | TEXT | Run summary |

### `repost_groups`

Detected possible repost clusters. A group is evidence for review, not proof that the postings are administratively identical.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| run_id | INTEGER FK -> repost_runs.id | |
| group_signature | TEXT | Stable-ish signature from agency/series/normalized titles |
| group_title | TEXT | Representative title |
| agency_key / series_key | TEXT | Blocking keys used by the detector |
| member_count | INTEGER | Number of postings in group |
| confidence_score | REAL | Average pairwise title similarity |
| evidence_json | TEXT | Member IDs, controls, titles, text hashes, dates, algorithm evidence |
| created_at | TEXT | |

### `repost_group_members`

Posting membership rows for repost groups.

| Column | Type | Notes |
| --- | --- | --- |
| group_id | INTEGER FK -> repost_groups.id | |
| job_id | INTEGER FK -> jobs.id | |
| role | TEXT | `original` for earliest observed member, `possible_repost` for later members |
| title_similarity | REAL | Similarity to the group's baseline/original title |
| text_hash | TEXT | SHA-1 hash of normalized long-form text when enough text exists |
| created_at | TEXT | |

### `job_notes`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK → jobs.id | |
| note | TEXT NOT NULL | |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |

### `job_tags`

| Column | Type | Notes |
| --- | --- | --- |
| job_id | INTEGER FK → jobs.id | |
| tag | TEXT NOT NULL | |

PK: `(job_id, tag)`.

### `saved_searches`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| name | TEXT NOT NULL | |
| query_params_json | TEXT NOT NULL | |
| alert_enabled | INTEGER | 0/1 |
| alert_frequency | TEXT | `manual` \| `on_open` |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | |

### `match_scores`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK → jobs.id | |
| score | INTEGER NOT NULL | 0–100 |
| explanation | TEXT | |
| positive_factors_json | TEXT | JSON array |
| negative_factors_json | TEXT | JSON array |
| missing_info_json | TEXT | JSON array |
| scoring_version | TEXT NOT NULL | e.g. `v1.0` |
| created_at | TEXT NOT NULL | |

A job can have multiple rows over time (one per scoring version). Latest row wins in the UI.

### `alerts`

Local in-app alerts. V1 alerts are manual/in-app only: no email, push, or background scheduler.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| job_id | INTEGER FK -> jobs.id | Nullable for future non-job alerts |
| alert_type | TEXT NOT NULL | `saved_search_match` \| `high_score` \| `closing_soon` \| `reposted` |
| severity | TEXT NOT NULL | `high` \| `medium` \| `low` \| `info` |
| title | TEXT NOT NULL | Short UI title |
| message | TEXT | Human-readable alert message |
| details_json | TEXT NOT NULL | JSON evidence: matched filters, score, close date, duplicate counts, etc. |
| source_search_id | INTEGER FK -> saved_searches.id | Present for saved-search alerts |
| dedupe_key | TEXT NOT NULL | Stable key used with `alert_type` to avoid duplicate alerts |
| status | TEXT NOT NULL | `new` \| `dismissed` |
| created_at | TEXT NOT NULL | |
| dismissed_at | TEXT | |

Unique: `(alert_type, dedupe_key)`.

### `alert_runs`

Audit table for each manual alert generation run.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| started_at | TEXT NOT NULL | |
| completed_at | TEXT | |
| alerts_created | INTEGER | Number of inserted, non-duplicate alerts |
| notes | TEXT | Candidate count or run note |

### `raw_api_responses`

Audit log for every API call. Lets us replay or debug without re-hitting the API.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| source | TEXT NOT NULL | `usajobs_search` \| `usajobs_historic` \| `usajobs_announcement_text` \| `opm` |
| endpoint | TEXT NOT NULL | URL path |
| query_params_json | TEXT NOT NULL | |
| response_path | TEXT | path under `data/raw/...` |
| status_code | INTEGER | |
| record_count | INTEGER | |
| page_number | INTEGER | |
| request_time | TEXT NOT NULL | ISO timestamp |
| error_message | TEXT | |

### `import_manifests`

Tracks resumable batch imports.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| source | TEXT NOT NULL | |
| endpoint | TEXT NOT NULL | |
| download_mode | TEXT NOT NULL | FULL_DOWNLOAD \| FOCUSED_FULL_DOWNLOAD \| STAGED_DOWNLOAD \| SAMPLE_ONLY |
| date_range_start | TEXT | |
| date_range_end | TEXT | |
| filters_json | TEXT | |
| estimated_records | INTEGER | |
| actual_records | INTEGER | |
| pages_requested | INTEGER | |
| pages_completed | INTEGER | |
| status | TEXT NOT NULL | running \| paused \| failed \| completed |
| started_at | TEXT NOT NULL | |
| completed_at | TEXT | |
| notes | TEXT | |

### `opm_workforce_records`

Normalized rows imported from downloaded OPM/FedScope files by `src/opm_data.py`. The importer accepts CSV, TSV, Excel, and ZIP files and maps common source column names into this compact schema.

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| dataset | TEXT | e.g. `fedscope_employment` |
| period_year | INTEGER | |
| period_quarter | INTEGER | |
| agency | TEXT | |
| sub_agency | TEXT | |
| occupation_series | TEXT | |
| grade | TEXT | |
| pay_plan | TEXT | |
| location_state | TEXT | |
| location_metro | TEXT | |
| employment_count | INTEGER | |
| accessions_count | INTEGER | |
| separations_count | INTEGER | |
| salary_avg | REAL | |
| raw_row_path | TEXT | |
| imported_at | TEXT | |

This table is **never joined** to `jobs` without a clearly-labeled chart/footnote that explains postings ≠ hires.

---

## Migrations

V1 ships with a single `init_schema()` function in `src/database.py` that creates everything if absent. No Alembic in V1. When the schema changes, bump a `schema_version` row in a `meta` table and write an idempotent migration.

## Privacy / sensitive data

The DB stores only public USAJOBS / OPM data plus the user's local notes and tags. No résumé content lives in V1. Résumé text enters in V3 and is stored locally only.
