# Federal Jobs Intelligence Dashboard

A local-first dashboard for searching, archiving, and analyzing USAJOBS postings and OPM federal-workforce data. Built to be runnable and improvable by a non-coder using Claude Code or Codex.

> Status: **V1 core plus early V2 tracking/intelligence phases are complete.** Reconnaissance, SQLite persistence, USAJOBS importers, Streamlit UI, rule-based scoring, alerts, explainable similar-job recommendations, OPM file import, GIS-style source-labeled maps, CSV/Excel exports, the local Application Tracker, Resume Versions, and Repost Detector are implemented.

---

## What this app will do (Version 1)

1. Search current USAJOBS postings by agency, series, grade, salary, location, remote, keyword, etc.
2. Download and archive historical USAJOBS announcements.
3. Import OPM federal-workforce datasets for separate, clearly-labeled analysis.
4. Show historical trend charts (postings over time, by agency, by series, by state, etc.).
5. Map federal job activity by state.
6. Save jobs with tags, notes, and application status.
7. Score jobs against a transparent rule-based profile (FEMA / DHS / emergency management / GS-13–15 / Chicago / Midwest / remote priorities).
8. Surface alerts for new matches, high scores, and closing-soon jobs.
9. Provide a data-admin page showing import status, freshness, and errors.

The remaining Version 2 and 3 work adds closing-window analytics, locality-normalized salary, vector search, and resume-to-announcement matching. See [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Important framing: postings vs. workforce

The app strictly separates two kinds of data:

- **USAJOBS posting data** — what was *announced* or *advertised*. (Use words like "postings" or "announcements".)
- **OPM workforce data** — what federal *employment, accessions, and separations* actually looked like. (Use words like "hires", "accessions", "separations", "workforce counts".)

A posting is not a hire. Maps and charts always label the data source.

---

## Tech stack (Version 1)

Python · Streamlit · SQLite · pandas · Plotly · requests · python-dotenv · pytest · openpyxl.

Explicitly **not** in V1: React, FastAPI, Docker, cloud deployment, user accounts, vector databases, paid APIs, automated job applications, browser scraping.

---

## Repository layout

```text
.
├── Project_Start.md              # Original project brief — source of truth for scope
├── README.md                     # You are here
├── CLAUDE.md                     # Guidance for AI coding assistants in this repo
├── .env.example                  # Template for required environment variables
├── requirements.txt              # Python dependencies (V1)
├── config.py                     # Thresholds + paths read from .env
├── app.py                        # Streamlit entry point
├── data/
│   ├── federal_jobs.sqlite       # SQLite database created locally
│   ├── manifests/                # Import manifests
│   ├── raw/                      # Raw API JSON, by source
│   └── processed/                # Samples and exports
├── docs/                         # Planning docs (see below)
├── src/                          # Python modules
├── pages/                        # Streamlit multipage UI
└── tests/                        # pytest tests
```

### Planning docs

| File | Purpose |
| --- | --- |
| [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) | What the app is and is not; user stories per version |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | SQLite tables, fields, keys, dedup rules |
| [docs/API_NOTES.md](docs/API_NOTES.md) | USAJOBS + OPM endpoints, auth, paging, rate limits |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Versioned build order |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture decision log |
| [docs/DATA_INVENTORY.md](docs/DATA_INVENTORY.md) | What we know about size of each dataset |
| [docs/FIELD_DICTIONARY.md](docs/FIELD_DICTIONARY.md) | Definitions of every normalized field |
| [docs/FEATURE_FEASIBILITY_MATRIX.md](docs/FEATURE_FEASIBILITY_MATRIX.md) | Each feature × data it requires × feasibility |
| [docs/DOWNLOAD_STRATEGY.md](docs/DOWNLOAD_STRATEGY.md) | Recommended download mode per dataset |
| [docs/MAP_FEATURE_SPEC.md](docs/MAP_FEATURE_SPEC.md) | Reusable GIS-style map feature sheet and replication checklist |

---

## Getting started

These are the local setup steps.

### Easy local launcher

On Windows, double-click `Open GovJobs.bat` from the repo root. It starts the
Streamlit dashboard, opens the main dashboard and Settings page, and starts the
public map at `http://localhost:5173/map`.

You can also run the same launcher from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_local.ps1
```

Use `-SkipMap` if you only want the Streamlit dashboard and Settings page.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_local.ps1 -SkipMap
```

### Manual setup

1. Install Python 3.11+ and create a virtual environment.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your USAJOBS credentials. Get a key at <https://developer.usajobs.gov/>.
4. Run the data-reconnaissance step before any large download: `python -m src.data_recon`.
5. Run the app: `streamlit run app.py`.

The reconnaissance step decides whether the historical USAJOBS dataset should be pulled as `FULL_DOWNLOAD`, `FOCUSED_FULL_DOWNLOAD`, `STAGED_DOWNLOAD`, or `SAMPLE_ONLY`. See [docs/DOWNLOAD_STRATEGY.md](docs/DOWNLOAD_STRATEGY.md).

---

## Safety rules the code must honor

- API keys live only in `.env` (never committed, never hardcoded).
- All API requests respect documented rate limits and use exponential-backoff retries.
- Raw API responses are saved to `data/raw/...` for debugging and reproducibility.
- Imports are resumable and deduplicated.
- Every imported record tracks its source URL, endpoint, query parameters, and request time.
- An admin page surfaces freshness, errors, and import progress.

---

## Build philosophy

Build boring first. Get the database, importers, filters, and trend charts working reliably before adding any AI/RAG features. See [docs/ROADMAP.md](docs/ROADMAP.md) for the strict build order.
