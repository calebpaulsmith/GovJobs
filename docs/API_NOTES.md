# API_NOTES.md

Working notes on the external APIs the app uses. Treat the "what we believe" sections as starting hypotheses — `src/data_recon.py` will confirm or correct them when the user runs it for the first time.

---

## USAJOBS

Base host: `https://data.usajobs.gov`.

Before changing importer parameters, verify the current official docs at
<https://developer.usajobs.gov/api-reference/>. The local SIF docs in the repo
are useful for field semantics, but REST parameter names come from the live
developer docs. See `docs/USAJOBS_DATA_STRUCTURES.md`.

### Auth

Every request needs:

| Header | Value |
| --- | --- |
| `Host` | `data.usajobs.gov` |
| `User-Agent` | the email tied to your USAJOBS developer account (`USAJOBS_USER_AGENT`) |
| `Authorization-Key` | API key from the USAJOBS developer portal (`USAJOBS_AUTHORIZATION_KEY`) |

Keys are issued at <https://developer.usajobs.gov/>. Do not embed in code.

### Endpoints we use

#### 1. Search API — `/api/Search`

Reference: <https://developer.usajobs.gov/api-reference/get-api-search>

- Returns currently open JOAs. Lightweight fields only.
- Typical params: `Keyword`, `LocationName`, `RemunerationMinimumAmount`, `RemunerationMaximumAmount`, `JobCategoryCode`, `Organization`, `PayGradeLow`, `PayGradeHigh`, `PositionScheduleTypeCode`, `RemoteIndicator`, `ResultsPerPage`, `Page`.
- Use `Organization=<agency subelement code>` for clean agency-targeted current searches. Example: FEMA is `Organization=HSCB`. Keyword searches such as `Keyword=FEMA` are useful but noisy.
- Multiple values are generally semicolon-delimited for Search filters.
- `ResultsPerPage` max ≈ 500. Confirm during recon.
- Pagination is page-based via `Page=N`.
- Use for the live search UI and for daily "new postings since last run" alerts.

#### 2. Historic JOAs API — `/api/HistoricJoa`

Reference: <https://developer.usajobs.gov/API-Reference/GET-api-HistoricJoa>

- Returns historical and current announcement records in compact form.
- Intended for bulk historical consumption.
- Canonical filters are plural/case-sensitive as documented: `HiringAgencyCodes`, `HiringDepartmentCodes`, `PositionSeries`, `AnnouncementNumbers`, `USAJOBSControlNumbers`, `StartPositionOpenDate`, `EndPositionOpenDate`, `StartPositionCloseDate`, `EndPositionCloseDate`.
- Use agency codes for targeted backfills. Example: FEMA is `HiringAgencyCodes=HSCB`.
- Live check on 2026-05-05: `HiringAgencyCodes=HSCB` returned `26,479` FEMA records.
- Recon must confirm: total available records, earliest date, paging mechanism (cursor vs. page), per-request maximum, and rate-limit headers.
- Use for trend charts, scorecards, the state map, and the historical archive.

#### 3. Announcement Text API — `/api/historicjoa/announcementtext`

Reference: <https://developer.usajobs.gov/api-reference/get-api-AnnouncementText>

- Public bulk endpoint at `/api/historicjoa/announcementtext` with the same continuation-token style as HistoricJoa.
- Long-form text fields (summary, duties, qualifications, specialized experience, etc.).
- Heavy. Do **not** pull for every historic record at the start.
- Key fields for matching: `summary` ("what this job is" at the top of the announcement) and `requirementsQualifications` (the qualifications / grade-equivalency language).
- Uses the same canonical filters as HistoricJoa. For agency/date slices, import text with `HiringAgencyCodes` + date range instead of calling one `USAJOBSControlNumbers` request per job.
- Live check on 2026-05-05: `HiringAgencyCodes=HSCB` returned `26,479` FEMA text records, and a 2026-01-01 to 2026-05-05 FEMA slice returned `41` text records in one page.
- Pull strategy: only for saved jobs, currently-open high-match jobs, jobs flagged for the (V3) RAG layer, and a sampled set for trend analysis.

### Rate limiting

Reference: <https://developer.usajobs.gov/guides/rate-limiting>

- USAJOBS publishes guidance per endpoint; recon step must read response headers and record observed throttle behavior in `docs/DATA_INVENTORY.md`.
- Implementation rule: respect any `Retry-After` header, default to 1 request/second per endpoint, exponential backoff on 429/5xx, max 5 retries.

### Pagination contract (our wrapper)

All importers expose:

```python
def fetch_pages(
    endpoint: str,
    params: dict,
    *,
    max_pages: int | None = None,
    dry_run: bool = False,
    on_page: Callable[[dict, int], None] | None = None,
) -> Iterator[dict]:
    ...
```

Each yielded dict is the raw decoded JSON for one page. The wrapper writes raw JSON to `data/raw/...`, logs an entry to `raw_api_responses`, and respects backoff. `dry_run=True` makes no network calls and returns a synthetic structure for tests.

### Error handling

| Status | Action |
| --- | --- |
| 200 | record + parse |
| 401 / 403 | abort with a credential-config error |
| 404 | log + skip page |
| 429 | sleep `Retry-After` (or 30s), retry, exponential backoff, max 5 |
| 5xx | exponential backoff, max 5 |
| network error | exponential backoff, max 5 |

After 5 failures, the manifest is marked `failed` with the error stored, and the importer exits cleanly so the user can resume later.

---

## OPM Federal Workforce Data

Sources:

- Data portal: <https://data.opm.gov/>
- Downloads: <https://data.opm.gov/explore-data/data/data-downloads>
- Getting started: <https://data.opm.gov/info-and-help/getting-started>
- FedScope (cube + downloads): <https://www.opm.gov/policy-data-oversight/data-analysis-documentation/fedscope/>

### What we expect

OPM publishes large CSV / fixed-width / Excel files rather than a transactional API. Examples include FedScope employment cubes (quarterly), accessions, separations, and special datasets. Typical fields include agency, sub-agency, occupational series, pay plan, grade, location, headcount.

### What we do

V1 OPM importer is a file-based ETL: download a CSV/TSV/Excel/zip to `data/raw/opm_workforce/`, normalize it with `src/opm_data.py` into `opm_workforce_records`, log to `raw_api_responses` and `import_manifests`. No streaming API.

OPM datasets can be large. The recon step must estimate raw size, processed size, and import time before any large pull, same as for USAJOBS.

### Comparing OPM to USAJOBS

OPM accessions are *hires*. USAJOBS records are *postings*. Any chart that places them on the same axis must be footnoted with that distinction. Direct ratios ("hire rate per posting") are unreliable because postings can fill 0..N positions.

---

## Remaining questions for recon

1. Earliest date across the full HistoricJoa endpoint, not just the FEMA sample.
2. Practical sustained request rate before 429 for HistoricJoa and AnnouncementText.
3. Actual raw JSON size and normalized SQLite size for representative HistoricJoa and AnnouncementText slices.
4. Whether AnnouncementText coverage remains one-to-one outside the FEMA sample.
5. Which official code-list files/endpoints should seed `agency_codes` and `code_lists`.
6. Most useful OPM datasets and their refresh cadence.
7. Field-name mapping between OPM datasets and USAJOBS fields (series codes, agency codes).
