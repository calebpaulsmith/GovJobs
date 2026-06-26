# Public Map UX passthrough — web + phone (Stage 6′, 2026-06)

A focused review of the recent website surfaces (Browse mosaic + phone bottom
sheet) and the new overseas UI shipped in 5′.1–5′.5 (PRs #78/#79/#80). Scope per
the operator's 2026-06-20 direction: the **website is the product** (desktop +
phone); the Streamlit app is out of scope. Findings are prioritized; the
low-risk quick wins were applied in this pass (this PR). Larger items are logged
as follow-ups, not done blind.

## Method
- Code review of the masthead/nav, theme system, no-overlap layout, and the
  overseas additions (country filter, markers, JobCard DSSR block).
- Cross-checked against the test guards already in the repo: `layout.test.ts`
  (no-overlap at desktop/tablet/mobile reference viewports), the WebKit/iOS
  Playwright suite (`sheet-detent`, `browse-touch`, `desktop-mosaic`,
  `country-filter`, …), and the theme variable set in `routes/+layout.svelte`.

## Findings

### Fixed in this pass (low-risk quick wins)
1. **[P1] Overseas pay badge was illegible in light mode.**
   `JobCard.svelte` `.pay-status-overseas` hardcoded `color: #e7b870` (amber) —
   the only pay-status pill not using a theme variable. On the light panel
   background (`--c-panel` ≈ `#f8fafc`) amber-on-near-white is barely readable.
   **Fix:** use `var(--c-warn)` / `var(--c-warn-border)` like the sibling pills
   (`-approx`, `-withheld`, `-note`), which resolve to a dark amber (`#92400e`)
   in light mode and the bright amber in dark mode. Regression introduced in
   5′.3; now consistent with every other pill.
2. **[P1] Overseas hover-tip ("approximate — country centroid") illegible in
   light mode.** `Map.svelte` `.ff-tip-approx` hardcoded `color: #e0a44d` on the
   hover popup panel — same class of problem. **Fix:** `var(--c-warn)`.

### Verified OK — no action
3. **Localities pill is not a dead control.** It renders as
   `class="mode disabled" aria-disabled="true" title="Coming soon"` with muted
   styling — already honestly labeled, not a bare broken link. (The earlier
   "dead control" concern is resolved; leave until D.5.27 builds the screen.)
4. **Saved searches reachable on phone.** `layout.ts` positions the saved-search
   slot below the address search at mobile and the `address-open` shift keeps the
   two from overlapping; `layout.test.ts` asserts no coexisting-slot overlap at
   the mobile reference viewport. No phone-reachability gap.
5. **Country filter introduces no overlap.** The country `MultiSelect` lives in
   the in-flow `FilterFields` panel and the `.chip.ctry` chip is a normal-flow
   child of the (positioned) `ActiveFilterStrip`; neither adds fixed/absolute
   positioning. `.chip.ctry` inherits the theme-variable base `.chip` styles, so
   it is light/dark-safe. Reaches both `/map` (FilterPanel) and `/browse`
   (FilterSheet) — phone included (proven by `country-filter-webkit.spec.mjs`).
6. **Theme system is robust.** Pre-paint init (no flash), `data-theme` +
   CSS-variable application across panels/controls/overlays, and the basemap
   re-mounts on toggle to swap to the light/dark map style.
7. **Overseas markers are acceptable on both basemaps.** The `country_centroid`
   amber (`#e0a44d`, 0.7 opacity) is a deliberate "approximate" signal and is no
   less visible on the light basemap than the existing light-blue (`#7bd0f2`)
   exact-US markers, which are the shipped/accepted bar. Left as-is.

### Deferred (own follow-ups, not quick wins)
- **Localities screen (D.5.27).** Build the dedicated browse-and-drill UI, then
  enable the pill. Tracked in ROADMAP; out of scope here.
- **Country chip visual distinction.** Optional: give `.chip.ctry` a tint like
  `.chip.ag`/`.chip.geo`. Skipped to keep this pass minimal; the "Country" tag
  label already distinguishes it.

## Net
The overseas arc lands clean on the website; the only real defects were two
light-mode color regressions in my own 5′.3, both fixed here. No layout,
reachability, or phone defects found in the recent surfaces.
