// WebKit (real iOS Safari engine) test for the Here card's "What to watch"
// note (D.5.28 / ADR-0036 — AreaWatchNote, deterministic + keyless).
//
//  - Click-to-load: no /api/job-history fetch happens before the toggle is
//    clicked (ADR-0029 / invariant #22), and the fetch is pinned to
//    window=3yr.
//  - Deterministic claims render from the mocked payload: year-over-year,
//    seasonal peak month, and a "withheld" reason for the claim whose
//    evidence bar fails (posting window with only 3 records).
//  - Filter drift after load shows the "filters changed" notice WITHOUT
//    auto-refetching; Reload refetches with the new slice.
//  - Upstream failure renders an explicit unavailable message, never
//    fabricated claims.
//
// /api/job-history is mocked at window.fetch (same approach and reason as
// share-urls-webkit.spec.mjs). Usage: `npm run dev` in another terminal, then
//   node tests/area-watch-webkit.spec.mjs

import { webkit } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-watch]', ...a);
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

await ctx.addInitScript(() => {
	window.__historyCalls = [];
	window.__historyMode = 'ok';
	// 36 complete months (2023-06 .. 2026-05) at count 2, with every March
	// boosted to 12: recent-12 = prior-12 = 34 ("on pace"), March is the clear
	// seasonal peak, and only 3 records → the posting-window claim is withheld.
	const monthly = [];
	let y = 2023;
	let m = 6;
	for (let i = 0; i < 36; i++) {
		const month = `${y}-${String(m).padStart(2, '0')}`;
		monthly.push({ month, count: month.endsWith('-03') ? 12 : 2 });
		m += 1;
		if (m > 12) {
			m = 1;
			y += 1;
		}
	}
	const rec = {
		control_number: 1,
		announcement_number: null,
		title: null,
		agency_code: null,
		agency_name: null,
		department_code: null,
		series: null,
		pay_plan: null,
		grade_low: null,
		grade_high: null,
		salary_min: null,
		salary_max: null,
		open_date: '2025-01-01',
		close_date: '2025-01-11',
		city: null,
		state: null,
		hiring_path: null
	};
	const realFetch = window.fetch.bind(window);
	window.fetch = async (input, init) => {
		const url = typeof input === 'string' ? input : input?.url;
		if (typeof url === 'string' && url.includes('/api/job-history')) {
			window.__historyCalls.push(url);
			if (window.__historyMode === 'fail') return new Response('', { status: 500 });
			return new Response(
				JSON.stringify({
					status: 'ok',
					window: '3yr',
					as_of: '2026-06-12T00:00:00.000Z',
					start_date: '2023-06-12',
					end_date: '2026-06-12',
					total: 102,
					truncated: false,
					page_cap: 5,
					monthly,
					records: [rec, rec, rec],
					source: 'usajobs:historicjoa'
				}),
				{ status: 200, headers: { 'content-type': 'application/json' } }
			);
		}
		return realFetch(input, init);
	};
});

const BLANK = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
await ctx.route(/tile\.openstreetmap\.org\//, (r) =>
	r.fulfill({ status: 200, contentType: 'image/png', body: BLANK, headers: { 'access-control-allow-origin': '*' } })
);
await ctx.route(/events\.mapbox\.com/, (r) => r.fulfill({ status: 204, body: '' }));

const page = await ctx.newPage();

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
await page.waitForSelector('.here-pane section.tab-here', { timeout: 15000 });

// ---------------------------------------------------------------------------
// 1) Click-to-load: collapsed by default, zero fetches before the click.
// ---------------------------------------------------------------------------
const watchToggle = page.locator('.here-pane .watch .toggle');
check(await watchToggle.isVisible(), 'What-to-watch toggle renders on the Here card');
let calls = await page.evaluate(() => window.__historyCalls.length);
check(calls === 0, `no /api/job-history fetch before the toggle is clicked (${calls})`);

// ---------------------------------------------------------------------------
// 2) Open → one fetch pinned to 3yr; deterministic claims + withheld reason.
// ---------------------------------------------------------------------------
await watchToggle.click();
await page.waitForSelector('.here-pane .watch .lines', { timeout: 10000 });
const callUrls = await page.evaluate(() => window.__historyCalls);
check(callUrls.length === 1, `exactly one fetch after opening (${callUrls.length})`);
check(callUrls[0]?.includes('window=3yr'), `fetch pinned to the 3yr window (${callUrls[0]})`);
const lines = await page.locator('.here-pane .watch .lines').innerText();
check(
	lines.includes('on pace with the prior 12 months (34)'),
	`year-over-year line renders (${lines.split('\n')[0]})`
);
check(lines.includes('historically peaked in March'), 'seasonal peak line names March');
const withheld = await page.locator('.here-pane .watch .withheld').innerText();
check(
	withheld.includes('Typical posting window withheld') && withheld.includes('only 3'),
	`thin posting-window claim is withheld with its reason (${withheld})`
);
const basis = await page.locator('.here-pane .watch .basis').innerText();
check(basis.includes('102 HistoricJoa postings'), `basis line states the sample (${basis})`);

// ---------------------------------------------------------------------------
// 3) Filter drift → stale notice, NO auto-refetch; Reload carries the chip.
// ---------------------------------------------------------------------------
await page.evaluate(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	m.filters = { ...m.filters, agencies: ['HSCB'] };
});
await page.waitForSelector('.here-pane .watch .stale', { timeout: 10000 });
calls = await page.evaluate(() => window.__historyCalls.length);
check(calls === 1, `stale notice appears without an auto-refetch (${calls} calls)`);
await page.locator('.here-pane .watch .stale button').click();
await page.waitForTimeout(600);
const lastUrl = await page.evaluate(() => window.__historyCalls.at(-1));
calls = await page.evaluate(() => window.__historyCalls.length);
check(calls === 2, `Reload triggers exactly one more fetch (${calls} calls)`);
check(
	lastUrl?.includes('agency_code=HSCB') && lastUrl?.includes('window=3yr'),
	`reload carries the new agency chip on the 3yr window (${lastUrl})`
);
check(
	(await page.locator('.here-pane .watch .stale').count()) === 0,
	'stale notice clears after reload'
);

// ---------------------------------------------------------------------------
// 4) Upstream failure → explicit unavailable message, no claims.
// ---------------------------------------------------------------------------
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('.here-pane section.tab-here', { timeout: 15000 });
await page.evaluate(() => {
	window.__historyMode = 'fail';
});
await page.locator('.here-pane .watch .toggle').click();
await page.waitForSelector('.here-pane .watch .error', { timeout: 10000 });
const errText = await page.locator('.here-pane .watch .error').innerText();
check(
	errText.includes('What-to-watch unavailable'),
	`failure renders an explicit message (${errText})`
);
check(
	(await page.locator('.here-pane .watch .lines').count()) === 0,
	'no claims are fabricated on failure'
);

// ---------------------------------------------------------------------------
// 5) Reactivity survives: the toggle still collapses after the sequence.
// ---------------------------------------------------------------------------
await page.locator('.here-pane .watch .toggle').click();
check(
	(await page.locator('.here-pane .watch .body').count()) === 0,
	'toggle still collapses the panel after the full sequence'
);

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
