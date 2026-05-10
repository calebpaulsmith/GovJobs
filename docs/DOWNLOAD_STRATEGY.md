# DOWNLOAD_STRATEGY.md

Recommended download mode per dataset. **This file is the output of `src/data_recon.py`.** Until the recon script runs, the entries below are placeholders — every numeric estimate is `?` and every recommendation is `pending`.

---

## How modes are chosen

A dataset is "huge" if any of these are true (configurable in `config.py`, defaults from `.env.example`):

- Estimated raw download > 5 GB
- Estimated DB size > 10 GB
- Estimated row count > 5,000,000
- Wall-clock to import > 8 hours
- API limits make a full import impractical without long-running batches
- Dataset includes long text that would explode local storage / embedding cost

Decision tree:

```
 not huge          → FULL_DOWNLOAD
 huge but a focused slice fits within all four limits
                   → FOCUSED_FULL_DOWNLOAD
 full eventually feasible but can't be done in one pass
                   → STAGED_DOWNLOAD
 even staged is impractical
                   → SAMPLE_ONLY (representative sample described below)
```

Mode definitions are in `Project_Start.md` §Download Modes.

---

## USAJOBS Search API

```text
Dataset:               USAJOBS Search (current open JOAs)
Endpoint:              GET /api/Search
Date range:            current snapshot
Estimated records:     ~25k–60k at any moment (est.)
Estimated raw size:    < 200 MB per full snapshot (est.)
Estimated database size: < 50 MB (est.)
API limits:            documented; recon to confirm sustained rate
Recommended mode:      FULL_DOWNLOAD (snapshot daily for "new since last run")
Reason:                Small, lightweight; refresh cost is low.
Next action:           After recon confirms paging behavior, schedule daily snapshot via Data Admin button (no auto-cron in V1).
```

---

## USAJOBS Historic JOAs

```text
Dataset:               USAJOBS HistoricJoa
Endpoint:              GET /api/HistoricJoa
Date range:            all available
Estimated records:     3,133,132 total observed; FEMA HSCB subset 26,479 observed
Estimated raw size:    ?
Estimated database size: ?
API limits:            continuation-token pagination; observed pageSize=500
Recommended mode:      STAGED_DOWNLOAD
Reason:                Structured rows are feasible, but imports should be scoped by agency/date/series to keep raw files and runtime manageable.
Next action:           Use filter-first import scopes, starting with agency codes and date ranges.
```

Structured import order:

1. **STAGED_DOWNLOAD**, in this order:
   1. Last 12 months by target agency codes.
   2. Last 5 years for target agency codes and series (FEMA `HSCB`; DHS department `HS`; other codes to be loaded from code lists; series 0089, 0301, 0343, 1109, 0020, 0101, 0110, 0300, 0501, 0560).
   3. Full history for those target agencies and series.
   4. Full federal historical structured records if feasible.
   5. AnnouncementText by the same filter scope as HistoricJoa, not one control number at a time.
   6. Embeddings only for selected announcement text (V3).
2. If even staged is impractical, fall back to **SAMPLE_ONLY** with the representative sample listed in `Project_Start.md`.

---

## Public map corpus target

D.5.7 target for meaningful public-map review:

```text
Open postings target:          >= 5,000 current USAJOBS postings
Closed-postings target:        >= 5,000 HistoricJoa records closed within trailing 90 days
Current import presets:        federal-wide current; top-25 agencies current
Historical context preset:     trailing-90-days closed by Start/EndPositionCloseDate
Recon gate:                    Every preset calls src.data_recon.run_recon first and rewrites this document before importing
Initial safe caps:             2 current pages per scope; 10 HistoricJoa pages
Operator path:                 Data Admin -> Public Map Corpus
```

The presets are intentionally capped for the first run. Increase page caps only after the recon log and USAJOBS rate-limit behavior look acceptable. Current Search requires credentials in `.env`; HistoricJoa trailing-90-day context does not.

---

## USAJOBS Announcement Text

```text
Dataset:               AnnouncementText (long fields)
Endpoint:              GET /api/historicjoa/announcementtext
Date range:            same scope as HistoricJoa slice
Estimated records:     same as matching HistoricJoa slice when text is available
Estimated raw size:    ? (per record KB to tens of KB)
Estimated database size: ?
API limits:            continuation-token pagination; observed pageSize=500
Recommended mode:      FOCUSED_FULL_DOWNLOAD by selection (saved jobs, high-score, recent, sampled)
Reason:                Text is large, but endpoint supports the same agency/date/series filters as HistoricJoa. Filtered slices are much faster than one control-number request per job.
Next action:           Import text immediately after each HistoricJoa slice using the exact same filter params.
```

---

## OPM workforce data

```text
Dataset:               OPM Federal Workforce (FedScope + data.opm.gov downloads)
Endpoint:              File downloads
Date range:            most recent 5 years initially; older as needed
Estimated records:     ?
Estimated raw size:    ?
Estimated database size: ?
API limits:            n/a (file downloads)
Recommended mode:      pending — likely STAGED_DOWNLOAD by quarter / dataset
Reason:                Files are large. Older data has lower analytical value for short-term decisions.
Next action:           Inventory the data.opm.gov downloads page during recon and choose specific datasets (employment cube, accessions, separations).
```

---

## Recon log

Most recent run rewrites this section. Each block represents one dataset.

```text
Run timestamp:       2026-05-10T00:43:15Z
Dataset:             USAJOBS Search (current open JOAs)
Endpoint:            GET /api/Search
Date range:          n/a
Estimated records:   10,000
Estimated raw size:  0.05 GB
Estimated DB size:   0.01 GB
Estimated import:    0.05 h
API limits:          Probed Search count via SearchResultCountAll.
Confidence:          medium
Probed:              True
Recommended mode:    FULL_DOWNLOAD
Reason:              All four estimates (raw size, DB size, row count, import hours) are within configured thresholds.
Next action:         Run the historic importer with the full date range; record progress in import_manifests.
Notes:               
```

```text
Run timestamp:       2026-05-10T00:43:15Z
Dataset:             USAJOBS HistoricJoa
Endpoint:            GET /api/HistoricJoa
Date range:          n/a
Estimated records:   4,000,000
Estimated raw size:  16.00 GB
Estimated DB size:   6.00 GB
Estimated import:    20.00 h
API limits:          Public probe failed; documented estimate.
Confidence:          low
Probed:              True
Recommended mode:    FOCUSED_FULL_DOWNLOAD
Reason:              Full breaches raw 16.0GB > 5.0GB, hours 20.0 > 8.0. A focused slice (~20% of full, scoped to target agencies and series) fits.
Next action:         Run a focused import: FEMA / DHS / CISA / HUD / FIMA / USACE / EPA / USDA / DOI / DOT / HHS / EDA / SBA, plus series 0089, 0301, 0343, 1109, 0020, 0101, 0110, 0300, 0501, 0560.
Notes:               Probe returned no usable count. Verify endpoint availability.
```

```text
Run timestamp:       2026-05-10T00:43:15Z
Dataset:             USAJOBS AnnouncementText
Endpoint:            GET /api/HistoricJoa/AnnouncementText
Date range:          n/a
Estimated records:   ?
Estimated raw size:  ?
Estimated DB size:   ?
Estimated import:    ?
API limits:          ~30000 bytes/record (est.); selective import only.
Confidence:          low
Probed:              False
Recommended mode:    SAMPLE_ONLY
Reason:              Record count could not be estimated; cannot guarantee a full pull will fit.
Next action:         Re-run recon with broader probes; meanwhile pull a representative sample.
Notes:               Pulled selectively (saved jobs, high-match jobs, recent jobs, RAG-flagged).
```

```text
Run timestamp:       2026-05-10T00:43:15Z
Dataset:             OPM Federal Workforce
Endpoint:            File downloads via data.opm.gov / FedScope
Date range:          n/a
Estimated records:   10,000,000
Estimated raw size:  2.00 GB
Estimated DB size:   0.80 GB
Estimated import:    50.00 h
API limits:          File download (no API rate limit).
Confidence:          low
Probed:              False
Recommended mode:    STAGED_DOWNLOAD
Reason:              Full dataset too large for one pass (~6.2 passes needed); each pass fits when sliced by date or agency, and the final DB (0.8 GB) fits.
Next action:         Stage in this order: last 12 months → last 5 years for target agencies/series → full history for those → full federal historical structured records if time permits → AnnouncementText only for selected/high-value records.
Notes:               Placeholder estimates. Inspect data.opm.gov downloads to refine.
```

## User approval gate

Before the importer downloads anything in `FULL_DOWNLOAD` or `FOCUSED_FULL_DOWNLOAD` mode, it confirms with the user via the Data Admin page (or CLI prompt). The approval is logged into `import_manifests.notes`. Without this approval, the importer refuses to start.
