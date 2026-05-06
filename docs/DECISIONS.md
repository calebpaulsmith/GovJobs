# DECISIONS.md

Architecture decision log. Append-only. Each entry is a decision that should outlive the conversation that produced it.

Format:

```text
## ADR-NNNN — Title
Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by ADR-XXXX
Context:
Decision:
Consequences:
```

---

## ADR-0001 — Local-first, single-user, SQLite
Date: 2026-05-04
Status: Accepted

**Context.** The user is one person who runs the app locally and is not a software engineer. The data is public. There is no need for hosting, auth, or multi-tenancy.

**Decision.** Version 1 is a Streamlit + SQLite single-user app run on the user's machine. No FastAPI, React, Docker, Postgres, or cloud deployment in V1.

**Consequences.** Setup is `pip install -r requirements.txt` + a `.env` file. No DBA, no auth, no scaling concerns. Future migrations to Postgres are possible because we keep DB access in `src/database.py`.

---

## ADR-0002 — Posting data and workforce data are kept separate
Date: 2026-05-04
Status: Accepted

**Context.** USAJOBS publishes *announcements*. OPM publishes *workforce composition, accessions, and separations*. Conflating these is a common analytic mistake.

**Decision.** The schema separates `jobs`/`job_text` (USAJOBS) from `opm_workforce_records` (OPM). Charts must label which source they come from. Joining the two requires a footnoted explanation.

**Consequences.** No "hire rate per posting" metric in V1 — the comparison isn't meaningful. Maps show two switchable layers.

---

## ADR-0003 — Reconnaissance gates large downloads
Date: 2026-05-04
Status: Accepted

**Context.** USAJOBS HistoricJoa and OPM datasets can be very large. A naïve full pull would burn time, disk, and rate-limit budget.

**Decision.** Before any large download, the recon script (`src/data_recon.py`) estimates size, paging, and runtime, then writes a `FULL_DOWNLOAD` / `FOCUSED_FULL_DOWNLOAD` / `STAGED_DOWNLOAD` / `SAMPLE_ONLY` recommendation to `docs/DOWNLOAD_STRATEGY.md`. The user explicitly approves the mode.

**Consequences.** All importers accept a download-mode argument that constrains scope. Resumable manifests track progress so partial pulls aren't wasted.

---

## ADR-0004 — Rule-based scoring in V1; LLM only in V3
Date: 2026-05-04
Status: Accepted

**Context.** Match scoring is core to the app. LLM-based scoring is opaque, costs money, and is unnecessary for the tilt the user wants (FEMA / DHS / GS-13–15 / Chicago / Midwest / remote).

**Decision.** V1 scoring is deterministic, transparent, rule-based. Each score returns a 0–100 number plus positive factors, negative factors, and missing info. LLM-based résumé matching arrives in V3 only.

**Consequences.** Scoring is testable and reproducible. We can iterate weights without re-embedding any data. Scoring version is stored with each row so historical scores stay interpretable.

---

## ADR-0005 — Raw API responses are first-class artifacts
Date: 2026-05-04
Status: Accepted

**Context.** APIs change. Bugs in the parser can corrupt the DB silently. We need to be able to re-derive the DB from raw bytes.

**Decision.** Every API response is written verbatim to `data/raw/{source}/{endpoint}/{date}/{hash}_{page}.json` and logged in `raw_api_responses`. Re-running the importer against existing raw files reproduces the DB without hitting the network.

**Consequences.** Disk usage grows with every pull. Recon estimates raw size as part of the mode recommendation. `data/raw/` is gitignored.

---

## ADR-0006 — Tests use mocked HTTP, never real USAJOBS
Date: 2026-05-04
Status: Accepted

**Context.** Hitting USAJOBS in CI would burn rate limit and break offline.

**Decision.** Use the `responses` library to stub HTTP in `tests/`. No test makes a network call. Importer functions accept a `dry_run=True` flag that returns a synthetic structure for higher-level tests.

**Consequences.** Tests are fast and offline. We need to keep stub fixtures up to date when the API shape changes; recon-step output helps spot drift.

---

## ADR-0007 — Streamlit pages are presentation only
Date: 2026-05-04
Status: Accepted

**Context.** Logic that lives in Streamlit pages is hard to test and easily duplicated.

**Decision.** Pages call into `src/` for everything: queries, scoring, importers, exports. Pages contain only UI wiring and presentation. Database access goes through `src/database.py`.

**Consequences.** Pages stay short. Replacing the UI later (FastAPI + React in a hypothetical V4) is mostly a port of the page layer.

---

## ADR-0008 — No automated job applications, ever
Date: 2026-05-04
Status: Accepted

**Context.** Auto-applying to federal jobs is a bad idea — it harms the user's reputation and violates USAJOBS terms.

**Decision.** The app never submits applications, fills application forms, or signs into usajobs.gov on the user's behalf. Saved jobs link out to the official USAJOBS page.

**Consequences.** "Application" features are always tracking-only.

---

## ADR-0009 — Recommendation formula: focused = 20%, staged ≤ 10 passes
Date: 2026-05-04
Status: Accepted

**Context.** `recommend_mode` in `src/data_recon.py` needs concrete numbers for "what counts as focused" and "how many passes is too many for staged."

**Decision.**
- A focused subset is modeled as 20% of the full dataset (`focused_factor=0.20`). This roughly matches a slice scoped to target agencies (FEMA, DHS, CISA, HUD, FIMA, USACE, etc.) and the 10 priority series.
- A staged pull is feasible if `passes_needed ≤ 10` AND the final DB still fits the configured `MAX_DATABASE_GB`. `passes_needed` is computed against `MAX_FULL_DOWNLOAD_GB`, `MAX_FULL_DOWNLOAD_ROWS`, and `MAX_IMPORT_HOURS`.
- If neither holds, the recommendation is `SAMPLE_ONLY`.

These constants are keyword arguments to `recommend_mode`, so they're tunable per-call without rewriting the function.

**Consequences.** The two thresholds (focused_factor and staged_max_passes) are independent: a dataset that fails focused at 20% but only needs 6 passes still gets STAGED. If we later tighten or loosen "what counts as focused," only the call site changes — the recommendation logic stays pure and tested.

---

## ADR-0010 — Recon falls back to documented estimates when credentials are missing
Date: 2026-05-04
Status: Accepted

**Context.** `python -m src.data_recon` should be useful before the user pastes their USAJOBS API key into `.env`, but it must never silently mislead them.

**Decision.** Probes detect missing/placeholder credentials and return `DatasetEstimate` rows built from order-of-magnitude defaults (4M HistoricJoa records, ~4 KB/record, 200k records/h throughput, etc.). Each fallback row sets `confidence="low"`, `probed=False`, and a `notes` line stating "no credentials." The strategy doc renders these flags so the user can tell at a glance whether the recommendation is live or estimated.

**Consequences.** First-run UX works without a key. Once credentials are added, the same script writes a fresh `## Recon log` with `confidence=medium` rows and updated estimates. No code change needed.

---

## ADR-0011 - REST docs are canonical for API parameters; SIF docs are canonical for field semantics
Date: 2026-05-05
Status: Accepted

**Context.** The repo includes local SIF guide and data-dictionary files, and USAJOBS also publishes live REST API documentation. The two sources overlap, but they answer different questions.

**Decision.** Importer query parameters must be verified against the official USAJOBS developer docs before coding. The local SIF docs are used to understand field meaning, required/conditional status, repeatability, text-section semantics, and code-list intent.

**Consequences.** We avoid broken REST calls caused by SIF/XML field names, while still using the richer local dictionaries to design the database and UI. `docs/USAJOBS_DATA_STRUCTURES.md` is the reconciliation file for this.

---

## ADR-0012 - Filter-first imports and UI
Date: 2026-05-05
Status: Accepted

**Context.** Keyword searches such as `FEMA` are noisy and can hide the structured shape of USAJOBS data. The APIs expose agency, department, series, date, grade, location, and other filters.

**Decision.** Import scopes and UI search controls should be built from structured filters first. Agency targeting uses codes: Search uses `Organization=HSCB` for FEMA, while HistoricJoa and AnnouncementText use `HiringAgencyCodes=HSCB`.

**Consequences.** Saved searches, historical imports, scorecards, and maps become reproducible. Keyword search remains available as a secondary text filter, not the primary import mechanism.

---

## ADR-0013 - Keep jobs flat for scanning, add child tables for repeated structures
Date: 2026-05-05
Status: Accepted

**Context.** The current `jobs` table is easy to query, but SIF and REST data show repeated locations, occupational series, hiring paths, and required documents. A single row cannot faithfully represent those structures.

**Decision.** Keep `jobs` as the summary/index table, and add child tables for repeated structures in Phase 4.5: `job_locations`, `job_categories`, `job_hiring_paths`, and `job_required_documents`, plus code lookup tables.

**Consequences.** The app can keep fast tables while gaining accurate maps, filters, eligibility views, and future scoring features. Existing imports continue to work, but broad imports should wait until the child-table schema lands.

---

## ADR-0014 - Recommendations are deterministic and explainable before embeddings
Date: 2026-05-05
Status: Accepted

**Context.** Phase 6.5 adds preference feedback and similar-job suggestions, but V3 AI/RAG work is intentionally deferred until the relational data pipeline is stable.

**Decision.** Similar-job recommendations are generated locally from structured fields, parsed text themes, tags, and explicit feedback. Every suggestion stores exact factors in `job_recommendations.factors_json`, and negative feedback can suppress or down-rank matching jobs.

**Consequences.** Recommendations are auditable, testable, and cheap to run. They are less semantically rich than embeddings, but they keep V1/V2 behavior transparent and give the later vector layer a clean feedback history to learn from.

---

## ADR-0015 - OPM ingestion is file-based and source-labeled
Date: 2026-05-05
Status: Accepted

**Context.** OPM workforce data is distributed as large downloadable files, not as a transactional API like USAJOBS. The app must keep workforce counts, accessions, and separations analytically separate from USAJOBS postings.

**Decision.** V1 imports OPM/FedScope CSV, TSV, Excel, or ZIP files through `src/opm_data.py` into `opm_workforce_records`. State maps expose an explicit source switch: "USAJOBS postings" or "OPM workforce", with separate OPM metrics for employment, accessions, and separations.

**Consequences.** The app can ingest downloaded OPM files without adding a network downloader or scheduler. Charts remain plainly labeled, avoiding posting-versus-hire confusion. More precise OPM field mapping can be added as real source files reveal additional column variants.
