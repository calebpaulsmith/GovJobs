# FEATURE_FEASIBILITY_MATRIX.md

Each Version-1 feature, the data it depends on, blockers, and a feasibility verdict. "Feasibility" assumes the recon step has not yet run; many `medium` ratings will move to `high` once we confirm dataset sizes and API limits.

Legend:
- **Feasibility:** `high` (clear path) / `medium` (depends on recon) / `low` (likely deferred to V2/V3).
- **Data needed:** which datasets must be present.
- **Blocker:** the thing that, if not solved, prevents the feature from shipping.

---

## V1 features

| Feature | Data needed | Blocker | Feasibility | Notes |
| --- | --- | --- | --- | --- |
| Current USAJOBS search | Search API live | API key | high | Lightweight, paginated. |
| Save job + tags + notes + status | jobs, saved_jobs, job_notes, job_tags | DB schema | high | Pure local CRUD. |
| Match score (rule-based) | jobs (+ optional job_text) | scoring rules | high | Transparent, deterministic. |
| Trend chart: postings over time | Historic JOA backfill | Recon mode | medium | "Medium" only because the historic pull may take time; the chart itself is trivial. |
| Trend chart: postings by agency / series / grade / state / remote share / salary | Historic JOA backfill | Recon mode | medium | Same caveat. |
| State map of postings | Historic JOA + state normalization | Reliable state field | medium | Multi-location and remote postings handled separately to avoid distortion. |
| State map of OPM workforce | OPM workforce dataset | OPM ETL | medium | Map labels source explicitly. |
| Scorecards (hottest agencies / series / locations / grades) | Historic + current | Backfill present | medium | Hotness formula in `docs/PRODUCT_SPEC.md`. |
| Local alerts (saved-search match, high score, closing soon, reposted) | jobs + saved_searches + match_scores | Email/push deferred | high | Implemented as manual in-app alerts with CSV export; no email in V1. |
| Data Admin page | manifests + raw_api_responses | DB | high | Surfaces what already exists. |
| Resumable historic import | manifests + raw responses | Pagination contract | high | Manifest-driven. |
| Announcement Text — selective import | AnnouncementText API | Selection criteria | high | Pulled only for saved / high-score / sample jobs. |
| Excel / CSV export | Pandas + openpyxl | None | high | Trivial once data is in DB. |

---

## V2 features

| Feature | Data needed | Blocker | Feasibility | Notes |
| --- | --- | --- | --- | --- |
| Application Tracker | saved_jobs + applications table | UI design | high | Add `pages/6_Application_Tracker.py`. |
| Resume Version Manager | local file storage | File-storage decisions | medium | Stores filenames + versions only, no parsing. |
| Repost Detector | jobs + simple text-similarity | text similarity tuning | medium | MinHash / Jaccard on title+series+text-hash. |
| Closing-window analytics | Historic JOA with reliable close_date | Historic backfill | medium | Median-days-open by series/grade. |
| Postings vs. accessions comparison | USAJOBS Historic + OPM accessions | Joinable agency / series codes | medium | Always footnoted: postings ≠ hires. |
| Locality salary normalization | jobs + GS locality table | Static GS locality lookup | high | Lookup table maintained in `data/processed/`. |
| Improved hotness model | Historic backfill + saved searches | Math review | medium | Layer growth rates and remote share. |
| PDF export | reportlab or wkhtmltopdf | extra dep | medium | Optional. |
| Per-agency notes | new `agency_notes` table | DB | high | |
| Career-ladder categorization | jobs.series + grade tagging | manual / rule definitions | medium | Explicit ladder rules per series. |

---

## V3 features (AI / RAG)

| Feature | Data needed | Blocker | Feasibility | Notes |
| --- | --- | --- | --- | --- |
| Vector store of `job_text` | `job_text` + embeddings | embedding model + storage | medium | Chroma / FAISS / sqlite-vss decision. Embeddings cost money — selectively embed. |
| Resume-to-announcement matcher | resume text + `job_text` + embeddings | LLM access + cost budget | medium | "Must not invent experience." Output: score, evidence, missing keywords. |
| Hidden-opportunity finder | `job_text` + embeddings | same as above | medium | Surfaces analyst / planner / coordinator titles that match resume semantically. |
| Application strategy generator | `job_text` + resume | LLM access | medium | Prompts cite announcement language verbatim. |

---

## Out of scope (any version)

| Feature | Why not |
| --- | --- |
| Auto-apply to jobs | Harms the user and violates terms. |
| Browser scraping | We use official APIs only. |
| Multi-tenant SaaS | Not a goal. |
| Live LLM scoring in V1 | Opaque, costly, unnecessary. |
