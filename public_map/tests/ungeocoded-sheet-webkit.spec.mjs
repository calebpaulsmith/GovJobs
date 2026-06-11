// WebKit (real iOS Safari engine) test for the ungeocoded-postings sheet.
// From /browse: open Filters, find the "N postings not on the map" button at the
// bottom of the filter fields, open the swipe-away sheet, confirm it lists the
// ungeocoded postings (rich rows), then dismiss it by swiping the grabber down —
// all without a Svelte reactivity freeze.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/ungeocoded-sheet-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-ungeo]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });
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

const readOpen = () =>
	page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState.ungeocodedOpen);
const computeCount = () =>
	page.evaluate(async () => {
		const { ungeocodedJobIds } = await import('/src/lib/geo.ts');
		const m = (await import('/src/lib/store.svelte.ts')).mapState;
		const detail = Object.keys(m.allJobDetails || {}).length;
		if (detail === 0 || !m.allJobs) return -1; // bundle not loaded yet
		return ungeocodedJobIds(m.allJobDetails, m.allJobs).length;
	});

// Poll until both bundle files have loaded (count >= 0) rather than racing a
// fixed timeout — jobs.geojson is ~70k features and can take a few seconds.
let expectedCount = -1;
for (let i = 0; i < 30 && expectedCount < 0; i++) {
	expectedCount = await computeCount();
	if (expectedCount < 0) await page.waitForTimeout(500);
}
out(`bundle has ${expectedCount} ungeocoded posting(s)`);
if (expectedCount === 0) {
	out('SKIP — local bundle has no ungeocoded postings; cannot exercise the sheet');
	await browser.close();
	process.exit(0);
}

// 1) Open Filters, find the ungeocoded button at the bottom of the fields.
await page.locator('.filters-fab', { hasText: 'Filters' }).first().click();
await page.waitForSelector('.sheet[aria-label="Filters"]', { timeout: 8000 });
const ungeoBtn = page.locator('.sheet[aria-label="Filters"] .ungeo');
await ungeoBtn.scrollIntoViewIfNeeded();
check(await ungeoBtn.isVisible().catch(() => false), 'filter fields show the "N postings not on the map" button');
const btnText = (await ungeoBtn.innerText().catch(() => '')) || '';
check(btnText.includes(String(expectedCount)), `button shows the count ${expectedCount} (saw "${btnText.replace(/\s+/g, ' ').trim()}")`);

// 1b) Filters are respected: a keyword that matches nothing zeroes the count
// (the button hides), and clearing it brings the full set back.
await page.locator('.sheet[aria-label="Filters"] input[type="search"]').first().fill('zzqqxnomatch_filtercheck');
await page.waitForTimeout(400);
check(
	(await page.locator('.sheet[aria-label="Filters"] .ungeo').count()) === 0,
	'a no-match keyword filter narrows the ungeocoded count to 0 (button hidden)'
);
await page.locator('.sheet[aria-label="Filters"] input[type="search"]').first().fill('');
await page.waitForTimeout(400);
check(
	await page.locator('.sheet[aria-label="Filters"] .ungeo').isVisible().catch(() => false),
	'clearing the keyword restores the ungeocoded button'
);
await ungeoBtn.scrollIntoViewIfNeeded();

// 2) Click it → the swipe-away sheet opens and lists the ungeocoded postings.
await ungeoBtn.click();
await page.waitForTimeout(400);
check(await readOpen(), 'clicking the button sets ungeocodedOpen = true');
const sheet = page.locator('.sheet[aria-label="Postings not on the map"]');
check(await sheet.isVisible().catch(() => false), 'the ungeocoded sheet renders');
await page.waitForSelector('.sheet[aria-label="Postings not on the map"] .row-rich', { timeout: 8000 }).catch(() => {});
const rowCount = await page.locator('.sheet[aria-label="Postings not on the map"] .row-rich').count();
check(rowCount > 0, `the sheet lists rich job rows (${rowCount} shown)`);

// 3) Swipe the grabber down → the sheet dismisses.
const grab = page.locator('.sheet[aria-label="Postings not on the map"] .grab');
const box = await grab.boundingBox();
if (box) {
	const cx = box.x + box.width / 2;
	const cy = box.y + box.height / 2;
	await page.mouse.move(cx, cy);
	await page.mouse.down();
	for (let i = 1; i <= 6; i++) await page.mouse.move(cx, cy + i * 40, { steps: 1 });
	await page.mouse.up();
	await page.waitForTimeout(400);
	check((await readOpen()) === false, 'swiping the grabber down dismisses the sheet');
} else {
	out('SKIP swipe — grabber not found');
}

// 4) Reopen + dismiss via the × to confirm the close path too.
await page.locator('.filters-fab', { hasText: 'Filters' }).first().click().catch(() => {});
await page.waitForTimeout(200);
await page.locator('.sheet[aria-label="Filters"] .ungeo').click().catch(() => {});
await page.waitForTimeout(300);
await page.locator('.sheet[aria-label="Postings not on the map"] .close').click().catch(() => {});
await page.waitForTimeout(300);
check((await readOpen()) === false, 'the ✕ closes the sheet');

// Close the Filters sheet so its overlay no longer covers the map.
await page.locator('.sheet[aria-label="Filters"] .close').click().catch(() => {});
await page.waitForTimeout(300);

// 5) Reactivity sanity: the map still drives the bottom sheet afterward.
const marker = await page.evaluate(() => {
	const m = window.__ffMap;
	if (!m) return null;
	for (const f of m.queryRenderedFeatures(undefined, { layers: ['job-markers', 'job-clusters'] })) {
		if (f.geometry?.type !== 'Point') continue;
		const p = m.project(f.geometry.coordinates);
		return { x: Math.round(p.x), y: Math.round(p.y) };
	}
	return null;
});
if (marker) {
	const cbox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();
	await page.touchscreen.tap(marker.x + (cbox?.x ?? 0), marker.y + (cbox?.y ?? 0));
	await page.waitForTimeout(700);
	const ok = await page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState.browseSheetExpanded === true);
	check(ok, 'map still drives the sheet after opening/closing the ungeocoded list (no freeze)');
} else {
	out('SKIP freeze check — no marker in viewport');
}

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
