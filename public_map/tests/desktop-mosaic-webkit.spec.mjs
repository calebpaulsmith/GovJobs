// WebKit test for the /browse desktop mosaic (D.5.28).
//
// At ≥ 1024 px /browse renders the mosaic grid — map pane top-left, Here pane
// (BrowseHerePanel) top-right, Postings pane (BrowsePostingsPanel) across the
// bottom — instead of the mobile bottom sheet. This spec drives a 1280×900
// desktop viewport and asserts:
//   1. the panes render and the BrowseSheet is NOT mounted;
//   2. the Here pane shows the SmallestAreaCard fallback when nothing is
//      selected;
//   3. clicking a Postings row opens the JobCard in the Here pane WITHOUT
//      moving the map (operator decision 2026-06-11: card only, no flyTo);
//   4. the Edit button opens the shared FilterSheet;
//   5. crossing the breakpoint swaps mosaic ↔ sheet live (matchMedia listener);
//   6. reactivity survives the whole sequence (no state_unsafe_mutation
//      freeze) — a second row click still updates the Here pane.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/desktop-mosaic-webkit.spec.mjs

import { webkit } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-mosaic]', ...a);
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

// 1) Mosaic panes render; the mobile bottom sheet is not mounted.
check(await page.locator('.content.mosaic').isVisible(), 'content renders in mosaic mode at 1280px');
check(await page.locator('.here-pane').isVisible(), 'Here pane renders');
check(await page.locator('.list-pane').isVisible(), 'Postings pane renders');
check(
	(await page.locator('aside[aria-label="Area and postings"]').count()) === 0,
	'BrowseSheet is not mounted on desktop'
);

// Panes must not overlap the map pane (grid construction sanity).
const mapBox = await page.locator('.content.mosaic .map-frame').boundingBox();
const hereBox = await page.locator('.here-pane').boundingBox();
const listBox = await page.locator('.list-pane').boundingBox();
const overlaps = (a, b) =>
	a && b && !(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y);
check(!overlaps(mapBox, hereBox), 'map pane and Here pane do not overlap');
check(!overlaps(mapBox, listBox), 'map pane and Postings pane do not overlap');
check(!overlaps(hereBox, listBox), 'Here pane and Postings pane do not overlap');
check(mapBox && hereBox && mapBox.x < hereBox.x, 'map is left of the Here pane');
check(listBox && mapBox && listBox.y > mapBox.y, 'Postings pane sits below the top band');

// 2) Nothing selected → Here pane shows the SmallestAreaCard fallback
// (the first-run welcome card may sit above it — both are fine).
await page.waitForSelector('.here-pane section.tab-here', { timeout: 15000 });
check(await page.locator('.here-pane section.tab-here').isVisible(), 'Here pane shows SmallestAreaCard when nothing is selected');

// D.5.28 area pulse: once the bundle loads, the band computes client-side and
// flips from placeholder to live; the Open-postings cell shows a real count.
await page.waitForSelector('.here-pane .pulse-band[data-status="live"]', { timeout: 30000 }).catch(() => {});
check(
	(await page.locator('.here-pane .pulse-band').getAttribute('data-status')) === 'live',
	'pulse band is live (computed from the bundle, not placeholder)'
);
const openCell = await page.locator('.here-pane .pulse-cell .pulse-value').first().innerText();
check(/^[\d,]+$/.test(openCell.trim()), `Open-postings pulse cell shows a number (${openCell.trim()})`);
const pulseInStore = await page.evaluate(
	async () => (await import('/src/lib/store.svelte.ts')).mapState.areaPulse
);
check(
	pulseInStore !== null && typeof pulseInStore.openPostings === 'number',
	'mapState.areaPulse is published for the JobList annotation'
);

// Wait for the postings list to populate (jobs.geojson is large).
await page.waitForSelector('.list-pane .row', { timeout: 30000 });
const rowCount = await page.locator('.list-pane .row').count();
check(rowCount > 0, `Postings pane lists job rows (${rowCount} shown)`);

// 3) Row click → JobCard in the Here pane, map stays put (no flyTo).
const centerBefore = await page.evaluate(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	return JSON.stringify(m.viewport.center ?? null);
});
await page.locator('.list-pane .row').first().click();
await page.waitForTimeout(600);
const selected = await page.evaluate(
	async () => (await import('/src/lib/store.svelte.ts')).mapState.selectedFeature !== null
);
check(selected, 'row click sets mapState.selectedFeature');
check(
	await page.locator('.here-pane .profile-actions').isVisible().catch(() => false),
	'Here pane shows the JobCard (Save/Hide actions present)'
);
const centerAfter = await page.evaluate(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	return JSON.stringify(m.viewport.center ?? null);
});
check(centerBefore === centerAfter, 'map viewport did not move on row click (card only, no flyTo)');

// 4) Edit opens the shared FilterSheet.
await page.locator('.list-pane .head-btn', { hasText: 'Edit' }).click();
await page.waitForTimeout(400);
check(
	await page.locator('.sheet[aria-label="Filters"]').isVisible().catch(() => false),
	'Edit opens the shared FilterSheet'
);
// FilterSheet closes via the ✕ / overlay / Done — it has no Escape handler.
await page.locator('.sheet[aria-label="Filters"] .close').click();
await page.waitForTimeout(400);
check(
	(await page.locator('.sheet[aria-label="Filters"]').count()) === 0,
	'the ✕ closes the FilterSheet'
);

// 5) Crossing the breakpoint live: shrink → sheet appears, panes unmount;
// grow → mosaic returns.
await page.setViewportSize({ width: 800, height: 900 });
await page.waitForTimeout(600);
check(
	await page.locator('aside[aria-label="Area and postings"]').isVisible().catch(() => false),
	'shrinking below 1024px mounts the BrowseSheet'
);
check((await page.locator('.here-pane').count()) === 0, 'panes unmount below the breakpoint');
await page.setViewportSize({ width: 1280, height: 900 });
await page.waitForTimeout(600);
check(await page.locator('.here-pane').isVisible().catch(() => false), 'growing back restores the mosaic');

// 6) Reactivity is still alive after the mode round-trip: clicking a
// different row updates the Here pane card title.
const titleOf = () => page.locator('.here-pane h2').first().innerText().catch(() => '');
const before = await titleOf();
const second = page.locator('.list-pane .row').nth(1);
if ((await second.count()) > 0) {
	await second.click();
	await page.waitForTimeout(600);
	const after = await titleOf();
	check(after !== '' && after !== before, `second row click updates the Here pane ("${before.slice(0, 30)}" → "${after.slice(0, 30)}")`);
} else {
	out('SKIP second-row check — only one row in the local bundle');
}

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
