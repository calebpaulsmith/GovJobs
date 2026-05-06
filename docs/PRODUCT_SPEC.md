# PRODUCT_SPEC.md

## Purpose

A local, single-user dashboard that turns USAJOBS posting data and OPM workforce data into actionable career intelligence — specifically tilted toward FEMA/DHS/emergency-management/grants/policy work at GS-13 through GS-15, with a Chicago/Midwest and remote bias.

## Non-goals (V1)

- No multi-user / no auth / no SaaS.
- No automated job applications.
- No browser scraping.
- No paid AI APIs.
- No vector search / RAG (V3 only).
- No mobile UI.

## Users and personas

Single user: a federal-careers-focused analyst who can run a Streamlit app, edit a `.env` file, and read a Plotly chart, but is not a software engineer. AI assistants (Claude Code, Codex) are co-users that read this spec to extend the codebase safely.

## Core terminology (must be honored everywhere)

| Term | Means | Source |
| --- | --- | --- |
| Posting / announcement | A USAJOBS Job Opportunity Announcement (JOA) | USAJOBS APIs |
| Hire / accession | A federal new hire recorded by OPM | OPM datasets |
| Separation | A federal employee leaving service | OPM datasets |
| Workforce count | Headcount on a reporting date | OPM datasets |

A posting is *not* a hire. Multiple postings can lead to one hire; one posting can fill many positions; some postings produce zero hires.

## Product principles

- Prefer structured filters over broad keyword searches. The app should guide the user toward agency codes, department codes, occupational series, grade/pay plan, location, remote status, dates, hiring paths, travel, security clearance, and supervisory status.
- Keep keyword search available, but treat it as a secondary text filter for discovery and narrowing.
- Preserve repeated structures from the source data. A job can have multiple locations, series, hiring paths, and required documents; the UI should not pretend those are always single values.
- Preference learning must be explainable. When the user marks a job as liked/disliked or "more/less like this," the app should accept a short explanation for later review, and every suggested job must offer a "why suggested" view.

## V1 user stories

1. *As a user,* I open the app and see whether the database is initialized and how fresh the data is, so I know what I'm looking at.
2. *As a user,* I run a current USAJOBS search with structured filters (agency code/name, series, grade, salary, location, remote, date) plus optional keyword text, and view results in a sortable table with a link back to USAJOBS.
3. *As a user,* I save a job, tag it, add a note, and assign a status (New, Interested, Maybe, Applied, Referred, Interview, Selected, Not selected, Skip, Archived).
4. *As a user,* I see a transparent match score 0–100 for each job along with positive factors, negative factors, and missing info.
5. *As a user,* I import historical USAJOBS data by filter scope (agency code, department code, series, date range, grade/pay plan), but only after the recon step recommends a download mode and I approve it.
6. *As a user,* I view trend charts: postings over time, by agency, by series, by grade, by state; remote share over time; salary range over time.
7. *As a user,* I view a US state map of postings (with remote and multi-location handled separately).
8. *As a user,* I view scorecards (hottest agencies/series/locations/grades; best remote opportunities; best matches).
9. *As a user,* I see a list of local alerts (saved-search matches, high score, closing soon, reposted) and can export them to CSV.
10. *As a user,* I open the Data Admin page to see import status, last API pull, errors, raw-folder size, and database size.
11. *As a user,* I can mark jobs as liked, disliked, more like this, or less like this, optionally with a short explanation, so the app can learn my preferences without losing my reasoning.
12. *As a user,* I can review suggested similar jobs and open an explanation showing exactly which shared fields, text signals, or feedback patterns caused the suggestion.

## V2 user stories (after V1 is stable)

11. Track applications end-to-end with résumé version, submission date, USAJOBS reference, and outcome.
12. Detect reposts of the same announcement by similarity of title/series/agency/text hash.
13. Closing-window tracker (median days open by series and grade).
14. Compare USAJOBS posting volume to OPM accession volume by agency/series.
15. Locality-adjusted salary view.
16. Improved hotness model.
17. Excel/PDF export of saved jobs and scorecards.
18. Personal agency / series notes (separate from per-job notes).
19. Career-ladder categorization (e.g., "GS-12 → GS-13 ladder").
20. Improved preference learning using saved feedback history, negative preferences, and explanation review.

## V3 user stories (AI / RAG)

21. Vector search across job duties, qualifications, specialized experience, and résumé text.
22. Resume-to-announcement matching that returns score, evidence, missing keywords, and "should I apply?" recommendation. **Must not invent experience.**
23. Hidden-opportunity finder for jobs whose titles do not use obvious keywords.
24. Application-strategy generator (key announcement language, résumé sections to emphasize, weaknesses, pre-application questions).

## Definition of done — V1

The build is done when:

1. `streamlit run app.py` opens the app locally.
2. SQLite DB initializes from a clean checkout.
3. Current USAJOBS search works.
4. Historic JOA import works for at least a limited date range.
5. Recon step produces a `DOWNLOAD_STRATEGY.md` recommendation.
6. Raw API responses are saved on disk; jobs are deduplicated.
7. Filters work in the UI.
8. Save / tag / note / status all work.
9. Match scoring (rule-based) works and is shown on every job.
10. Trend charts, state map, and scorecards render when data is present.
11. Admin page shows import status and freshness.
12. Tests pass with `pytest`.
13. README explains setup and run.

## Out-of-scope clarifications

- We will not build email/push notifications in V1; local in-app alerts are manual and stored in SQLite.
- We will not call any LLM in V1 — scoring is rule-based.
- We will not deploy to the cloud.
