# MAP_FEATURE_SPEC.md

Reusable feature sheet for the GovJobs GIS-style review map. This file is meant to be portable: it describes the map behavior, data contract, UI requirements, edge cases, and implementation notes so the same pattern can be reused for other datasets.

---

## Purpose

The map is a review workspace, not a dashboard chart. It should let the user inspect actual work-location points on detailed street/imagery basemaps, zoom into streets/buildings, open source records, and review records that cannot be plotted without losing them.

Current implementation:

- Streamlit page: `pages/4_State_Map.py`
- Data helpers: `src/ui_data.py`
- Location storage: `job_locations`
- Long-form popup text: `job_text`
- Source data: USAJOBS Search, USAJOBS HistoricJoa, OPM workforce files

---

## Core Principles

1. Use real coordinates only for point markers.
2. Do not geocode, invent, or approximate exact locations silently.
3. Preserve every named location from the source record.
4. Multi-location records may appear in multiple places.
5. Records without mappable coordinates must remain reviewable.
6. Remote-anywhere records must not be plotted as fake geographic points.
7. Popup content should support quick decision-making, not just show labels.
8. The map should occupy most of the page; supporting tables belong in expandable panels.

---

## Data Contract

### Required Point Fields

A mappable point row needs:

| Field | Required | Notes |
| --- | --- | --- |
| `record_id` / `job_id` | Yes | Stable source record ID. |
| `title` | Yes | Marker tooltip and popup title. |
| `latitude` | Yes for plotted points | Must come from source or an explicit geocoding process. |
| `longitude` | Yes for plotted points | Same precision rule as latitude. |
| `location_text` | Strongly preferred | Human-readable location for clicked point. |
| `all_locations` | Strongly preferred | Full list of named locations on the record. |
| `url` | Strongly preferred | Source-record link. |

### Recommended Popup Fields

| Field | Use |
| --- | --- |
| `agency` / owner | Context. |
| `series`, `grade`, category | Triage and filtering. |
| `summary` | Quick read of what the record is. |
| `qualifications` / requirements | Fit assessment. |
| `specialized_experience` | Prefer this over full qualifications when available. |
| `close_date` / deadline | Time sensitivity. |

### GovJobs Tables

| Table | Role |
| --- | --- |
| `jobs` | Fast summary/index row. |
| `job_locations` | Repeated locations, coordinates, states, remote indicator. |
| `job_text` | Summary, duties, qualifications, specialized experience. |
| `opm_workforce_records` | Separate workforce layer; not mixed with postings. |

---

## Location Rules

### Coordinate Rows

If a listing has latitude/longitude, plot it as a point.

If multiple listings share the exact same coordinate:

- Keep all records.
- Slightly separate the display coordinates so every marker remains clickable.
- Show the true source coordinate in the popup.
- Show a note that shared-coordinate records were visually separated.

### Multi-Location Listings

If a listing has multiple mappable work locations:

- Render one marker per coordinate.
- Keep a control to include/exclude multi-location postings.
- In every popup, show the complete `all_locations` list, not only the clicked location.

### No Latitude/Longitude

If a listing has named locations but no coordinates:

- Do not place a fake point.
- Keep the listing in an unmapped table.
- Show it only when the user is zoomed in enough to review the relevant area/state.
- Include all named source locations in the table.

Current GovJobs behavior:

- Current USAJOBS postings without lat/long go to `Unmapped Current Postings In View`.
- The table is zoom-scoped using state center points as a rough visibility gate.
- HistoricJoa rows generally have city/state/country but no exact coordinates; they are not exact point markers unless coordinates are present.

### Remote Anywhere

Remote-anywhere records:

- Do not get map points.
- Appear in a separate remote table.
- Are counted separately in map coverage metrics.

---

## Basemap Requirements

The map needs detailed, fast GIS-style basemaps:

- Esri World Street Map
- Esri World Imagery
- OpenStreetMap fallback

The user must be able to pan/zoom into streets and buildings. The primary point map uses Folium/Leaflet so it can return bounds and zoom state to Streamlit.

---

## UI Layout

The map should be the main object on the page.

Current GovJobs layout:

- Streamlit sidebar starts collapsed on the map page.
- Page uses full-width layout.
- Map height is large (`860px` currently).
- Filters live in a `Map Filters` popover.
- Metrics/tables live in a `Map Review Panel` popover.
- A small top caption summarizes map coverage without stealing map width.

Avoid:

- Permanent right-side tables beside the map.
- Large dashboard cards that shrink the map.
- Showing long instructions inside the map workspace.

---

## Popup Requirements

Each marker popup should include:

1. Large source-record button at the top.
2. Raw URL underneath the button so the link is visible even if browser/popup behavior is odd.
3. Title.
4. Agency/owner.
5. Clicked location.
6. Full named-location list.
7. Series/grade/category context.
8. Summary.
9. Qualifications or specialized-experience excerpt.
10. Shared-coordinate note when display points were separated.
11. True source coordinate.

Popup text should be clipped to readable excerpts. Full source text stays in the app detail view or source record.

---

## Coverage Metrics

The map review panel should expose:

| Metric | Meaning |
| --- | --- |
| Mapped work locations | Number of rendered coordinate rows. |
| Current mapped | Current source records with at least one non-remote coordinate point. |
| Current unmapped | Current non-remote records with no coordinate point. |
| Remote | Current records marked remote-anywhere. |

These metrics are intentionally record/point aware:

- `Mapped work locations` counts points.
- `Current mapped`, `Current unmapped`, and `Remote` count postings/records.

---

## Source-Specific Behavior

### USAJOBS Search

USAJOBS Search can return coordinates in `MatchedObjectDescriptor.PositionLocation[]`:

- `Latitude`
- `Longitude`
- `LocationName`
- `CityName`
- `CountrySubDivisionCode`
- `CountryCode`

The importer and migration/backfill should preserve these in `job_locations`.

### USAJOBS HistoricJoa

HistoricJoa commonly returns city/state/country but not coordinates. Treat those as named locations, not exact point data.

### OPM Workforce

OPM workforce data is analytically separate from USAJOBS postings. It can be shown as state-level workforce/accession/separation maps, but must not be blended with posting points without explicit labeling.

---

## Current Implementation Checklist

- [x] Store repeated locations in `job_locations`.
- [x] Store `latitude` and `longitude` when the source provides them.
- [x] Backfill Search coordinates from raw JSON for older imported rows.
- [x] Render a Folium/Leaflet map with street, imagery, and OSM layers.
- [x] Render one marker per mappable work location.
- [x] Separate exact-coordinate duplicate markers visually.
- [x] Preserve true source coordinate in popup.
- [x] Preserve and display full named-location list in popup.
- [x] Put source-record link at top of popup.
- [x] Include summary and qualifications/specialized-experience in popup.
- [x] Keep unmapped current postings in a zoom-scoped table.
- [x] Keep remote-anywhere postings in a separate table.
- [x] Collapse sidebar by default on map page.
- [x] Move filters and review tables into popovers.

---

## Replication Checklist

To reuse this feature for another domain:

1. Define the record table and repeated-location table.
2. Preserve source-provided coordinates exactly.
3. Preserve all named locations, even when they cannot be mapped.
4. Add a source URL field.
5. Add summary/description and requirements/detail text fields.
6. Build a point query with `all_locations` aggregated by record.
7. Build an unmapped query for records with named locations but no coordinates.
8. Build a remote/non-geographic query if the domain has non-location records.
9. Render coordinates only for true coordinate rows.
10. Use visual separation for duplicate coordinates.
11. Put filters in a compact popover or drawer.
12. Put tables and metrics in an expandable review panel.
13. Add tests for multi-location, duplicate-coordinate, unmapped, and remote cases.

---

## Open Refinements

- Add optional user-approved geocoding for named locations when a future use case explicitly wants approximate placement.
- Add selectable marker colors by score/status/source.
- Add bounds-aware mapped-point table, not just unmapped table.
- Add draw/select tools for geographic review.
- Add "open all jobs in this visible area" workflow.
- Add map screenshot/export.
