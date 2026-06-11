// WebKit test for the D.5.28 follow-on slices on the desktop mosaic:
//
//   A. Row ↔ marker crossfilter — hovering a Postings row publishes
//      mapState.hoveredJobId, points the `job-markers-hover` ring layer's
//      filter at that posting, and un-hovering clears both. (The marker →
//      row direction shares the same store field; asserting the store +
//      layer filter covers the contract without pixel-hunting a marker.)
//
//   B. In-list toolbar URL round-trip — the main Postings pane now renders
//      the sticky toolbar (search / sort / facets) in scoped mode; its state
//      lives in mapState.list and debounce-writes to the address bar as
//      lq / lsort / lf params; hydrating a URL with those params restores
//      the toolbar.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/toolbar-crossfilter-webkit.spec.mjs

import { webkit } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-tbxf]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
const ctx = await browser.newContext({
	viewport: { width: 1280, height: 900 },
	ignoreHTTPSErrors: true
});
const page = await ctx.newPage();

const BLANK = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
await ctx.route(/tile\.openstreetmap\.org\//, (r) =>
	r.fulfill({ status: 200, contentType: 'image/png', body: BLANK, headers: { 'access-control-allow-origin': '*' } })
);
await ctx.route(/events\.mapbox\.com/, (r) => r.fulfill({ status: 204, body: '' }));

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
await page.waitForSelector('.list-pane .row', { timeout: 30000 });

const store = () => page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState);

// ── A. Crossfilter ──────────────────────────────────────────────────────────
const firstRow = page.locator('.list-pane .row').first();
await firstRow.hover();
await page.waitForTimeout(300);
const hoveredId = await page.evaluate(
	async () => (await import('/src/lib/store.svelte.ts')).mapState.hoveredJobId
);
check(hoveredId !== null && hoveredId !== '', `hovering a row sets hoveredJobId (${hoveredId})`);
check(
	await firstRow.evaluate((el) => el.classList.contains('hover-linked')),
	'the hovered row carries the hover-linked class'
);
const ringFilter = await page.evaluate(() => {
	const m = window.__ffMap;
	if (!m || !m.getLayer('job-markers-hover')) return null;
	return JSON.stringify(m.getFilter('job-markers-hover'));
});
check(
	ringFilter !== null && ringFilter.includes(String(hoveredId)),
	`the hover-ring layer filter targets the hovered posting (${ringFilter?.slice(0, 80)})`
);
// Un-hover: move to the masthead.
await page.locator('.masthead .brand').hover();
await page.waitForTimeout(300);
const cleared = await page.evaluate(
	async () => (await import('/src/lib/store.svelte.ts')).mapState.hoveredJobId
);
check(cleared === null, 'leaving the row clears hoveredJobId');
const restFilter = await page.evaluate(() =>
	JSON.stringify(window.__ffMap?.getFilter('job-markers-hover') ?? null)
);
check(
	restFilter !== null && restFilter.includes('__no_hover__'),
	'the hover ring resets to the no-match filter'
);

// ── B. Toolbar round-trip ───────────────────────────────────────────────────
// The main (scoped/viewport) Postings pane now renders the sticky toolbar.
const toolbarSearch = page.locator('.list-pane .rich-search');
check(await toolbarSearch.isVisible(), 'the Postings pane renders the in-list toolbar');

await toolbarSearch.fill('specialist');
await page.waitForTimeout(700); // 200ms search debounce + 300ms URL debounce
let url = page.url();
check(url.includes('lq=specialist'), `in-list search lands in the URL (${url.slice(0, 90)}…)`);

await page.locator('.list-pane .facet-chip').first().click();
await page.waitForTimeout(600);
url = page.url();
check(url.includes('lf=gs_family'), 'facet chip lands in the URL as lf=');

await page.locator('.list-pane .rich-search-row select').selectOption('salary_high');
await page.waitForTimeout(600);
url = page.url();
check(url.includes('lsort=salary_high'), 'sort choice lands in the URL as lsort=');

const listState = await page.evaluate(
	async () => (await import('/src/lib/store.svelte.ts')).mapState.list
);
check(
	listState.search === 'specialist' &&
		listState.sort === 'salary_high' &&
		listState.facets.includes('gs_family'),
	`mapState.list carries the toolbar state (${JSON.stringify(listState)})`
);

// Fresh navigation with toolbar params → state hydrates back.
await page.goto(`${BASE}/browse?lq=analyst&lsort=title&lf=remote_eligible`, {
	waitUntil: 'networkidle',
	timeout: 60000
});
await page.waitForSelector('.list-pane .rich-search', { timeout: 30000 });
await page.waitForTimeout(500);
const hydrated = await page.evaluate(
	async () => (await import('/src/lib/store.svelte.ts')).mapState.list
);
check(
	hydrated.search === 'analyst' && hydrated.sort === 'title' && hydrated.facets.includes('remote_eligible'),
	`URL params hydrate mapState.list (${JSON.stringify(hydrated)})`
);
check(
	(await page.locator('.list-pane .rich-search').inputValue()) === 'analyst',
	'the search input shows the hydrated draft'
);
check(
	await page
		.locator('.list-pane .facet-chip', { hasText: 'Remote-eligible' })
		.first()
		.evaluate((el) => el.classList.contains('on')),
	'the hydrated facet chip renders active'
);

// Mobile sanity: at phone width the sheet's Postings panel gets the same
// toolbar with the same store state (no second write path).
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(600);
const sheetGrabber = page.locator('aside[aria-label="Area and postings"] .grabber');
if (await sheetGrabber.count()) {
	await sheetGrabber.click();
	await page.waitForTimeout(400);
	const sheetSearch = page.locator('aside[aria-label="Area and postings"] .rich-search');
	if (await sheetSearch.count()) {
		check(
			(await sheetSearch.inputValue()) === 'analyst',
			'the mobile sheet toolbar shows the same hydrated state'
		);
	} else {
		out('SKIP mobile toolbar check — Postings page not visible after expand');
	}
} else {
	out('SKIP mobile sanity — sheet not mounted');
}

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
