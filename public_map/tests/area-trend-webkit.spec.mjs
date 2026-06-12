// WebKit (real iOS Safari engine) test for the Here card's 12-month posting
// volume sparkline (D.5.28 — AreaTrendSparkline).
//
//  - Click-to-load: no /api/job-history fetch happens before the toggle is
//    clicked (ADR-0029 / invariant #22).
//  - One click → one fetch with window=1yr; bars are zero-filled across the
//    payload's full month range (13 bars for a 1yr window).
//  - Filter drift after load shows the "filters changed" notice WITHOUT
//    auto-refetching; Reload refetches and relabels the slice.
//  - Upstream failure renders an explicit "Trend unavailable" message, never
//    fabricated bars.
//
// Vite's dev server does not run Cloudflare Pages Functions, so /api/job-history
// is mocked at window.fetch (same approach as share-urls-webkit.spec.mjs —
// page.route does not reliably intercept the app's own fetch under WebKit).
// Usage: `npm run dev` in another terminal, then
//   node tests/area-trend-webkit.spec.mjs

import { webkit } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-trend]', ...a);
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
	const realFetch = window.fetch.bind(window);
	window.fetch = async (input, init) => {
		const url = typeof input === 'string' ? input : input?.url;
		if (typeof url === 'string' && url.includes('/api/job-history')) {
			window.__historyCalls.push(url);
			if (window.__historyMode === 'fail') return new Response('', { status: 500 });
			return new Response(
				JSON.stringify({
					status: 'ok',
					window: '1yr',
					as_of: '2026-06-12T00:00:00.000Z',
					start_date: '2025-06-12',
					end_date: '2026-06-12',
					total: 42,
					truncated: false,
					page_cap: 5,
					monthly: [
						{ month: '2025-08', count: 5 },
						{ month: '2026-01', count: 12 },
						{ month: '2026-05', count: 3 }
					],
					records: [],
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
const trendToggle = page.locator('.here-pane .trend .toggle');
check(await trendToggle.isVisible(), 'trend toggle renders on the Here card');
let calls = await page.evaluate(() => window.__historyCalls.length);
check(calls === 0, `no /api/job-history fetch before the toggle is clicked (${calls})`);

// ---------------------------------------------------------------------------
// 2) Open → one fetch, window=1yr, 13 zero-filled bars, honest summary.
// ---------------------------------------------------------------------------
await trendToggle.click();
await page.waitForSelector('.here-pane .trend .spark', { timeout: 10000 });
const callUrls = await page.evaluate(() => window.__historyCalls);
check(callUrls.length === 1, `exactly one fetch after opening (${callUrls.length})`);
check(
	callUrls[0]?.includes('window=1yr'),
	`fetch pinned to the 1yr window (${callUrls[0]})`
);
const barCount = await page.locator('.here-pane .trend .spark .bar').count();
check(barCount === 13, `13 zero-filled monthly bars for a 1yr window (${barCount})`);
const janTitle = await page
	.locator('.here-pane .trend .spark .bar[title*="2026-01"]')
	.getAttribute('title');
check(janTitle === '2026-01: 12 postings', `bucketed month carries its count (${janTitle})`);
const summary = await page.locator('.here-pane .trend .summary').innerText();
check(summary.includes('42'), `summary shows the payload total (${summary.replace(/\n/g, ' ')})`);

// ---------------------------------------------------------------------------
// 3) Filter drift → stale notice, NO auto-refetch; Reload refetches + relabels.
// ---------------------------------------------------------------------------
await page.evaluate(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	m.filters = { ...m.filters, agencies: ['HSCB'] };
});
await page.waitForSelector('.here-pane .trend .stale', { timeout: 10000 });
calls = await page.evaluate(() => window.__historyCalls.length);
check(calls === 1, `stale notice appears without an auto-refetch (${calls} calls)`);
await page.locator('.here-pane .trend .stale button').click();
await page.waitForTimeout(600);
calls = await page.evaluate(() => window.__historyCalls.length);
check(calls === 2, `Reload triggers exactly one more fetch (${calls} calls)`);
const lastUrl = await page.evaluate(() => window.__historyCalls.at(-1));
check(lastUrl?.includes('agency_code=HSCB'), `reload carries the new agency chip (${lastUrl})`);
const slice = await page.locator('.here-pane .trend .slice').innerText();
check(slice.includes('agency HSCB'), `slice caption names the loaded query (${slice.replace(/\n/g, ' ')})`);
check(
	(await page.locator('.here-pane .trend .stale').count()) === 0,
	'stale notice clears after reload'
);

// ---------------------------------------------------------------------------
// 4) Upstream failure → explicit unavailable message, no bars.
// ---------------------------------------------------------------------------
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('.here-pane section.tab-here', { timeout: 15000 });
await page.evaluate(() => {
	window.__historyMode = 'fail';
});
await page.locator('.here-pane .trend .toggle').click();
await page.waitForSelector('.here-pane .trend .error', { timeout: 10000 });
const errText = await page.locator('.here-pane .trend .error').innerText();
check(errText.includes('Trend unavailable'), `failure renders an explicit message (${errText})`);
check(
	(await page.locator('.here-pane .trend .spark').count()) === 0,
	'no bars are fabricated on failure'
);

// ---------------------------------------------------------------------------
// 5) Reactivity survives (no state_unsafe_mutation freeze): the toggle still
//    collapses/expands after the whole sequence.
// ---------------------------------------------------------------------------
await page.locator('.here-pane .trend .toggle').click();
check(
	(await page.locator('.here-pane .trend .body').count()) === 0,
	'toggle still collapses the panel after the full sequence'
);

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
