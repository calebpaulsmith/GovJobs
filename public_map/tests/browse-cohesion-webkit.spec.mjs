// WebKit smoke test for the D.6 mobile-cohesion surfaces (ADR-0035).
// Verifies, on the real iOS Safari engine, that from /browse alone a user can:
//   1. see the first-run welcome card on the Here panel,
//   2. see active-filter chips + Edit (opens FilterSheet) on the Postings panel,
//   3. save the current search by name (lands in localStorage saved_searches),
//   4. open "Go to" and geocode a ZIP offline (zip_centroids path, no network),
//   5. open the Pay Compare drawer from a JobCard.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/browse-cohesion-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-d6]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });
const page = await ctx.newPage();

const BLANK_PNG = Buffer.from(
	'iVBORw0KGgoAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
await ctx.route(/tile\.openstreetmap\.org\//, (route) =>
	route.fulfill({ status: 200, contentType: 'image/png', body: BLANK_PNG, headers: { 'access-control-allow-origin': '*' } })
);
await ctx.route(/events\.mapbox\.com/, (route) => route.fulfill({ status: 204, body: '' }));
// The ZIP path is offline; block external geocoders so a regression that
// reaches for them fails loudly instead of silently passing via network.
await ctx.route(/nominatim\.openstreetmap\.org|api\.mapbox\.com\/geocoding/, (route) =>
	route.fulfill({ status: 503, body: '' })
);

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(500);

// ── 1) Welcome card on first run (Here panel) ────────────────────────────
await page.locator('.grabber').click();
await page.waitForTimeout(900);
await page.locator('.seg button', { hasText: 'Here' }).click();
await page.waitForTimeout(400);
const welcomeVisible = await page.locator('.welcome').isVisible().catch(() => false);
check(welcomeVisible, 'first-run welcome card renders on the Here panel');

// Welcome's "See postings list" flips to Postings and dismisses.
await page.locator('.welcome-btn', { hasText: 'See postings list' }).click();
await page.waitForTimeout(400);
const onList = await page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState.browseSheetPage);
const flagSet = await page.evaluate(() => localStorage.getItem('fedfinder.public_map.browse_welcome.v1'));
check(onList === 'list' && flagSet === '1', 'welcome action flips to Postings and persists dismissal');

// ── 2) Task spine: chip strip + Edit on the Postings panel ───────────────
const stripVisible = await page.locator('.filters-row .strip').isVisible().catch(() => false);
check(stripVisible, 'docked ActiveFilterStrip renders in the Postings panel header');

await page.locator('.filters-row .head-btn', { hasText: 'Edit' }).click();
await page.waitForTimeout(400);
const filterSheetOpen = await page.locator('aside[aria-label="Filters"]').isVisible().catch(() => false);
check(filterSheetOpen, 'Edit opens the FilterSheet');
await page.locator('aside[aria-label="Filters"] .done').click();
await page.waitForTimeout(300);

// ── 3) Save current search ────────────────────────────────────────────────
await page.locator('.filters-row .head-btn', { hasText: 'Save' }).click();
await page.waitForTimeout(200);
await page.locator('.save-row input').fill('WebKit cohesion test');
await page.locator('.save-row .head-btn.primary').click();
await page.waitForTimeout(300);
const savedSearches = await page.evaluate(() => {
	const raw = localStorage.getItem('fedfinder.public_map.saved_searches.v1');
	return raw ? JSON.parse(raw).items.map((i) => i.name) : [];
});
check(savedSearches.includes('WebKit cohesion test'), `Save creates a named saved search (${JSON.stringify(savedSearches)})`);

// ── 4) Go to: offline ZIP geocode ────────────────────────────────────────
await page.locator('.fab-row button', { hasText: 'Go to' }).click();
await page.waitForTimeout(200);
await page.locator('.goto-panel input[type="search"]').fill('80202');
await page.locator('.goto-panel .search-row button', { hasText: 'Go' }).click();
await page.waitForSelector('.goto-panel .results button', { timeout: 10000 });
await page.locator('.goto-panel .results button').first().click();
await page.waitForTimeout(1200);
const addr = await page.evaluate(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	return m.lastAddressTarget ? { label: m.lastAddressTarget.label, provider: m.lastAddressTarget.provider } : null;
});
const gotoClosed = !(await page.locator('.goto-panel').isVisible().catch(() => false));
check(addr?.provider === 'zip_centroid' && gotoClosed, `ZIP geocode commits offline and closes the panel (${JSON.stringify(addr)})`);

// ── 5) Pay Compare from a JobCard ────────────────────────────────────────
// Collapse the sheet, tap a marker, then tap "$ Compare pay" on the card.
await page.evaluate(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	m.browseSheetExpanded = false;
	m.browseSheetFull = false;
});
await page.waitForTimeout(400);
// Tap an INDIVIDUAL marker (layer 'job-markers'), not a cluster — clusters
// open PointJobList, not JobCard. Zoom in until one is rendered.
let marker = null;
for (const zoom of [9, 11, 12]) {
	marker = await page.evaluate((z) => {
		const m = window.__ffMap;
		if (m.getZoom() < z) return null;
		const w = m.getCanvas().clientWidth;
		const h = m.getCanvas().clientHeight;
		for (const f of m.queryRenderedFeatures(undefined, { layers: ['job-markers'] })) {
			if (f.geometry?.type !== 'Point') continue;
			const p = m.project(f.geometry.coordinates);
			if (p.x > 20 && p.x < w - 20 && p.y > 20 && p.y < h - 80) {
				return { x: Math.round(p.x), y: Math.round(p.y) };
			}
		}
		return null;
	}, zoom);
	if (marker) break;
	await page.evaluate((z) => {
		const m = window.__ffMap;
		m.jumpTo({ center: m.getCenter(), zoom: z });
	}, zoom + 2);
	await page.waitForTimeout(900);
}
// Final scan at whatever zoom we landed on.
if (!marker) {
	marker = await page.evaluate(() => {
		const m = window.__ffMap;
		const w = m.getCanvas().clientWidth;
		const h = m.getCanvas().clientHeight;
		for (const f of m.queryRenderedFeatures(undefined, { layers: ['job-markers'] })) {
			if (f.geometry?.type !== 'Point') continue;
			const p = m.project(f.geometry.coordinates);
			if (p.x > 20 && p.x < w - 20 && p.y > 20 && p.y < h - 80) {
				return { x: Math.round(p.x), y: Math.round(p.y) };
			}
		}
		return null;
	});
}
if (!marker) {
	out('SKIP pay-compare — no marker in viewport');
} else {
	const cbox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();
	await page.touchscreen.tap(marker.x + (cbox?.x ?? 0), marker.y + (cbox?.y ?? 0));
	await page.waitForTimeout(900);
	const compareBtn = page.locator('.profile-btn', { hasText: 'Compare pay' });
	const btnVisible = await compareBtn.first().isVisible().catch(() => false);
	check(btnVisible, 'JobCard shows the Compare pay action');
	if (btnVisible) {
		await compareBtn.first().click();
		await page.waitForTimeout(600);
		const compareOpen = await page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState.compareOpen);
		check(compareOpen === true, 'Compare pay opens the comparator drawer on /browse');
	}
}

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
