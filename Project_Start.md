# Project_Start.md

# Federal Jobs Intelligence Dashboard — Project Start Instructions

## Purpose

Build a local-first USAJOBS and federal workforce intelligence dashboard that helps me:

1. Search current USAJOBS postings.
2. Download and archive historical USAJOBS postings.
3. Analyze historical federal hiring/posting trends.
4. Map federal job activity by state and location.
5. Filter jobs by salary, grade, agency, series, location, remote status, and keywords.
6. Create alerts for jobs that match my criteria.
7. Score jobs against my resume and career goals.
8. Build a RAG/vector-search layer for semantic job matching and resume-to-announcement analysis.
9. Produce dashboards, scorecards, trend graphs, and exports.

This should start as a local app that a non-coder can run, inspect, and improve with Claude Code or Codex.

The first priority is a working, reliable dashboard and data pipeline. The AI/RAG layer should come after the data collection, database, filters, and basic charts work.

---

## Important Product Framing

This app should distinguish between:

- **USAJOBS posting data**: what jobs were announced or advertised.
- **OPM workforce data**: what federal employment, accessions, separations, and workforce composition actually looked like.

Posting volume is not the same as hiring volume. A job announcement may not lead to a hire, may cover multiple vacancies, may be a standing register, or may be reposted.

The app should be careful with terms:

- Use “postings” or “announcements” when analyzing USAJOBS data.
- Use “hires,” “accessions,” “separations,” or “workforce counts” only when analyzing OPM workforce data.
- Maps and trend charts should clearly label the data source.

---

## Current Official Data Sources to Use

Use official federal data sources first.

### USAJOBS APIs

Use the USAJOBS developer APIs for current and historical federal job announcement data.

Core APIs to investigate and use:

1. **Search API**
   - Current open job announcements.
   - Requires USAJOBS API credentials.
   - Lightweight JOA content.
   - Supports paging.
   - Use for current job search and alerts.

2. **Historic JOAs API**
   - Historical and current job announcement records.
   - Intended for bulk historical data consumption.
   - Smaller structured fields.
   - Use for historical trend analysis.

3. **Announcement Text API**
   - Long text fields for current and past postings.
   - Use for duties, qualifications, specialized experience, and future RAG/vector search.

Relevant documentation:
- https://developer.usajobs.gov/api-reference/
- https://developer.usajobs.gov/api-reference/get-api-search
- https://developer.usajobs.gov/API-Reference/GET-api-HistoricJoa
- https://developer.usajobs.gov/api-reference/get-api-AnnouncementText
- https://developer.usajobs.gov/guides/rate-limiting

### OPM Federal Workforce Data

Use OPM Federal Workforce Data for actual workforce data, accessions, separations, and workforce composition.

Relevant pages:
- https://data.opm.gov/
- https://data.opm.gov/explore-data/data/data-downloads
- https://data.opm.gov/info-and-help/getting-started
- https://www.opm.gov/policy-data-oversight/data-analysis-documentation/fedscope/

OPM data should support analysis of:

- Federal employment by agency, occupation, location, grade, pay plan, and time.
- Accessions/new hires.
- Separations.
- Compensation.
- Location trends.
- Workforce composition.

---

## Key Requirement: Download the Entire Dataset Unless It Is Huge

The project should try to download the complete relevant dataset, but only after estimating size, paging limits, runtime, and storage impact.

### Define “Huge”

Treat a dataset as “huge” if any of the following are true:

- Estimated raw download size is greater than 5 GB.
- Estimated processed database size is greater than 10 GB.
- Estimated row count is greater than 5 million rows.
- Full import would take more than 8 hours on a normal laptop.
- API limits make a full import impractical without long-running batch jobs.
- The data includes long text fields that would greatly exceed local storage or embedding costs.

These thresholds should be configurable in `config.py`.

### Required Download Strategy

Before downloading everything, the app must run a **dataset reconnaissance step**.

The reconnaissance step should:

1. Query available date ranges.
2. Estimate record counts by year or month.
3. Estimate pages required.
4. Estimate raw JSON size.
5. Estimate processed SQLite size.
6. Identify API row limits, page limits, and rate limits.
7. Recommend one of these modes:
   - `FULL_DOWNLOAD`
   - `FOCUSED_FULL_DOWNLOAD`
   - `STAGED_DOWNLOAD`
   - `SAMPLE_ONLY`

### Download Modes

#### FULL_DOWNLOAD

Use when the entire dataset appears manageable.

Download all available records for the relevant API, using safe pagination, retry logic, checkpoints, and deduplication.

#### FOCUSED_FULL_DOWNLOAD

Use when the entire federal dataset is too large, but a complete focused dataset is manageable.

Examples:

- All FEMA postings.
- All DHS postings.
- All Emergency Management Specialist postings.
- All GS-13/14/15 postings in selected series.
- All postings in series 0089, 0301, 0343, 1109.
- All remote postings.
- All Chicago/Midwest postings.

#### STAGED_DOWNLOAD

Use when a full download is possible but too large for a first pass.

Download in this order:

1. Last 12 months, all relevant searches.
2. Last 5 years for target agencies/series.
3. Full history for target agencies/series.
4. Full federal historical structured records if feasible.
5. Announcement text only for selected/high-value records.
6. Embeddings only for selected/high-value announcement text.

#### SAMPLE_ONLY

Use only when the data is too large or API limits prevent a practical full/staged import.

Even then, download a representative sample that includes:

- Current jobs.
- Historical jobs.
- FEMA jobs.
- DHS jobs.
- GS-13/14/15 jobs.
- Remote jobs.
- Chicago/Midwest jobs.
- Emergency management jobs.
- Grants jobs.
- Program analyst jobs.
- Management analyst jobs.
- Policy jobs.
- Non-matches for scoring tests.

---

## Non-Negotiable Safety and Reliability Rules

The app must:

1. Never hardcode API keys.
2. Store API keys only in `.env`.
3. Respect API rate limits.
4. Use pagination safely.
5. Retry failed requests with backoff.
6. Save raw responses for debugging.
7. Deduplicate records.
8. Support resumable downloads.
9. Keep a manifest of downloaded files.
10. Track source URL, endpoint, query parameters, request time, and response metadata.
11. Log errors in a user-readable way.
12. Provide an admin/debug page showing data freshness and import status.

---

## Recommended Technical Stack

Use this stack for Version 1:

- Python
- Streamlit
- SQLite
- pandas
- Plotly
- requests
- python-dotenv
- pytest
- openpyxl

Avoid in Version 1:

- React
- FastAPI
- user accounts
- cloud deployment
- Docker
- complex auth
- complicated background workers
- paid APIs
- automated applications
- browser scraping
- vector databases before the relational data pipeline works

A later version may add:

- FastAPI
- React
- Postgres
- Docker
- pgvector or Chroma
- scheduled jobs
- cloud deployment
- email notifications
- richer AI/RAG features

---

## Initial Folder Structure

Create this repository structure:

```text
federal-jobs-intel/
  README.md
  CLAUDE.md
  .env.example
  requirements.txt
  config.py
  app.py

  data/
    federal_jobs.sqlite
    manifests/
    raw/
      usajobs_current/
      usajobs_historic/
      usajobs_announcement_text/
      opm_workforce/
    processed/
      samples/
      exports/

  docs/
    PRODUCT_SPEC.md
    DATA_MODEL.md
    API_NOTES.md
    ROADMAP.md
    DECISIONS.md
    DATA_INVENTORY.md
    FIELD_DICTIONARY.md
    FEATURE_FEASIBILITY_MATRIX.md
    DOWNLOAD_STRATEGY.md

  src/
    usajobs_current_api.py
    usajobs_historic_api.py
    usajobs_announcement_text_api.py
    opm_data.py
    database.py
    data_recon.py
    data_import.py
    scoring.py
    parsing.py
    charts.py
    maps.py
    alerts.py
    exports.py
    logging_utils.py

  pages/
    1_Search_Jobs.py
    2_Saved_Jobs.py
    3_Historical_Trends.py
    4_State_Map.py
    5_Scorecards.py
    6_Application_Tracker.py
    7_Data_Admin.py
    8_Settings.py

  tests/
    test_database.py
    test_usajobs_current_api.py
    test_usajobs_historic_api.py
    test_announcement_text_api.py
    test_opm_data.py
    test_data_recon.py
    test_scoring.py
    test_parsing.py
    test_alerts.py
```

---

## Environment Variables

Create `.env.example`:

```env
USAJOBS_USER_AGENT=your_email@example.com
USAJOBS_AUTHORIZATION_KEY=your_usajobs_api_key_here
DATABASE_PATH=data/federal_jobs.sqlite
RAW_DATA_PATH=data/raw
PROCESSED_DATA_PATH=data/processed
MAX_FULL_DOWNLOAD_GB=5
MAX_DATABASE_GB=10
MAX_FULL_DOWNLOAD_ROWS=5000000
MAX_IMPORT_HOURS=8
```

The real `.env` file should not be committed to git.

---

## Version 1 Product Features

Version 1 should focus on the dashboard, database, data import, filters, and basic trend analysis.

### 1. Current USAJOBS Search

The app should allow the user to search current USAJOBS postings.

Filters should include:

- Keyword
- Agency
- Department
- Series
- Grade
- Salary range
- Location
- State
- Remote
- Telework
- Hiring path
- Open date
- Close date
- Supervisory status
- Travel requirement
- Security clearance
- Appointment type

The result table should include:

- Job title
- Agency
- Series
- Grade
- Salary range
- Location
- Remote/telework status
- Open date
- Close date
- Match score
- Status
- Link to USAJOBS

### 2. Historical USAJOBS Import

The app should download historic JOA records.

Must support:

- Full download if feasible.
- Focused full download if the full dataset is too large.
- Staged download by date range, agency, series, grade, location, and keyword.
- Resumable imports.
- Deduplication.
- Import manifest.

### 3. Announcement Text Import

The app should download long-form announcement text for:

- Saved jobs.
- High-match jobs.
- Recent jobs.
- Historical jobs selected for analysis.
- Jobs used in the resume-matching/RAG layer.

Do not embed all announcement text until the size and cost are understood.

### 4. OPM Workforce Data Import

The app should support importing OPM workforce datasets.

Initial OPM imports should focus on:

- Employment/status data.
- Accessions data.
- Separations data.
- Location fields.
- Agency fields.
- Occupation/series fields.
- Grade/pay plan fields.
- Time period fields.

### 5. Saved Jobs, Tags, Notes, and Status

Users should be able to:

- Save jobs.
- Tag jobs.
- Add notes.
- Mark application status.

Statuses:

- New
- Interested
- Maybe
- Applied
- Referred
- Interview
- Selected
- Not selected
- Skip
- Archived

### 6. Match Scoring

Each job should receive a transparent score from 0 to 100.

The score should prioritize:

- FEMA
- DHS
- Emergency management
- Mitigation
- Public Assistance
- Grants management
- Disaster recovery
- Policy analysis
- Program analysis
- Infrastructure
- Resilience
- Supervisory roles
- GS-13
- GS-14
- GS-15
- Chicago
- Midwest
- Remote

The scoring function must return:

- Numeric score
- Short explanation
- Positive factors
- Negative factors
- Missing information

### 7. Historical Trend Graphs

Charts should include:

- Postings over time
- Postings by agency over time
- Postings by series over time
- Postings by grade over time
- Salary range over time
- Remote postings over time
- Postings by state over time
- Keyword frequency over time
- Open-to-public vs. status-only trends if available
- Supervisory vs. non-supervisory trends if available

### 8. State Map

Build a map of the United States showing job activity by state.

The map should support:

- USAJOBS postings by state
- OPM workforce counts by state
- OPM accessions by state
- Filters by agency, series, grade, salary, remote, date range, and keyword

Remote jobs must be handled separately to avoid distorting state counts.

Categories:

- Location-specific postings
- Multi-location postings
- Remote-anywhere postings
- Telework-eligible postings
- Unknown/unclear location postings

### 9. Scorecards

Create scorecards for:

- Hottest agencies
- Hottest series
- Hottest locations
- Hottest grades
- Hottest keywords
- Best remote opportunities
- Best matches for my profile
- Fastest-growing agencies/series/locations

Each scorecard should support historical date ranges.

A “hotness” formula should include:

- Current posting volume
- Growth versus prior period
- GS-13/14/15 share
- Remote share
- Salary level
- Match score
- Posting frequency
- Closing-window length

### 10. Alerts

Version 1 can start with manual or local alerts.

Alert rules should include:

- New remote job matching criteria
- GS-14 or GS-15 job matching criteria
- FEMA/DHS job matching criteria
- Chicago/Midwest job matching criteria
- High match score
- Closing soon
- Reposted job
- Salary threshold

Later versions can add email notifications.

### 11. Data Admin Page

The app must have a data/admin page showing:

- Last API pull
- Number of jobs imported
- Number of historic records imported
- Number of announcement texts imported
- Number of OPM records imported
- Duplicate records skipped
- Failed requests
- Current database size
- Raw data folder size
- Estimated completeness
- Download mode selected
- API/key status
- Errors and warnings

---

## Version 2 Features

Add after Version 1 is stable:

1. Application tracker.
2. Resume version manager.
3. Repost detector.
4. Closing-window tracker.
5. OPM posting-vs-accession comparison.
6. Salary/locality normalizer.
7. Better map and drill-downs.
8. Better “hotness” model.
9. Export to Excel/PDF.
10. Personal agency/series notes.
11. Career-ladder categorization.

---

## Version 3 AI/RAG Features

Add only after the relational data pipeline is working.

### Vector Search

Use vector search for semantic matching across:

- Job title
- Duties
- Qualifications
- Specialized experience
- Required documents
- Evaluation criteria
- Resume text
- Master resume bullets
- User preference profile

Potential tools:

- Chroma
- FAISS
- SQLite vector extension if practical
- pgvector later if moving to Postgres

### Resume-to-Job Matching

The app should compare a resume to a job announcement and return:

- Match score
- Evidence from resume
- Evidence from job announcement
- Missing keywords
- Specialized experience analysis
- Recommended resume emphasis
- Application-worthiness recommendation

The app must not invent experience.

### Hidden Opportunity Finder

Find jobs that do not use obvious terms but are relevant.

Examples:

- Program Analyst
- Management Analyst
- Grants Management Specialist
- Community Planner
- Infrastructure Program Specialist
- Policy Analyst
- Intergovernmental Affairs Specialist
- Resilience Coordinator
- Disaster Recovery Coordinator
- Risk Analyst

### Application Strategy Generator

For a selected job, generate:

- Why this job is worth applying to
- Key announcement language
- Resume keywords
- Suggested resume sections to emphasize
- Potential weaknesses
- Questions to answer before applying

---

## Database Requirements

Design the database before coding the dashboard.

Suggested tables:

### jobs

Stores normalized job announcement records.

Fields should include:

- id
- source
- position_id
- announcement_number
- title
- department
- agency
- sub_agency
- series
- grade_low
- grade_high
- pay_plan
- salary_min
- salary_max
- salary_type
- location_text
- state
- city
- remote_status
- telework_status
- open_date
- close_date
- hiring_paths
- appointment_type
- work_schedule
- supervisory_status
- travel_required
- security_clearance
- promotion_potential
- url
- source_endpoint
- source_query_hash
- raw_json_path
- imported_at
- updated_at

### job_text

Stores long-form announcement text.

Fields:

- job_id
- duties
- qualifications
- specialized_experience
- education
- required_documents
- how_to_apply
- evaluation_criteria
- conditions_of_employment
- raw_text
- raw_json_path
- imported_at

### saved_jobs

Fields:

- job_id
- status
- priority
- saved_at
- last_reviewed_at

### job_notes

Fields:

- job_id
- note
- created_at
- updated_at

### job_tags

Fields:

- job_id
- tag

### saved_searches

Fields:

- id
- name
- query_params_json
- alert_enabled
- alert_frequency
- created_at
- updated_at

### match_scores

Fields:

- job_id
- score
- explanation
- positive_factors_json
- negative_factors_json
- missing_info_json
- scoring_version
- created_at

### raw_api_responses

Fields:

- id
- source
- endpoint
- query_params_json
- response_path
- status_code
- record_count
- page_number
- request_time
- error_message

### import_manifests

Fields:

- id
- source
- endpoint
- download_mode
- date_range_start
- date_range_end
- filters_json
- estimated_records
- actual_records
- pages_requested
- pages_completed
- status
- started_at
- completed_at
- notes

### opm_workforce_records

Fields should be based on actual OPM field names after data inspection.

Likely categories:

- time period
- agency
- sub-agency
- occupation/series
- grade
- pay plan
- location
- employment count
- accession/separation action category
- salary or compensation fields

---

## Data Reconnaissance Task

Before building the full app, create `src/data_recon.py`.

It should:

1. Probe USAJOBS Historic JOAs by year/month.
2. Estimate record counts.
3. Estimate page counts.
4. Estimate file sizes.
5. Probe Announcement Text availability.
6. Inspect OPM downloadable datasets.
7. Produce `docs/DOWNLOAD_STRATEGY.md`.
8. Recommend `FULL_DOWNLOAD`, `FOCUSED_FULL_DOWNLOAD`, `STAGED_DOWNLOAD`, or `SAMPLE_ONLY`.

The output should include:

```text
Dataset:
Endpoint:
Date range:
Estimated records:
Estimated raw size:
Estimated database size:
API limits:
Recommended mode:
Reason:
Next action:
```

---

## First Claude Code Prompt

Use this prompt first.

```text
You are helping me build a local-first Federal Jobs Intelligence Dashboard.

Read this Project_Start.md completely.

Do not build the app yet.

First, create the repository structure and planning documents only.

Create or update:
- README.md
- CLAUDE.md
- .env.example
- requirements.txt
- docs/PRODUCT_SPEC.md
- docs/DATA_MODEL.md
- docs/API_NOTES.md
- docs/ROADMAP.md
- docs/DECISIONS.md
- docs/DATA_INVENTORY.md
- docs/FIELD_DICTIONARY.md
- docs/FEATURE_FEASIBILITY_MATRIX.md
- docs/DOWNLOAD_STRATEGY.md

The app should use:
- Python
- Streamlit
- SQLite
- pandas
- Plotly
- requests
- python-dotenv
- pytest
- openpyxl

Important:
- The app should attempt to download the entire USAJOBS historical dataset unless it is too large.
- Before any full download, implement a dataset reconnaissance plan.
- If the full dataset is huge, design a focused/staged download plan.
- Do not hardcode API keys.
- Do not implement React, FastAPI, cloud deployment, user accounts, or vector search in Version 1.
- Keep Version 1 realistic for a non-coder.

After creating the planning files, summarize:
1. What files you created.
2. What assumptions you made.
3. What data questions remain.
4. The first coding task you recommend.
```

---

## Second Claude Code Prompt: Data Reconnaissance

Use this only after the planning docs exist.

```text
Implement the data reconnaissance layer.

Create:
- src/data_recon.py
- src/logging_utils.py
- tests/test_data_recon.py

The goal is not to download the full dataset yet. The goal is to estimate whether a full download is practical.

Requirements:
1. Read thresholds from config.py.
2. Probe USAJOBS Historic JOAs by year/month where possible.
3. Probe Announcement Text availability.
4. Document API paging and limits.
5. Estimate record counts and raw data size.
6. Create or update docs/DOWNLOAD_STRATEGY.md.
7. Recommend one of:
   - FULL_DOWNLOAD
   - FOCUSED_FULL_DOWNLOAD
   - STAGED_DOWNLOAD
   - SAMPLE_ONLY
8. Use clear logging.
9. Write tests for the recommendation logic using mocked estimates.

Do not hardcode API credentials.
Do not start a full download.
```

---

## Third Claude Code Prompt: Database Foundation

```text
Implement the SQLite database foundation.

Create:
- src/database.py
- tests/test_database.py

Use the data model described in docs/DATA_MODEL.md.

Requirements:
1. Initialize the database.
2. Create required tables.
3. Support upserting jobs.
4. Prevent duplicate jobs by position ID, announcement number, and source.
5. Store raw API response metadata.
6. Store import manifests.
7. Store job text.
8. Store saved jobs, tags, notes, and statuses.
9. Store match scores.
10. Include tests for inserts, updates, duplicates, and retrieval.

Do not build the Streamlit UI yet.
```

---

## Fourth Claude Code Prompt: USAJOBS Import

```text
Implement USAJOBS import modules.

Create:
- src/usajobs_current_api.py
- src/usajobs_historic_api.py
- src/usajobs_announcement_text_api.py
- src/data_import.py
- tests/test_usajobs_current_api.py
- tests/test_usajobs_historic_api.py
- tests/test_announcement_text_api.py

Requirements:
1. Read USAJOBS credentials from .env.
2. Support current Search API imports.
3. Support Historic JOA imports.
4. Support Announcement Text imports.
5. Support pagination.
6. Respect rate limits.
7. Save raw JSON files.
8. Upsert normalized records into SQLite.
9. Support resumable downloads using import_manifests.
10. Include a dry-run mode.
11. Include a max-pages setting for testing.
12. Include clear errors for missing API credentials.
13. Include tests using mocked API responses.

Do not download the entire dataset until the reconnaissance step approves it.
```

---

## Fifth Claude Code Prompt: First Streamlit App

```text
Build the first Streamlit app.

Create:
- app.py
- pages/1_Search_Jobs.py
- pages/2_Saved_Jobs.py
- pages/3_Historical_Trends.py
- pages/4_State_Map.py
- pages/5_Scorecards.py
- pages/7_Data_Admin.py
- pages/8_Settings.py

Requirements:
1. Show database status.
2. Let me run a current USAJOBS search.
3. Let me view results in a table.
4. Let me filter by agency, series, grade, salary, location, remote, and date.
5. Let me save jobs.
6. Let me add tags and notes.
7. Let me mark job status.
8. Show historical trend charts if historical data exists.
9. Show a state map if location/state data exists.
10. Show scorecards if data exists.
11. Show an admin page with import status, errors, and data freshness.

Keep the UI simple, readable, and functional.
```

---

## Sixth Claude Code Prompt: Match Scoring

```text
Implement transparent job match scoring.

Create:
- src/scoring.py
- tests/test_scoring.py

The scoring system should prioritize:
- FEMA
- DHS
- Emergency management
- Mitigation
- Public Assistance
- Grants management
- Disaster recovery
- Policy analysis
- Program analysis
- Infrastructure
- Resilience
- Supervisory roles
- GS-13
- GS-14
- GS-15
- Chicago
- Midwest
- Remote

Each scoring result must include:
- score from 0 to 100
- explanation
- positive factors
- negative factors
- missing information
- scoring version

Add score and explanation to the job table and job detail page.

The score must be transparent and rule-based in Version 1. Do not use an LLM for scoring yet.
```

---

## Seventh Claude Code Prompt: Alerts

```text
Implement local alert rules.

Create:
- src/alerts.py
- tests/test_alerts.py

Requirements:
1. Let saved searches have alert_enabled true/false.
2. Detect new matching jobs since the last search.
3. Detect high-score jobs.
4. Detect remote jobs matching saved criteria.
5. Detect closing-soon jobs.
6. Produce an alert summary table inside the app.
7. Export alerts to CSV.

Do not implement email sending yet unless the local alert summary works.
```

---

## Definition of Done for Version 1

Version 1 is done when:

1. The app runs locally with `streamlit run app.py`.
2. The database initializes successfully.
3. Current USAJOBS search works.
4. Historic JOA import works for at least a limited date range.
5. Data reconnaissance recommends a full, staged, focused, or sample download.
6. Raw API responses are saved.
7. Jobs are deduplicated.
8. Jobs can be filtered in the UI.
9. Jobs can be saved, tagged, noted, and assigned statuses.
10. Basic match scoring works.
11. Trend charts work when historical data is present.
12. State map works when state/location data is present.
13. Scorecards work when enough data is present.
14. Admin page shows import status and data freshness.
15. Tests pass.
16. README explains how to run the app.

---

## Questions to Resolve During Build

Claude Code should investigate and document:

1. How many records are available through Historic JOAs?
2. What is the maximum practical download size?
3. What fields are available in Historic JOAs versus current Search results?
4. How reliable are location fields?
5. How should remote jobs be represented on maps?
6. How should multi-location jobs be counted?
7. How much Announcement Text data is available?
8. Whether Announcement Text should be downloaded for all records or only high-value records.
9. How OPM workforce data fields line up with USAJOBS fields.
10. Whether OPM accessions can be compared meaningfully to USAJOBS postings.
11. Which occupational series matter most for my career use case.
12. Whether salary ranges need locality normalization.
13. How to avoid double-counting repeated announcements.

---

## Initial Target Agencies, Series, and Keywords

### Agencies and Departments

- FEMA
- DHS
- Department of Homeland Security
- FIMA
- CISA
- HUD
- EDA
- EPA
- USACE
- SBA
- HHS
- DOT
- USDA
- DOI

### Occupational Series

Start with:

- 0089 Emergency Management Specialist
- 0301 Miscellaneous Administration and Program
- 0343 Management and Program Analysis
- 1109 Grants Management
- 0020 Community Planning
- 0101 Social Science
- 0110 Economist
- 0300 General Administrative
- 0501 Financial Administration and Program
- 0560 Budget Analysis

### Keywords

- emergency management
- mitigation
- hazard mitigation
- public assistance
- disaster recovery
- resilience
- infrastructure
- grants management
- policy analysis
- program analysis
- management analyst
- supervisory
- remote
- telework
- climate resilience
- community resilience
- risk analysis
- intergovernmental
- recovery
- preparedness
- response
- continuity
- federal assistance
- cooperative agreement
- grant compliance
- infrastructure resilience

---

## Build Philosophy

Build boring first.

The app should first become a reliable local database and dashboard. Then add intelligence.

Correct order:

1. Data reconnaissance.
2. Database.
3. Import pipeline.
4. Basic UI.
5. Filters.
6. Trend charts.
7. Map.
8. Scorecards.
9. Alerts.
10. Resume matching.
11. Vector search.
12. AI application strategy.

Do not add advanced AI features until the basic data is clean and trustworthy.
