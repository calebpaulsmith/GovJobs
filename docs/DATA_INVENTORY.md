# DATA_INVENTORY.md

What we know, and what we still need to confirm, about each external dataset.

Legend: `?` = unknown, to be filled by recon or a targeted probe.

---

## USAJOBS Search API

| Property | Value |
| --- | --- |
| Endpoint | `GET /api/Search` |
| Records returned | Currently open JOAs only |
| Field depth | Lightweight plus some long-ish fields in `UserArea.Details` |
| Auth | API key + email user-agent |
| Pagination | `Page=N`, `ResultsPerPage` max `500` |
| Agency filter | `Organization=<agency subelement code>`; FEMA = `HSCB` |
| Series filter | `JobCategoryCode`; multiple values are semicolon-delimited |
| Typical record count at any moment | ~25k-60k open JOAs (est.); Search result sets are capped by USAJOBS |
| Refresh cadence (ours) | Daily or on-demand for filtered searches |
| Raw size per pull | Small (MB-scale) |
| Last live check | 2026-05-05 |

Keyword search is secondary. `Keyword=FEMA` returned false positives; `Organization=HSCB` returned the clean current FEMA set.

---

## USAJOBS Historic JOAs API

| Property | Value |
| --- | --- |
| Endpoint | `GET /api/historicjoa` |
| Records | Historical + current JOAs in compact structured form |
| Auth | Public; no API key required |
| Earliest date | Observed FEMA sample begins `2015-12-23`; full endpoint range still to profile |
| Total record count | `3,133,132` all records observed on 2026-05-05 |
| Pagination | Continuation token via `paging.metadata.continuationToken` / `paging.next` |
| Per-request max | Observed `pageSize=500` |
| Filter params supported | `HiringAgencyCodes`, `HiringDepartmentCodes`, `PositionSeries`, `AnnouncementNumbers`, `USAJOBSControlNumbers`, `StartPositionOpenDate`, `EndPositionOpenDate`, `StartPositionCloseDate`, `EndPositionCloseDate` |
| Estimated raw JSON size (full) | ? |
| Estimated SQLite size after normalization | ? |
| Recommended download mode | Staged import: target agencies/series/date ranges first, then broader history |
| Last live check | 2026-05-05 |

FEMA check: `HiringAgencyCodes=HSCB` returned `26,479` records. The local `44` FEMA count was only a bounded sample: `41` historic rows from 2026-01-01 to 2026-05-05 plus `3` current Search rows.

---

## USAJOBS Announcement Text API

| Property | Value |
| --- | --- |
| Endpoint | `GET /api/historicjoa/announcementtext` |
| Records | Long-form text fields for historical + current JOAs |
| Auth | Public; no API key required |
| Coverage | Observed same total count as HistoricJoa for FEMA (`26,479` for `HSCB`) |
| Pagination | Same continuation-token pattern as HistoricJoa |
| Filter params supported | Same as HistoricJoa |
| Per-record size | KB to tens of KB |
| Recommended pull strategy | Filtered slices using the same scope as HistoricJoa: agency code + date range + optional series. Avoid one-control-number-per-request except for small ad hoc saved-job refreshes. |
| Estimated raw size for all records | ?; likely large enough to import selectively |
| Last live check | 2026-05-05 |

FEMA check: `HiringAgencyCodes=HSCB` returned `26,479` text records. The 2026-01-01 to 2026-05-05 FEMA slice returned `41` text rows in one page.

---

## Local SIF Documents

| File | Useful for | Imported? |
| --- | --- | --- |
| `opm sif guide v3.0.docx` | Conceptual SIF flow, JOA processing, data dictionary context, reference tables | No; documentation only |
| `data dictionary -all sif schemas.xlsx` | Field semantics, required/conditional flags, repeating field hints | No; documentation only |
| `data dictionary -all sif schemas uat.xlsx` | UAT version of SIF field semantics; useful for diffs | No; documentation only |

The SIF docs confirm that USAJOBS data is more structured than the current flat `jobs` table: locations, series, hiring paths, key requirements, and required documents can repeat. See `docs/USAJOBS_DATA_STRUCTURES.md`.

---

## OPM Federal Workforce Data

Format: large CSV / fixed-width / Excel files via the OPM data portal and FedScope.

| Dataset | URL | Format | Approx size | Cadence | Imported? |
| --- | --- | --- | --- | --- | --- |
| FedScope Employment cube | <https://www.opm.gov/policy-data-oversight/data-analysis-documentation/fedscope/> | CSV/zip | ? GB | Quarterly | No |
| Accessions | <https://data.opm.gov/explore-data/data/data-downloads> | CSV | ? | Periodic | No |
| Separations | <https://data.opm.gov/explore-data/data/data-downloads> | CSV | ? | Periodic | No |
| Special datasets (e.g., demographics) | <https://data.opm.gov/> | varies | ? | Periodic | No |

Recon must record per-dataset row count, file size, and field list.

---

## Storage Budget

Defaults from `.env.example`:

| Limit | Default | Trigger |
| --- | --- | --- |
| Raw JSON max | 5 GB | switch to `FOCUSED_FULL_DOWNLOAD` or `STAGED_DOWNLOAD` |
| SQLite max | 10 GB | trigger compaction / archival or focused mode |
| Row count max | 5,000,000 | focused / staged |
| Wall-clock import max | 8 h | staged |

---

## Recon Must Record

- Endpoint / URL.
- Date range probed.
- Pages requested and pages succeeded.
- Records returned per page (min / median / max).
- Observed rate limit.
- Estimated total records.
- Estimated raw size.
- Estimated normalized DB size.
- Recommended mode.
- Reason.
- Next action.
