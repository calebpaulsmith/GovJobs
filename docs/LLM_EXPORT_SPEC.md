# LLM_EXPORT_SPEC.md

**Source of truth** for the LLM Project Export feature. Implementation queue lives in [ROADMAP.md](ROADMAP.md) under Phase 12. Decision context lives in [DECISIONS.md](DECISIONS.md) under ADR-0031 (and the narrowing of ADR-0022).

This spec is what another chat session needs to execute Phases 1, 2, and 3 without re-deriving anything from the conversation that produced it. Read it end-to-end before writing code.

---

## What this feature does

When the user finishes triaging jobs in GovJobs, they click **Export to LLM Project**. The app produces a single zip file the user drops into a Claude Project, ChatGPT Project, or generic chat. Inside the zip:

- One Markdown file per job (structured fields, summary, qualifications, scoring breakdown, hiring-climate signals, locality-adjusted pay, cost-of-living block).
- The user's résumé file(s) verbatim, in `resume/`.
- User notes from `applications` and `application_events`, in `notes/`.
- Token-budgeted Markdown bundles (`02_BUNDLE_*.md`) so even a small LLM project can hold the corpus.
- A three-format manifest (`01_SOURCE_MANIFEST.md` + `manifest.csv` + `manifest.json`).
- A target-specific instructions file the user pastes into Custom Instructions.
- A privacy notice the user reads first.

The user uploads the bundle by hand. The app never automates the upload.

---

## Two entry points

1. **Saved Jobs export** ([pages/2_Saved_Jobs.py](../pages/2_Saved_Jobs.py)): export every saved job, or a multi-select subset.
2. **Search Jobs export** ([pages/1_Search_Jobs.py](../pages/1_Search_Jobs.py)): export the current filter's results, capped at the chosen tier's file count and trimmed to top-N by score.

Both entry points open the same export modal and call the same `run_export(...)` backend.

---

## Output layout

The zip contains a single timestamped folder:

```
govjobs_<target>_<YYYYMMDD-HHMMSS>/
  00_START_HERE.md              # walkthrough: open Project, drag files, paste instructions, read privacy
  00_PRIVACY.md                 # what's in the bundle, what the LLM vendor will see
  00_INSTRUCTIONS_<TARGET>.md   # the block the user pastes into Custom Instructions
  00_OVERVIEW.md                # filter, date, counts, what each subfolder contains
  01_SOURCE_MANIFEST.md         # human-readable manifest (DOC_ID + path + tokens + status)
  manifest.csv                  # round-trip CSV
  manifest.json                 # round-trip JSON
  02_BUNDLE_001.md              # token-budgeted bundles
  02_BUNDLE_002.md
  ...
  jobs/
    DOC_0001__<control_number>__<safe_title>.md
    ...
  resume/
    <verbatim user résumé files>
  notes/
    DOC_NNNN__<safe_title>__notes.md
  data/
    closing_window_stats.csv    # per-job historical close-time medians
    opm_trends.csv              # per-agency accessions/separations trend
  assets/                       # only if a résumé is a PDF or image; FileSlicer-style
```

`assets/` and `data/` folders always exist (even if empty), matching FileSlicer's posture: downstream tooling can rely on them.

---

## Per-job Markdown (the "killer file")

One file per job under `jobs/`. Filename: `DOC_NNNN__<usajobs_control_number>__<safe_title>.md`. Body structure:

```markdown
---
DOC_ID: DOC_0001
SOURCE_FILE: DOC_0001__<control>__<safe-title>.md
SOURCE_PATH: jobs/DOC_0001__<control>__<safe-title>.md
ORIGINAL_EXTENSION: .md
USAJOBS_CONTROL_NUMBER: <number>
ANNOUNCEMENT_NUMBER: <number>
POSITION_ID: <number>
JOB_URL: https://www.usajobs.gov/job/<id>
---

# <Job Title>

**Agency:** <agency_name> (<agency_code>)
**Series:** <series>  ·  **Grade:** <grade range>  ·  **Pay plan:** <plan>
**Locations:** <one or more>
**Salary:** <min>–<max> (<locality_adjusted=true|false>)
**Hiring path:** <path(s)>
**Open:** <open_date> → **Close:** <close_date>  ·  <urgency_label>

## Why this is in your bundle
- Score: <0–100> (rule-based, [src/scoring.py](../src/scoring.py))
- Positive factors: <bullet list>
- Negative factors: <bullet list>
- Missing info: <bullet list>

## Hiring climate (signal, not prediction)
- Agency accessions trend (last 5 yr): <up/down/flat, +/- N per year>
- Agency attrition trend (last 5 yr): <up/down/flat>
- Series-level retirement-eligible share (FedScope, if available): <%>
- Median days-posted for similar (agency × series × grade): <N> days (n=<sample_size>)
- Total openings on this announcement: <total_openings>
- Source: OPM workforce data (<year>) + USAJOBS HistoricJoa (<window>)

## Locality-adjusted pay
| Grade | Step 1 | Step 5 | Step 10 |
| ----- | ------ | ------ | ------- |
| GS-13 | $X     | $Y     | $Z      |
...
Source: [src/pay_calculator.py](../src/pay_calculator.py), reference year <year>, locality <locality_code>

## Cost of living
- State RPP: <value> (BEA, <year>)
- County RPP: <value> if available, else "state fallback (approximate)"
- Pay-vs-COL index: <index> (100 = U.S. average; >100 = above-average purchasing power)

## Summary
<job_text.summary>

## Qualifications
<job_text.qualifications>

## Apply at
<JOB_URL>
```

Every numeric field cites its source. No probability claims. The `Hiring climate` block is labeled **signal, not prediction** in the section heading and again in the bundle's bundle-level header.

---

## Tier presets

Stored in `data/llm_tiers.json` with this shape:

```json
{
  "_schema_version": 1,
  "_verified_date": "2026-05-10",
  "_disclaimer": "These are guidance, not official platform limits. Vendors change them without notice. Verify before relying on them.",
  "presets": [
    {
      "id": "claude_pro",
      "label": "Claude Pro",
      "vendor": "claude",
      "max_files": 200,
      "max_total_mb": 30,
      "max_tokens_per_bundle": 120000,
      "notes": "Project knowledge supports up to ~200 files; per-chat context ~200k tokens."
    },
    {
      "id": "claude_max",
      "label": "Claude Max",
      "vendor": "claude",
      "max_files": 200,
      "max_total_mb": 30,
      "max_tokens_per_bundle": 160000,
      "notes": "Same project caps as Pro; more usage."
    },
    {
      "id": "chatgpt_plus",
      "label": "ChatGPT Plus",
      "vendor": "chatgpt",
      "max_files": 20,
      "max_total_mb": 512,
      "max_tokens_per_bundle": 90000,
      "notes": "File count per project varies by tier and changes."
    },
    {
      "id": "chatgpt_pro",
      "label": "ChatGPT Pro",
      "vendor": "chatgpt",
      "max_files": 20,
      "max_total_mb": 512,
      "max_tokens_per_bundle": 120000
    },
    {
      "id": "chatgpt_team",
      "label": "ChatGPT Team",
      "vendor": "chatgpt",
      "max_files": 20,
      "max_total_mb": 512,
      "max_tokens_per_bundle": 120000
    },
    {
      "id": "custom",
      "label": "Custom",
      "vendor": "generic",
      "max_files": 50,
      "max_total_mb": 50,
      "max_tokens_per_bundle": 60000,
      "notes": "Edit every knob."
    }
  ]
}
```

- The user picks a preset in the export modal; the modal shows every knob; the user can override any number for the run.
- A "save my custom settings" checkbox writes the override back to a user override layer (separate from the shipped defaults so an upgrade can refresh the defaults without overwriting personal numbers).
- The Settings page ([pages/8_Settings.py](../pages/8_Settings.py)) gets a **Tier presets** panel: review, edit, reset to ship defaults, see verified date.
- **Hard rule (FileSlicer compatibility):** every tier label, modal screen, and instruction file says these are *guidance, not official platform limits.* Quoting FileSlicer's CLAUDE.md verbatim is fine.

---

## Preflight ingestion

When the user clicks **Export**, the pipeline runs a *preflight* before assembling the bundle:

1. **Determine what's needed.** For every job in scope, compute the tuple `(agency_code, series, grade)`. Deduplicate.
2. **Check the cache.** A new SQLite table `llm_export_cache` (or reuse `import_manifests` with a new `kind`) records when each `(agency × series × grade)` slice was last fetched from HistoricJoa. Slices fetched within the freshness window (default 7 days) are reused.
3. **Fetch missing slices.** Targeted HistoricJoa calls per missing slice via `[src/usajobs_historic_api.py](../src/usajobs_historic_api.py)`. Trailing 24 months. Save raw responses to `data/raw/usajobs/historicjoa/<date>/...` per [CLAUDE.md](../CLAUDE.md) hard rule 4. Write to `import_manifests`. Same pattern as existing imports.
4. **OPM workforce.** Same approach for per-agency accessions/separations trend lookups, but [src/opm_data.py](../src/opm_data.py) is file-based — no network call. Just memo the answers per export.
5. **Time ceiling.** A wall-clock cap (default 5 min, configurable in Settings) stops the preflight if it runs long. Slices not fetched in time render in the per-job Markdown as "insufficient history (preflight timed out)."
6. **Skip button.** The Streamlit progress UI exposes a Skip button. Skipped slices render as "insufficient history (skipped by user)."
7. **Rate-limit posture.** Existing USAJOBS rate-limit handling in `src/usajobs_historic_api.py` applies. Don't add a parallel limiter.

The preflight is idempotent: re-running an export within the freshness window does not re-fetch anything.

---

## Filter-export volume gate

When the entry point is the Search Jobs filter:

1. Run the filter, count results.
2. Compare to the chosen tier's `max_files` (minus reserved slots: 1 for résumé, 1 for overview, 1 for manifest, 1 for instructions, 1 for closing-window CSV, 1 for OPM trend CSV — call it 6 reserved).
3. If results > available, trim to top-N by `match_scores.score`. Show the user the trim count *before* running.
4. The trimmed-out jobs are listed in `00_OVERVIEW.md` so the user knows what got cut.

Saved Jobs export skips this gate by default (the user picked them all individually). It still warns if the saved-job count exceeds `max_files`.

---

## "Résumé removed" mode

A checkbox in the export modal: **Include my résumé**. Default ON.

When unchecked:
- `resume/` is empty (still exists).
- Every per-job Markdown's `Why this is in your bundle` block omits any résumé-derived signals (today the rule-based scorer doesn't use résumé content, so this is mostly future-proofing).
- `00_OVERVIEW.md` states **"No résumé included"** in bold.
- The instruction template's "compare these jobs to the user's résumé" line is replaced with "the user has not shared their résumé in this bundle; ask them to paste relevant skills before comparing."

Use cases: sharing the bundle with someone else, testing on a different LLM without leaking the résumé, running future filter-recommendation flows that don't need a personal document.

---

## Privacy posture

`00_PRIVACY.md` lives at the top of every bundle. Content:

> ⚠️ **Privacy notice — read before uploading.**
>
> This bundle was assembled by GovJobs on your local machine. Until now, none of this data has left your computer.
>
> Uploading this bundle to Claude, ChatGPT, or any other LLM means that vendor will see and process **all of the following:**
> - Your résumé files (if you included them).
> - Every saved or filtered USAJOBS posting in this bundle, including its full text.
> - Your personal notes from the Application Tracker.
> - Your scoring breakdowns and the factors that produced them.
>
> The vendor's privacy policy applies from the moment you upload. GovJobs has no way to recall the data after it leaves your computer.
>
> If you do not want to share your résumé, re-run the export with **Include my résumé** unchecked.

The same warning is rendered as a yellow `st.warning(...)` in the export modal, with a checkbox **"I understand and want to continue"** that must be ticked before the Export button enables.

The export instructions file (`00_INSTRUCTIONS_<TARGET>.md`) repeats the warning at the top, before the Custom Instructions block.

---

## Instruction templates

### Claude Project (`00_INSTRUCTIONS_CLAUDE.md`)

```markdown
# Pasting these into a Claude Project

## Step 1 — Create a new Project in Claude
- Name it something like "GovJobs export <YYYY-MM-DD>".
- Open Project knowledge.

## Step 2 — Upload everything in this folder
- Drag every file in this folder (including subfolders) into Project knowledge.
- Claude will index them.

## Step 3 — Paste this block into Custom Instructions
> [...the actual instruction block. Default below; user-extended via the modal's free-text box.]
>
> You are reviewing federal job postings for the user. The DOC_<NNNN> identifiers are stable —
> always cite them when you reference a specific posting. The user's résumé is in resume/.
>
> Your priorities, in order:
> 1. Compare each posting to the user's résumé. Identify gaps and matches honestly.
> 2. Suggest concrete résumé edits — wording changes, accomplishments to surface, things to drop.
> 3. Surface postings the user has under-rated based on the scoring breakdown vs your read.
> 4. Flag postings where the hiring climate or closing-window stats suggest the user should
>    apply quickly or pause.
>
> Constraints:
> - Never invent experience the résumé does not contain.
> - When you are uncertain, say so. Do not bluff.
> - Cite DOC_<NNNN> for every claim about a posting.
> - When the user asks about pay, use the locality-adjusted pay table inside that posting's
>   Markdown — do not estimate.
>
> The hiring-climate block in each posting is signal, not prediction. Do not state probabilities.
```

### ChatGPT Project (`00_INSTRUCTIONS_CHATGPT.md`)

Same content, with paste-step instructions adjusted for ChatGPT Project's UI.

### Generic (`00_INSTRUCTIONS_GENERIC.md`)

For one-off chats. Tells the user to paste the manifest + the user's question into a single chat message.

The user's free-text addition from the export modal (Phase 2 UI) is appended to the instructions block under a `## Your custom guidance` heading.

---

## Module layout

New package: `src/llm_export/`

```
src/llm_export/
  __init__.py            # exports run_export, build_staging, load_tier_presets
  tiers.py               # JSON load/save; user override layer; built-in defaults
  staging.py             # build_staging(jobs, resume_versions, options) -> Path
  signals.py             # closing-window stats, OPM trend lookups, time-to-fill medians
  preflight.py           # ingestion preflight: detect missing slices, fetch, cache, time-cap
  bundler.py             # token-budget Markdown bundler (port from FileSlicer)
  manifest.py            # MD + CSV + JSON manifest writer (port from FileSlicer)
  instructions.py        # Claude / ChatGPT / generic instruction templates + privacy block
  pipeline.py            # run_export(target, tier, jobs, options) -> Path (zip)
```

Tests under `tests/test_llm_export.py` (single file is fine; one test class per module).

Reused, not duplicated:
- [src/database.py](../src/database.py) for SQLite access.
- [src/scoring.py](../src/scoring.py) for the per-job scoring breakdown.
- [src/pay_calculator.py](../src/pay_calculator.py) for locality-adjusted pay tables.
- [src/reference_data.py](../src/reference_data.py) for COL/RPP lookups.
- [src/opm_data.py](../src/opm_data.py) for OPM workforce trend reads.
- [src/usajobs_historic_api.py](../src/usajobs_historic_api.py) for HistoricJoa slice fetching during preflight.

Hard rule from [CLAUDE.md](../CLAUDE.md) hard rule 8: every new file in `src/` has a matching test in `tests/`. Use mocked HTTP. No real network in tests.

---

## API surface

```python
# src/llm_export/__init__.py
from .pipeline import run_export
from .tiers import load_tier_presets, save_tier_overrides

# src/llm_export/pipeline.py
def run_export(
    *,
    target: Literal["claude", "chatgpt", "generic"],
    tier_id: str,
    tier_overrides: dict | None,
    jobs: list[dict],                     # rows from a SQL query, not raw API JSON
    include_resume: bool,
    resume_version_ids: list[int] | None,  # which résumés to include; None = active
    include_col: bool = True,
    include_hiring_climate: bool = True,
    include_closing_window: bool = True,
    user_custom_guidance: str = "",        # appended to instructions
    preflight_time_ceiling_s: int = 300,
    output_dir: Path | None = None,        # defaults to ./llm_project_exports/
    progress_callback: Callable | None = None,
    dry_run: bool = False,                 # for tests; skip network
) -> ExportResult: ...
```

`ExportResult` is a dataclass with: `zip_path`, `staging_dir`, `included_count`, `trimmed_count`, `preflight_fetched_count`, `preflight_skipped_count`, `warnings`, `errors`.

---

## Streamlit UI contract

### Export modal (shared by both entry points)
- Target selector: Claude / ChatGPT / Generic.
- Tier preset selector: dropdown of presets + Custom; live-editable knobs (max_files, max_total_mb, max_tokens_per_bundle).
- Include résumé: checkbox + version multi-select (default: active version).
- Include cost-of-living context: checkbox.
- Include hiring-climate signals: checkbox.
- Include closing-window stats: checkbox.
- Free-text "what should the LLM do with this?" textarea (optional).
- Privacy notice block (yellow `st.warning`) + "I understand" checkbox.
- Volume preview when entry point is Search Jobs filter: "Filter has N jobs → tier supports M files (after reserves) → top M by score will be included."
- Run button (disabled until "I understand" is ticked).
- Progress UI: per-job rendering, preflight fetch progress, bundling, zip; Skip button for preflight.
- On completion: `st.download_button` returns the zip; success banner with included/trimmed/skipped counts.

### Settings page tab — Tier presets
- Review every shipped default and every user override.
- Edit any knob; save.
- "Reset to ship defaults" button.
- "Verified: YYYY-MM-DD" stamp visible.
- Free-text disclaimer: "These are guidance, not official platform limits."

---

## Test fixtures

`tests/fixtures/llm_export/`:
- 3 fake jobs across two agencies, one with a multi-location, one with no `job_text.summary` to exercise the empty-summary path.
- 2 fake résumé versions (.docx + .pdf bytes — minimal).
- A fake `import_manifests` row for one (agency × series × grade) slice so preflight skips it.
- A fake `import_manifests` row that's stale to exercise refetch.
- A fake OPM workforce slice.

Tests:
- `test_staging_layout`: every expected file exists in the staging dir.
- `test_per_job_markdown_shape`: front-matter, sections, COL block, hiring-climate block all present and labeled.
- `test_tier_presets_load_and_override`: round-trip JSON + user override layer.
- `test_volume_gate_trims_to_top_n`: filter with > tier `max_files` trims correctly and lists trimmed-out jobs in OVERVIEW.
- `test_preflight_skips_fresh_slices`: cached slice within freshness window is not refetched.
- `test_preflight_fetches_stale_slices`: stale slice triggers `usajobs_historic_api.fetch_*` (mocked).
- `test_preflight_time_ceiling`: synthetic slow fetch hits ceiling, remaining slices marked "insufficient history (preflight timed out)."
- `test_resume_removed_mode`: empty `resume/`, OVERVIEW says "No résumé included," instructions block adjusted.
- `test_privacy_notice_required`: pipeline raises if the "I understand" flag isn't passed.
- `test_zip_round_trip`: zip extracts to a folder identical to the staging dir.

Run with `pytest -q tests/test_llm_export.py`.

---

## Things explicitly out of scope

- NotebookLM target. Removed by user decision; do not re-add without an ADR.
- Auto-uploading to any LLM provider. Same posture as FileSlicer.
- Embeddings, vector store, in-app chat assistant. Those are V3.
- Schools, housing, commute, weather. Saved as future ideas in [ROADMAP.md](ROADMAP.md) but explicitly out of V2 scope.
- Series × agency level OPM trend in Phase 1 (agency-level only). Series-level is a Phase 3 polish item.
- Bulk HistoricJoa imports for the public map. The preflight is *targeted* — agency × series × grade slices for the trailing 24 months, never federal-wide. Public map's hard rule 22 still applies.

---

## Open questions deferred to implementation

These are intentionally not pre-decided; the implementing chat session resolves them and updates the spec:

1. Where exactly the `llm_export_cache` table lives — new table or new `kind` in `import_manifests`. Recommend: new `kind="llm_export_preflight"` rows in `import_manifests` with the slice tuple in `parameters_json`.
2. Whether résumé bytes are read from the file path stored in `resume_versions` or copied into the table itself. Recommend: keep the file-path approach (no schema migration), but verify the file exists before adding it to the bundle. If missing, surface the error in the modal.
3. Default `tier_id`. Recommend: `claude_pro` because Claude Project is the killer use case.
4. Whether to ship a "Sample export" button (1–3 jobs) for previewing the format. Recommend: yes, in Phase 3 polish.
5. Whether the export zip is also persisted to disk after the download or only streamed. Recommend: persisted under `./llm_project_exports/` so the user can re-download without re-running.
