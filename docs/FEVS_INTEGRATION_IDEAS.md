# FEVS Integration — Parking-Lot Ideas

**Status:** exploratory only. **Not on the V1 or V1.5 roadmap.** Do not implement from this file. If/when this graduates, write an ADR and a ROADMAP entry first.

**Date captured:** 2026-05-10

## Why this is here, not in ROADMAP

User wants to revisit the idea of attaching Federal Employee Viewpoint Survey (FEVS) signals — or similar workplace-quality signals — to agencies / locations / offices in the dashboard and public map. Initial research suggests it's feasible at the agency level only, and the per-job / per-office version is largely impossible from public data. Parking the research here so it isn't lost and isn't accidentally pulled into V1.

## What FEVS actually publishes

- **OPM FEVS Public Data File** (annual, CSV/SAS) at <https://www.opm.gov/fevs/public-data-file/> and <https://catalog.data.gov/dataset/federal-employee-viewpoint-survey-fevs-public-data-file-f0ff2>.
- Aggregate companion files: "Index Results by Agency", "Employee Engagement Index Results by Agency".
- **Granularity is organizational, not geographic.** Agency + (sometimes) subcomponent / work-unit. **No duty station, city, ZIP, or office** in the public file — location is suppressed for respondent privacy.
- **Threshold rule:** subcomponents/work-units below a minimum respondent count are collapsed into "all other". In 2023 the work-unit identifier was effectively limited to agencies with ≥ 750 respondents. Many small bureaus and most field offices never appear individually.
- **Agency codes don't match USAJOBS.** FEVS uses OPM internal agency identifiers; USAJOBS uses 4-letter Organization codes (e.g. `HSCB`). No published crosswalk — would need a hand-curated mapping table.

## Feasibility by tie-in level

| Level | Feasible? | Why |
|---|---|---|
| Specific job/announcement | No | Survey is anonymous; no link to positions, supervisors, or vacancies. |
| Specific duty station / office | No | Suppressed in the public file. Cannot be recovered. |
| Sub-agency / bureau | Partial | Only when subcomponent meets respondent threshold AND a USAJOBS Organization code maps to it. Many USAJOBS sub-orgs won't have a match. |
| Agency (cabinet department / large independent) | **Yes** | ~17 large + 26 midsize + 30 small agencies have stable, comparable scores year over year. Mapping to USAJOBS top-level departments is a small fixed table. |

## Best Places to Work — likely the better integration target

Partnership for Public Service publishes the **Best Places to Work in the Federal Government** rankings, derived from FEVS + supplemental agency surveys. Coverage:

- 17 large + 26 midsize + 30 small agencies
- **459 subcomponents** (broader than what the FEVS public file gives directly)
- Engagement score plus 8 workplace-issue scores

**Caveats:**

- No documented public API or bulk CSV. Data is in an interactive site at <https://bestplacestowork.org/>.
- Two practical ways to consume it:
  1. **Deep-link** out from the agency profile to `bestplacestowork.org/agency/<slug>`. Zero data ownership, always current, no licensing risk. **This is probably the right V1-style integration if we ever do it.**
  2. **Manually maintain a small CSV** of headline scores once a year. Automated scraping would violate the project's hard "no scraping" rule; a hand-updated seed is fine.

## If we ever build it: shape of the integration

Sketch only — do not implement without an ADR.

- Reference table `agency_workplace_scores` (agency_code → year → engagement, satisfaction, leadership, source URL). Seed CSV like the other reference data per ADR-0027.
- Manual crosswalk USAJOBS Organization code → FEVS / Best Places to Work agency identifier (~70 rows; comparable to existing agency tables).
- Surface on the agency profile and as a small badge in JobCard / FeaturePanel: "Working at this agency: employee perspectives" with a deep link.
- **Never imply the score reflects the specific office, team, or supervisor.** Same labeling discipline as "postings ≠ hires".
- Skip subcomponent and per-location integration. Threshold gaps would leave most cards blank — exactly the "silently broken" failure the public-map V1.5 invariants tell us to avoid.

## Things to push back on if this gets picked up

- **No per-office or per-job FEVS data.** It doesn't exist publicly and inferring it would mislead users.
- **No auto-scraping Best Places to Work.** If their T&Cs change or the site moves behind auth, the dashboard would silently break the project's "no scraping" hard rule.
- **No promising "this agency has a good culture" claims** based on a 1-year score. Show the number, link the source, let the user judge.

## Other workplace-quality signals worth scoping later

Thrown in as future research seeds, not commitments:

- OPM Federal Workforce Data Portal (<https://data.opm.gov/>) — workforce composition, telework participation, separations. Already partly used in the dashboard for OPM file ingestion.
- MSPB Merit Principles Survey — different cadence, smaller scope, less granular than FEVS. <https://www.mspb.gov/about/surveys.htm>
- Glassdoor / Indeed agency pages — non-authoritative, ToS-restricted, not appropriate for this project.
- Agency-specific climate surveys (e.g. DoD DEOCS) — not all are public; usually agency-only.

## Sources captured

- <https://www.opm.gov/fevs/public-data-file/>
- <https://catalog.data.gov/dataset/federal-employee-viewpoint-survey-fevs-public-data-file-f0ff2>
- <https://catalog.data.gov/dataset/federal-employee-viewpoint-survey-fevs-index-results-by-agency-43f3c>
- <https://catalog.data.gov/dataset/federal-employee-viewpoint-survey-fevs-employee-engagement-index-results-by-agency-6967e>
- <https://www.opm.gov/fevs/reports/understanding-results/>
- <https://www.opm.gov/fevs/reports/opm-fevs-dashboard/>
- <https://bestplacestowork.org/rankings/>
- <https://bestplacestowork.org/about/methodology/>
- <https://developer.usajobs.gov/tutorials/code-list>
