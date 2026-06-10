// WebKit (real iOS Safari engine) test for radius search (D.5.30).
// From /browse: open "Go to", geocode a ZIP offline, confirm a radius chip is
// committed, the distance popover changes the radius, the remote toggle flips,
// and the postings list reflects the radius filter — without a reactivity freeze.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/radius-search-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-radius]', ...a);
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
// Force the offline ZIP path; block external geocoders so a regression fails loudly.
await ctx.route(/nominatim\.openstreetmap\.org|api\.mapbox\.com\/geocoding/, (r) => r.fulfill({ status: 503, body: '' }));

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(500);

const readRadii = () =>
	page.evaluate(async () => {
		const m = (await import('/src/lib/store.svelte.ts')).mapState;
		return m.filters.radii.map((c) => ({ miles: c.miles, includeRemote: c.includeRemote, label: c.label }));
	});

// 1) Open "Go to", geocode ZIP 80202 (Denver), commit → a radius chip appears.
await page.locator('.fab-row button', { hasText: 'Go to' }).click();
await page.waitForTimeout(200);
await page.locator('.goto-panel input[type="search"]').fill('80202');
await page.locator('.goto-panel .search-row button', { hasText: 'Go' }).click();
await page.waitForSelector('.goto-panel .results button', { timeout: 10000 });
await page.locator('.goto-panel .results button').first().click();
await page.waitForTimeout(800);

let radii = await readRadii();
check(radii.length === 1 && radii[0].miles === 50 && radii[0].includeRemote === true,
	`committing a geocode result adds one 50 mi radius chip (${JSON.stringify(radii)})`);

// Open the Postings panel so the docked chip strip + list are visible.
await page.locator('.grabber').click();
await page.waitForTimeout(700);
await page.locator('.seg button', { hasText: 'Postings' }).click();
await page.waitForTimeout(500);

const chip = page.locator('.chip.radius').first();
check(await chip.isVisible().catch(() => false), 'radius chip renders in the Postings panel chip strip');

// 2) Change the radius via the distance popover (50 → 25).
await page.locator('.chip.radius .radius-dist').first().click();
await page.waitForTimeout(150);
await page.locator('.radius-pop button', { hasText: '25 mi' }).first().click();
await page.waitForTimeout(400);
radii = await readRadii();
check(radii[0]?.miles === 25, `distance popover changes the radius to 25 (${JSON.stringify(radii)})`);

// 3) Toggle anywhere-remote off.
await page.locator('.chip.radius .radius-remote').first().click();
await page.waitForTimeout(300);
radii = await readRadii();
check(radii[0]?.includeRemote === false, 'remote toggle flips includeRemote to false');

// 4) The radius summary line appears in the rich toolbar.
const summary = await page.locator('.radius-summary').first().isVisible().catch(() => false);
check(summary, 'rich toolbar shows the "within N mi of …" summary');

// 5) Remove the chip via × → radii empty, no freeze (list still responds).
await page.locator('.chip.radius .radius-x').first().click();
await page.waitForTimeout(300);
radii = await readRadii();
check(radii.length === 0, 'the × removes the radius chip');

// Reactivity sanity: tap a marker still drives the sheet after all that.
const marker = await page.evaluate(() => {
	const m = window.__ffMap;
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
	const ok = await page.evaluate(async () => {
		const m = (await import('/src/lib/store.svelte.ts')).mapState;
		return m.browseSheetExpanded === true;
	});
	check(ok, 'map still drives the sheet after radius interactions (no freeze)');
} else {
	out('SKIP freeze check — no marker in viewport');
}

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
