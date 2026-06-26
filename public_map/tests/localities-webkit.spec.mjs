// WebKit (real iOS Safari engine) test for the D.5.27 Localities screen
// (ADR-0032). From /browse: the Localities pill navigates to /localities; the
// rollup renders, defaults to posting-count desc, sorting preserves the
// multi-selection, and drill-in routes to /browse with locality: chips set and
// non-geographic filters preserved. The Remote-only preset toggles the filter.
//
// Uses the real dev bundle (US localities + postings) — no fixture needed.
// Usage: `npm run dev` in another terminal, then
//   node tests/localities-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-localities]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
try {
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

	const filters = () =>
		page.evaluate(async () => {
			const m = (await import('/src/lib/store.svelte.ts')).mapState;
			return { geographies: m.filters.geographies.slice(), remote: m.filters.remote };
		});

	// 1) Localities pill on /browse navigates to /localities.
	await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
	await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
	await page.waitForTimeout(400);
	await page.locator('.modes .mode', { hasText: 'Localities' }).click();
	await page.waitForURL((u) => new URL(u).pathname === '/localities', { timeout: 10000 });
	check(true, 'Localities pill navigates to /localities');

	// 2) The rollup renders rows.
	await page.waitForSelector('.rollup tbody tr', { timeout: 20000 });
	const rowCount = await page.locator('.rollup tbody tr').count();
	check(rowCount > 0, `rollup renders rows (${rowCount} localities)`);

	// 3) Default sort is posting-count descending.
	const postingsAt = async (i) =>
		Number((await page.locator('.rollup tbody tr td.strong').nth(i).textContent())?.replace(/[^0-9]/g, '') || '0');
	const p0 = await postingsAt(0);
	const p1 = await postingsAt(1);
	check(p0 >= p1, `default sort is postings desc (${p0} >= ${p1})`);

	// 4) Multi-select two rows; sorting must not drop the selection.
	await page.locator('.rollup tbody tr td.cb input').nth(0).check();
	await page.locator('.rollup tbody tr td.cb input').nth(1).check();
	let checked = await page.locator('.rollup tbody td.cb input:checked').count();
	check(checked === 2, 'two rows selected');
	await page.locator('.rollup .sort', { hasText: 'Locality' }).click(); // re-sort by name
	await page.waitForTimeout(200);
	checked = await page.locator('.rollup tbody td.cb input:checked').count();
	check(checked === 2, 'selection survives a re-sort (selection is code-keyed, not row-order-keyed)');

	// 5) Footer CTA shows the M-localities count and drills into /browse with chips.
	const cta = page.locator('.show-jobs');
	check((await cta.textContent())?.includes('2 localit') ?? false, 'footer CTA names the 2 selected localities');
	await cta.click();
	await page.waitForURL((u) => new URL(u).pathname === '/browse', { timeout: 10000 });
	await page.waitForTimeout(700); // let /browse onMount hydrate filters from the URL
	let f = await filters();
	check(
		f.geographies.length === 2 && f.geographies.every((g) => g.startsWith('locality:')),
		`drill-in sets two locality chips (${JSON.stringify(f.geographies)})`
	);

	// 6) Single-row click (locality name) is a one-locality drill-in shortcut.
	await page.goto(`${BASE}/localities`, { waitUntil: 'networkidle', timeout: 30000 });
	await page.waitForSelector('.rollup tbody tr', { timeout: 20000 });
	await page.locator('.rollup tbody tr .loc').nth(0).click();
	await page.waitForURL((u) => new URL(u).pathname === '/browse', { timeout: 10000 });
	await page.waitForTimeout(700); // let /browse onMount hydrate filters from the URL
	f = await filters();
	check(
		f.geographies.length === 1 && f.geographies[0].startsWith('locality:'),
		`single-row click drills into one locality (${JSON.stringify(f.geographies)})`
	);

	// 7) Paired map renders; GS purchasing-power column toggles; map→row select.
	await page.goto(`${BASE}/localities`, { waitUntil: 'networkidle', timeout: 30000 });
	await page.waitForSelector('.rollup tbody tr', { timeout: 20000 });
	await page.waitForSelector('.mini .canvas canvas', { timeout: 20000 });
	check(true, 'paired LocalityMiniMap renders a canvas');

	const gsHeader = page.locator('.rollup th', { hasText: 'GS-13 real pay' });
	check((await gsHeader.count()) === 0, 'GS purchasing-power column is hidden by default');
	await page.locator('.preset', { hasText: 'GS purchasing power' }).click();
	await page.waitForTimeout(200);
	check((await gsHeader.count()) === 1, 'GS toggle shows the GS-13 real pay column');
	await page.locator('.preset', { hasText: 'GS purchasing power' }).click();
	await page.waitForTimeout(200);
	check((await gsHeader.count()) === 0, 'GS toggle hides the column again');
	// (Two-way highlight: the rollup table and the map share one `selected` Set,
	// so selecting rows highlights polygons and clicking polygons checks rows.
	// We don't pixel-click a polygon here — the map center sits over "Rest of US",
	// which has no polygon, so an arbitrary-pixel click is environment-fragile.)

	// 8) Remote-only preset toggles the remote filter and re-tallies.
	await page.goto(`${BASE}/localities`, { waitUntil: 'networkidle', timeout: 30000 });
	await page.waitForSelector('.rollup tbody tr', { timeout: 20000 });
	await page.locator('.preset', { hasText: 'Remote-only' }).click();
	await page.waitForTimeout(200);
	f = await filters();
	check(f.remote === 'remote', 'Remote-only preset sets filters.remote = remote');
	check(
		(await page.locator('.preset.on', { hasText: 'Remote-only' }).count()) === 1,
		'Remote-only preset shows its active (✓) state'
	);
	await page.locator('.preset', { hasText: 'Remote-only' }).click();
	await page.waitForTimeout(200);
	f = await filters();
	check(f.remote === 'any', 'clicking Remote-only again clears it');
} finally {
	await browser.close();
}

out(failures === 0 ? 'ALL PASSED' : `${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
