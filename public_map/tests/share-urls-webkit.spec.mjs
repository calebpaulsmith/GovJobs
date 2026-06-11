// WebKit (real iOS Safari engine) test for shareable view URLs (D.5.29).
//
//  - Hydration: /browse?<params> restores filters + metric into the store.
//  - Share button (short-link success): a mocked /api/share returns a short URL
//    and that's what lands on the clipboard.
//  - Share button (fallback): when /api/share fails, the full long URL is
//    copied instead (clipboard copy always succeeds).
//  - Closed-job banner: a shared selected=<closed id> shows the banner, not a
//    dead card, and the rest of the view still renders.
//  - Live selected: a shared selected=<open id> opens that job card.
//
// Vite's dev server does not run Cloudflare Pages Functions, so we mock
// /api/share at the network layer (which is exactly how it behaves in a no-KV
// deploy too). Usage: `npm run dev` in another terminal, then
//   node tests/share-urls-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-share]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });

// Capture what the page copies to the clipboard, and mock the /api/share
// network boundary at window.fetch. WebKit + Playwright does not reliably
// intercept the app's own POST via page.route/ctx.route (an evaluate() fetch
// intercepts, the in-app one slips through to the dev server), so we stub fetch
// in an init script — deterministic and exactly the boundary the component
// depends on. `window.__shareMode` flips success ↔ failure per test.
await ctx.addInitScript(() => {
	window.__copied = null;
	window.__shareMode = 'ok';
	try {
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: { writeText: async (t) => { window.__copied = String(t); } }
		});
	} catch (e) {
		/* fall back to execCommand override below */
	}
	document.execCommand = (cmd) => {
		if (cmd === 'copy') {
			const el = document.querySelector('textarea');
			if (el) window.__copied = el.value;
			return true;
		}
		return false;
	};
	const realFetch = window.fetch.bind(window);
	window.fetch = async (input, init) => {
		const url = typeof input === 'string' ? input : input?.url;
		if (typeof url === 'string' && url.includes('/api/share')) {
			if (window.__shareMode === 'fail') return new Response('', { status: 503 });
			return new Response(JSON.stringify({ hash: 'abc2345', url: 'https://share.test/s/abc2345' }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			});
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

const store = () => page.evaluate(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const readStore = (fn) => page.evaluate(fn);

// ---------------------------------------------------------------------------
// 1) Hydration from a shared link.
// ---------------------------------------------------------------------------
await page.goto(`${BASE}/browse?q=analyst&agency=HSCB&metric=workforce&center=-87.63,41.88&zoom=9`, {
	waitUntil: 'networkidle',
	timeout: 60000
});
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
await page.waitForTimeout(800);

const hydrated = await readStore(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	return { keyword: m.filters.keyword, agencies: [...m.filters.agencies], metric: m.metric };
});
check(hydrated.keyword === 'analyst', `keyword hydrated from URL (${hydrated.keyword})`);
check(hydrated.agencies.includes('HSCB'), `agency chip hydrated from URL (${JSON.stringify(hydrated.agencies)})`);
check(hydrated.metric === 'workforce', `metric hydrated from URL (${hydrated.metric})`);

// ---------------------------------------------------------------------------
// 2) Share button — short-link success path (mocked /api/share via fetch stub).
// ---------------------------------------------------------------------------
await page.evaluate(() => { window.__shareMode = 'ok'; window.__copied = null; });
await page.locator('.share-btn').first().click();
await page.waitForTimeout(600);
let copied = await page.evaluate(() => window.__copied);
check(copied === 'https://share.test/s/abc2345', `short link copied on success (${copied})`);
check(
	await page.locator('.toast').first().isVisible().catch(() => false),
	'a confirmation toast appears'
);

// ---------------------------------------------------------------------------
// 3) Share button — fallback to the long URL when the Function fails.
// ---------------------------------------------------------------------------
await page.evaluate(() => { window.__shareMode = 'fail'; window.__copied = null; });
await page.locator('.share-btn').first().click();
await page.waitForTimeout(600);
copied = await page.evaluate(() => window.__copied);
check(
	typeof copied === 'string' && copied.includes('/browse?') && copied.includes('q=analyst'),
	`long URL copied as fallback, carrying the view (${copied})`
);

// ---------------------------------------------------------------------------
// 4) Closed-job banner — shared selected id that isn't an open posting.
// ---------------------------------------------------------------------------
await page.goto(`${BASE}/browse?selected=999999999`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
// Wait for jobs_detail to load so the resolver can decide open-vs-closed.
await page.waitForFunction(
	async () => Object.keys((await import('/src/lib/store.svelte.ts')).mapState.allJobDetails || {}).length > 0,
	{ timeout: 30000 }
).catch(() => {});
await page.waitForTimeout(600);
check(
	await page.locator('.closed-banner').isVisible().catch(() => false),
	'closed-job banner renders for a shared link whose job has closed'
);
const closedId = await readStore(async () => (await import('/src/lib/store.svelte.ts')).mapState.shareClosedJobId);
check(closedId === '999999999', `shareClosedJobId set to the closed id (${closedId})`);

// ---------------------------------------------------------------------------
// 5) Live selected — shared selected id that IS an open posting opens the card.
// ---------------------------------------------------------------------------
const openId = await readStore(async () => {
	const m = (await import('/src/lib/store.svelte.ts')).mapState;
	return Object.keys(m.allJobDetails || {})[0] ?? null;
});
if (openId) {
	await page.goto(`${BASE}/browse?selected=${openId}`, { waitUntil: 'networkidle', timeout: 60000 });
	await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });
	await page.waitForFunction(
		async () => Object.keys((await import('/src/lib/store.svelte.ts')).mapState.allJobDetails || {}).length > 0,
		{ timeout: 30000 }
	).catch(() => {});
	await page.waitForTimeout(600);
	const sel = await readStore(async () => {
		const m = (await import('/src/lib/store.svelte.ts')).mapState;
		return { label: m.selectedFeature?.label ?? null, id: String(m.selectedFeature?.properties?.id ?? '') };
	});
	check(sel.label === 'Job card' && sel.id === String(openId), `shared open job opens its card (${JSON.stringify(sel)})`);
} else {
	out('SKIP live-selected — no open postings in bundle');
}

out('================');
out(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
