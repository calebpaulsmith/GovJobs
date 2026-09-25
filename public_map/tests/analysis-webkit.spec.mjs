// WebKit (iOS Safari engine) spec for ADR-0039: Browse finds jobs, Analysis
// analyzes places.
//
//   Browse (mobile): no Here tab; a picked row opens its card over the list
//   with "‹ Back to postings"; a county-scoped list matches by polygon and
//   offers "Analyze this area →".
//   Analysis: the pill lands on the level/area matching where the Browse map
//   was; the level picker keeps you in the same place; the typeahead picks
//   any area; ?area= round-trips; /localities redirects.
//   Desktop: the top-right pane holds job details only.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/analysis-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-analysis]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const BLANK_PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
async function newPage(browser, opts) {
	const ctx = await browser.newContext(opts);
	await ctx.route(/tile\.openstreetmap\.org\//, (r) =>
		r.fulfill({ status: 200, contentType: 'image/png', body: BLANK_PNG, headers: { 'access-control-allow-origin': '*' } })
	);
	await ctx.route(/events\.mapbox\.com/, (r) => r.fulfill({ status: 204, body: '' }));
	const page = await ctx.newPage();
	const errors = [];
	// Mapbox telemetry to events.mapbox.com fails CORS under the placeholder
	// token — known harness noise (see sheet-detent spec), not an app error.
	page.on('pageerror', (e) => {
		if (!/events\.mapbox\.com/.test(e.message)) errors.push(e.message);
	});
	return { page, errors };
}
async function waitForMap(page) {
	await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
	await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
	await page.waitForTimeout(600);
}

const browser = await webkit.launch();

// ---------------------------------------------------------------- mobile
{
	const { page, errors } = await newPage(browser, { ...devices['iPhone 13'] });
	await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
	await waitForMap(page);

	const pills = await page.locator('nav.modes .mode:visible').allTextContents();
	check(pills.join('|') === 'Browse|Analysis', `mobile masthead reads Browse | Analysis (got ${pills.join('|')})`);

	await page.locator('.grabber').click();
	await page.waitForTimeout(800);
	check((await page.locator('.sheet .seg').count()) === 0, 'sheet has no Here/Postings tabs');
	check((await page.locator('.sheet .postings').count()) === 1, 'sheet shows the Postings list');

	// Pick a row → detail view with back.
	await page.locator('.sheet .postings li button').first().click();
	await page.waitForTimeout(500);
	check((await page.locator('.sheet .back').count()) === 1, 'picking a row opens a detail view with "Back to postings"');
	check((await page.locator('.sheet .postings').count()) === 0, 'the list is replaced by the job card while open');
	await page.locator('.sheet .back').click();
	await page.waitForTimeout(400);
	check((await page.locator('.sheet .postings').count()) === 1, 'Back returns to the Postings list');

	// County-scoped list (as a county tap sets it): polygon match + Analyze link.
	const countyRows = await page.evaluate(async () => {
		const { mapState } = await import('/src/lib/store.svelte.ts');
		const fc = await (await fetch('/data/counties.geojson')).json();
		const f = fc.features.find((x) => x.properties.fips === '08031');
		mapState.listView = { scope: 'county', code: '08031', label: 'Denver County, CO', geometry: f.geometry };
		await new Promise((r) => setTimeout(r, 600));
		return {
			rows: document.querySelectorAll('.sheet .postings li').length,
			href: document.querySelector('.sheet .analyze-link')?.getAttribute('href') ?? null
		};
	});
	check(countyRows.rows > 0, `a county-scoped list matches postings by polygon (${countyRows.rows} rows)`);
	check(countyRows.href === '/analysis?area=county%3A08031', `list offers "Analyze this area" (${countyRows.href})`);
	await page.evaluate(async () => {
		const { mapState } = await import('/src/lib/store.svelte.ts');
		mapState.listView = null;
	});

	// Zoom the Browse map onto Denver at county zoom, then open Analysis.
	await page.evaluate(() => window.__ffMap.jumpTo({ center: [-104.99, 39.74], zoom: 9 }));
	await page.waitForTimeout(800);
	await page.locator('nav.modes .mode', { hasText: 'Analysis' }).click();
	await page.waitForURL((u) => u.pathname === '/analysis', { timeout: 15000 });
	await page.waitForSelector('.area-analysis h2', { timeout: 30000 });
	const onLevel = () => page.locator('.levels .level.on').textContent();
	const title = () => page.locator('.area-analysis h2').textContent();
	check((await onLevel()) === 'County', `Analysis opens at the County level from a county-zoom map (got ${await onLevel()})`);
	check(/Denver/.test(await title()), `…on the county under the map center (got ${await title()})`);
	check(/area=county%3A08031|area=county:08031/.test(page.url()), `URL carries the area (${page.url()})`);

	await page.locator('.levels .level', { hasText: 'Metro' }).click();
	await page.waitForTimeout(300);
	check(/Denver-Aurora/.test(await title()), `switching to Metro stays in place (${await title()})`);
	await page.locator('.levels .level', { hasText: 'State' }).click();
	await page.waitForTimeout(300);
	check((await title()) === 'Colorado', `switching to State stays in place (${await title()})`);
	await page.locator('.levels .level', { hasText: 'Locality' }).click();
	await page.waitForTimeout(300);
	check(/Denver/.test(await title()), `switching to Locality stays in place (${await title()})`);

	// Typeahead: pick a county elsewhere.
	await page.locator('.levels .level', { hasText: 'County' }).click();
	const search = page.locator('.area-search input');
	await search.fill('Travis');
	await page.locator('.matches button', { hasText: 'Travis County, TX' }).click();
	await page.waitForTimeout(400);
	check((await title()) === 'Travis County, TX', `the area picker selects any county (${await title()})`);
	await page.locator('.levels .level', { hasText: 'State' }).click();
	await page.waitForTimeout(300);
	check((await title()) === 'Texas', `the picked county becomes the new anchor (${await title()})`);

	const pulse = await page.locator('.area-analysis .pulse-band').getAttribute('data-status');
	check(pulse === 'live', `pulse band is live for the chosen area (${pulse})`);

	// Nationwide + the locality comparison section.
	await page.locator('.levels .level', { hasText: 'Nationwide' }).click();
	await page.waitForTimeout(300);
	check((await title()) === 'Nationwide', 'Nationwide level shows the national view');
	check((await page.locator('.compare .rollup').count()) === 1, 'locality comparison is kept below the analysis');

	// Old route redirects, carrying the area.
	await page.goto(`${BASE}/localities?area=state:CO`, { waitUntil: 'networkidle' });
	await page.waitForURL((u) => u.pathname === '/analysis', { timeout: 15000 });
	await page.waitForSelector('.area-analysis h2', { timeout: 30000 });
	check((await title()) === 'Colorado', '/localities redirects to /analysis and keeps ?area=');

	check(errors.length === 0, `no page errors on mobile (${errors.slice(0, 2).join(' | ')})`);
	await page.context().close();
}

// ---------------------------------------------------------------- desktop
{
	const { page, errors } = await newPage(browser, { viewport: { width: 1280, height: 800 } });
	await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
	await waitForMap(page);
	const hint = await page.locator('.here-pane .empty h2').textContent().catch(() => null);
	check(hint === 'Job details', `desktop top-right pane is for job details (${hint})`);
	check((await page.locator('.here-pane .tab-here').count()) === 0, 'desktop pane no longer shows area metrics');
	await page.locator('.list-pane .postings li button').first().click();
	await page.waitForTimeout(500);
	const eyebrow = await page.locator('.here-pane .eyebrow').first().textContent().catch(() => null);
	check(/posting/i.test(eyebrow ?? ''), `a list row opens its job card in the pane (${eyebrow})`);
	check(errors.length === 0, `no page errors on desktop (${errors.slice(0, 2).join(' | ')})`);
	await page.context().close();
}

await browser.close();
out(failures ? `${failures} CHECK(S) FAILED` : 'ALL CHECKS PASSED');
process.exit(failures ? 1 : 0);
