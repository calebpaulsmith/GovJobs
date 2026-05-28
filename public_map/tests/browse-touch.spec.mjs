// Browse-map stuck-bottom-sheet repro harness. Boots Chromium with iPhone 13
// touch emulation against the local Vite dev server, drives real taps via
// `page.touchscreen.tap`, and reads `mapState` directly from the running
// store module to verify the reactive chain end-to-end.
//
// Usage: `npm run dev` in another terminal, then `node tests/browse-touch.spec.mjs`.
//
// What this catches (and doesn't): the touch event model in headless
// Chromium matches iOS Safari (synthesized mousemove on touchstart, no
// mouseleave on lift), so it reproduces the popup-intercept class of
// bug that #51 addressed. It does NOT reproduce WebKit-specific quirks
// (100vh, momentum scroll, specific WebKit popup DOM behaviour). If the
// operator still sees a stuck sheet on real iOS after #51 deployed but
// this harness passes, the bug is in that WebKit-only territory.

import { chromium, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[test]', ...a);

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });
const page = await ctx.newPage();

// In this sandbox, egress to tile.openstreetmap.org returns CORS-stripped 403s,
// which prevents mapbox-gl from firing `load` and stalls the data-hydration
// chain. Intercept tile + telemetry requests so the test rig can exercise the
// app's behavior independently of network state. Mapbox doesn't require valid
// tile bytes to emit `load`; it just needs the requests to succeed.
const BLANK_PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
await ctx.route(/tile\.openstreetmap\.org\//, (route) =>
	route.fulfill({ status: 200, contentType: 'image/png', body: BLANK_PNG, headers: { 'access-control-allow-origin': '*' } })
);
await ctx.route(/events\.mapbox\.com/, (route) => route.fulfill({ status: 204, body: '' }));

const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => {
	if (m.type() === 'error') errors.push('console.error: ' + m.text());
});

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForSelector('canvas.mapboxgl-canvas, canvas.maplibregl-canvas', { timeout: 30000 });

// Wait until Map.svelte has finished its data-hydration (poll for the
// `jobs` source rather than trusting `map.idle`, which fires too early
// when tile requests are still in flight).
await page
	.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 })
	.catch(() => out('WARN: jobs source never added — Map.svelte data hydration stalled'));
await page.waitForTimeout(500);

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);

const snapshot = async (label) => {
	const s = await page.evaluate((m) => {
		const props = m.selectedFeature?.properties ?? {};
		return {
			selectedFeature: m.selectedFeature
				? { source: m.selectedFeature.source, id: props.id ?? null, city: props.city ?? null }
				: null,
			jobStack: m.jobStack ? { label: m.jobStack.label, count: m.jobStack.items?.length ?? 0 } : null,
			sheetPage: m.browseSheetPage,
			sheetExpanded: m.browseSheetExpanded
		};
	}, handle);
	out(label, JSON.stringify(s));
	return s;
};

await snapshot('initial');

const canvasBox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();

const tapTargets = await page.evaluate(() => {
	const map = window.__ffMap;
	if (!map) return { error: 'window.__ffMap not set (dev build expected)' };
	const layers = map
		.getStyle()
		.layers.filter((l) => /marker|jobs/i.test(l.id))
		.map((l) => l.id);
	const rendered = map.queryRenderedFeatures(undefined, { layers });
	const seen = new Set();
	const inView = [];
	for (const f of rendered) {
		if (f.geometry?.type !== 'Point') continue;
		const [lng, lat] = f.geometry.coordinates;
		const key = `${lng.toFixed(4)},${lat.toFixed(4)}`;
		if (seen.has(key)) continue;
		seen.add(key);
		const p = map.project([lng, lat]);
		inView.push({ x: Math.round(p.x), y: Math.round(p.y), id: f.properties?.id ?? null });
	}
	return { inView: inView.slice(0, 12) };
});

if (tapTargets.error || (tapTargets.inView ?? []).length < 2) {
	out('FAIL — could not find two distinct in-viewport markers');
	out('  diag:', JSON.stringify(tapTargets));
	out('  errors:', errors.slice(0, 5));
	await browser.close();
	process.exit(1);
}

const m1 = tapTargets.inView[0];
const m2 = tapTargets.inView.slice(1).find((t) => Math.hypot(t.x - m1.x, t.y - m1.y) > 60) ?? tapTargets.inView[1];

// CASE: tap two distinct markers in sequence with iPhone 13 touch events.
// This is the operator's exact gesture pattern. If `selectedFeature` does
// not change on the second tap, the popup-intercept bug (or any other
// click-handler block) is reproducing here.
out(`tap A → id=${m1.id} @ (${m1.x},${m1.y})`);
await page.touchscreen.tap(m1.x + (canvasBox?.x ?? 0), m1.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(600);
const afterA = await snapshot('after tap A');

out(`tap B → id=${m2.id} @ (${m2.x},${m2.y})`);
await page.touchscreen.tap(m2.x + (canvasBox?.x ?? 0), m2.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(600);
const afterB = await snapshot('after tap B');

const idA = afterA.selectedFeature?.id ?? null;
const idB = afterB.selectedFeature?.id ?? null;
const expandedA = afterA.sheetExpanded;
const expandedB = afterB.sheetExpanded;

out('---');
if (idA && idB && idA !== idB && expandedB) {
	out(`PASS — selectedFeature updated A(${idA}) → B(${idB}), sheet expanded.`);
	out('       The popup-intercept bug does NOT reproduce in headless Chromium with iPhone 13 touch emulation.');
} else if (idA === idB && idA !== null) {
	out(`FAIL — selection stayed on id=${idA} across both taps. Stuck-sheet repro.`);
} else {
	out(`UNEXPECTED — idA=${idA} idB=${idB} expandedA=${expandedA} expandedB=${expandedB}`);
}

if (errors.length) out('page/console errors:', errors.slice(0, 5));
await browser.close();
