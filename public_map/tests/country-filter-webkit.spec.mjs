// WebKit (real iOS Safari engine) test for the country scope filter (overseas
// US-fed jobs, Stage 5'.4). From /browse on a phone: open the FilterSheet,
// confirm the Country multi-select renders, add a country chip, and verify the
// filter actually narrows the corpus, round-trips to the URL, shows a chip in
// the ActiveFilterStrip, and clears cleanly — without a reactivity freeze.
//
// The local dev bundle has no overseas postings and no countries.json, so we
// write a tiny 2-country catalog into static/data for the test's duration
// (WebKit does NOT reliably intercept same-origin /data/* requests via
// ctx.route, so a real served file is the dependable path), then assert the
// *effect*: filtering to "IT" yields 0 of an all-US corpus, and removing it
// restores the full set. The wiring — not fabricated overseas data — is the SUT.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/country-filter-webkit.spec.mjs

import { webkit, devices } from 'playwright';
import { writeFileSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-country]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

// --- fixture: a 2-country catalog so the country control un-hides (it renders
// only when countries.json offers more than one country). Back up any existing
// file and restore it on teardown so we never clobber a real exported bundle.
const COUNTRIES_PATH = fileURLToPath(new URL('../static/data/countries.json', import.meta.url));
const hadFile = existsSync(COUNTRIES_PATH);
const backup = hadFile ? readFileSync(COUNTRIES_PATH) : null;
writeFileSync(
	COUNTRIES_PATH,
	JSON.stringify([
		{ code: 'US', name: 'United States', postings: 6493 },
		{ code: 'IT', name: 'Italy', postings: 1 }
	])
);
const restoreFixture = () => {
	if (hadFile) writeFileSync(COUNTRIES_PATH, backup);
	else rmSync(COUNTRIES_PATH, { force: true });
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

	// Skip the first-run welcome card so it can't intercept taps.
	await ctx.addInitScript(() => {
		try {
			localStorage.setItem('fedfinder.public_map.browse_welcome.v1', '1');
		} catch {}
	});

	await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
	await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
	await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 }).catch(() => {});
	await page.waitForTimeout(500);

	const readCountries = () =>
		page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState.filters.countries.slice());
	const filteredCount = () =>
		page.evaluate(async () => {
			const m = (await import('/src/lib/store.svelte.ts')).mapState;
			const { filterJobDetails } = await import('/src/lib/filters.ts');
			return filterJobDetails(Object.values(m.allJobDetails), m.filters).length;
		});

	const baseline = await filteredCount();
	check(baseline > 0, `corpus is non-empty before filtering (${baseline} postings)`);

	// Open the Postings panel, then Edit → FilterSheet.
	await page.locator('.grabber').click();
	await page.waitForTimeout(900);
	await page.locator('.seg button', { hasText: 'Postings' }).click();
	await page.waitForTimeout(400);
	await page.locator('.filters-row .head-btn', { hasText: 'Edit' }).click();
	await page.waitForTimeout(400);

	const sheet = page.locator('aside[aria-label="Filters"], .sheet[aria-label="Filters"]').first();
	check(await sheet.isVisible().catch(() => false), 'Edit opens the FilterSheet');

	const countryMs = sheet
		.locator('.ms')
		.filter({ has: page.locator('.field-label', { hasText: 'Country' }) });
	check(await countryMs.isVisible().catch(() => false), 'Country multi-select renders when >1 country is offered');

	// Add "Italy".
	await countryMs.locator('input.search').fill('Italy');
	await page.waitForTimeout(200);
	await countryMs.locator('.option', { hasText: 'Italy' }).first().click();
	await page.waitForTimeout(400);

	check(JSON.stringify(await readCountries()) === JSON.stringify(['IT']), 'selecting Italy sets filters.countries=[IT]');
	const itCount = await filteredCount();
	check(itCount === 0, `country=IT narrows the all-US corpus to 0 (got ${itCount}) — the filter is actually applied`);

	const urlHasCountry = await page.evaluate(() => new URLSearchParams(location.search).getAll('country').includes('IT'));
	check(urlHasCountry, 'the country filter round-trips to the URL (country=IT)');

	// Close the sheet → the ActiveFilterStrip shows a Country chip.
	await sheet.locator('.done, .close').first().click();
	await page.waitForTimeout(300);
	const chip = page.locator('.chip.ctry').first();
	check(await chip.isVisible().catch(() => false), 'a Country chip renders in the ActiveFilterStrip');
	check((await chip.textContent())?.includes('Italy') ?? false, 'the chip labels the country by name (Italy)');

	// Remove the chip → corpus restored, URL cleared.
	await chip.click();
	await page.waitForTimeout(400);
	check((await readCountries()).length === 0, 'removing the chip clears filters.countries');
	const restored = await filteredCount();
	check(restored === baseline, `corpus is restored after removing the country chip (${restored} == ${baseline})`);
	const urlCleared = await page.evaluate(() => new URLSearchParams(location.search).getAll('country').length === 0);
	check(urlCleared, 'the country param is removed from the URL after clearing the chip');
} finally {
	await browser.close();
	restoreFixture();
}

out(failures === 0 ? 'ALL PASSED' : `${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
