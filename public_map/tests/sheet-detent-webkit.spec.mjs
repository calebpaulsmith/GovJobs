// WebKit (real iOS Safari engine) test for the browse bottom-sheet detents.
// Verifies the drag-to-resize fix: collapsed → half (partway) → full (~92%),
// tap-to-toggle, and — critically — that going to the full detent and back
// does NOT trip the Svelte 5 `state_unsafe_mutation` bailout that froze the
// reactive graph on earlier iOS-only bugs (CLAUDE.md "frozen Here screen").
//
// Runs against the local Vite dev server with iPhone 13 + WebKit emulation.
// Usage: `npm run dev` in another terminal, then
//   node tests/sheet-detent-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });
const page = await ctx.newPage();

// Route OSM tiles to a blank PNG so mapbox-gl fires `load` regardless of
// network (kept from the Chromium harness; harmless when egress works).
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
await page
	.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 })
	.catch(() => out('WARN: jobs source never added'));
await page.waitForTimeout(500);

const ua = await page.evaluate(() => navigator.userAgent);
out('UA:', ua);
check(/AppleWebKit/.test(ua) && /Mobile/.test(ua), 'running under WebKit + mobile emulation');

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const readState = () =>
	page.evaluate(
		(m) => ({
			expanded: m.browseSheetExpanded,
			full: m.browseSheetFull,
			page: m.browseSheetPage,
			selSource: m.selectedFeature?.source ?? null,
			stackSet: m.jobStack !== null,
			listScope: m.listView?.scope ?? null
		}),
		handle
	);
const sheetRect = () =>
	page.evaluate(() => {
		const el = document.querySelector('.sheet');
		const r = el.getBoundingClientRect();
		// The sheet sizes against its offsetParent, not the window.
		const ph = el.offsetParent?.getBoundingClientRect().height ?? window.innerHeight;
		return { height: Math.round(r.height), top: Math.round(r.top), parentH: Math.round(ph), cls: el.className };
	});

// Drag the grabber by issuing pointer events (the grabber listens to generic
// pointerdown/move/up; mouse-driven pointer events exercise the same path).
async function dragGrabber(deltaY, steps = 10) {
	const g = await page.locator('.grabber').boundingBox();
	const cx = g.x + g.width / 2;
	const cy = g.y + g.height / 2;
	await page.mouse.move(cx, cy);
	await page.mouse.down();
	for (let i = 1; i <= steps; i++) {
		await page.mouse.move(cx, cy + (deltaY * i) / steps);
		await page.waitForTimeout(16);
	}
	await page.mouse.up();
	await page.waitForTimeout(400);
}

out('--- initial ---');
const s0 = await readState();
const r0 = await sheetRect();
out('state:', JSON.stringify(s0), 'rect:', JSON.stringify(r0));

// 1) Tap the grabber → expand to the half (partway) detent. The 220ms CSS
// height transition starts only after the panel content mounts (the first-run
// welcome card adds DOM on first expand), so give it a comfortable margin.
await page.locator('.grabber').click();
await page.waitForTimeout(900);
let s = await readState();
let r = await sheetRect();
out('after tap-to-expand:', JSON.stringify(s), JSON.stringify(r));
check(s.expanded && !s.full, 'tap expands to half detent (expanded, not full)');
check(r.height > r.parentH * 0.4 && r.height < r.parentH * 0.62, `half detent ~50% of parent (got ${r.height}/${r.parentH})`);

// 2) Drag the grabber up to the top → full detent (~92%).
await dragGrabber(-Math.round(r.parentH * 0.9));
s = await readState();
r = await sheetRect();
out('after drag up:', JSON.stringify(s), JSON.stringify(r));
check(s.expanded && s.full, 'drag-up snaps to full detent');
check(r.height > r.parentH * 0.8 && r.height > 0, `full detent ≥80% of parent (got ${r.height}/${r.parentH})`);

// 3) The panel must actually be scrollable at full height (the whole point).
const scrollable = await page.evaluate(() => {
	const panels = [...document.querySelectorAll('.sheet .panel')];
	return panels.some((p) => p.scrollHeight > p.clientHeight + 4);
});
check(scrollable, 'at full height a panel overflows and can be scrolled');

// 4) Drag the grabber back down to the bottom → collapses, full drops.
await dragGrabber(Math.round(r.parentH * 1.1));
s = await readState();
r = await sheetRect();
out('after drag down:', JSON.stringify(s), JSON.stringify(r));
check(!s.expanded && !s.full, 'drag-down to bottom collapses and clears full');

// 5) REACTIVITY-FREEZE GUARD. After cycling through detents, tap a marker
//    and confirm the reactive chain still fires (selectedFeature set, sheet
//    auto-expands to Here at the half detent). This is the WebKit-only
//    `state_unsafe_mutation` class of bug the CLAUDE.md investigation chased.
out('--- post-cycle reactivity ---');
const marker = await page.evaluate(() => {
	const m = window.__ffMap;
	// Individual job markers and same-coord stacks only. The old /marker|jobs/i
	// regex also matched the cluster layers ('job-clusters'), and tapping a
	// cluster zooms the map instead of selecting — which this check would
	// mis-read as a freeze.
	const layers = m
		.getStyle()
		.layers.filter((l) => l.id === 'job-markers' || l.id === 'job-markers-stack')
		.map((l) => l.id);
	const rendered = m.queryRenderedFeatures(undefined, { layers });
	// Skip markers that project behind the collapsed bottom sheet (~3.6rem)
	// or the masthead — a tap there hits the sheet's peek bar, not the map,
	// and the check would mis-read that as a freeze.
	const h = m.getCanvas().clientHeight;
	for (const f of rendered) {
		if (f.geometry?.type !== 'Point') continue;
		const p = m.project(f.geometry.coordinates);
		if (p.y > h - 80 || p.y < 60) continue;
		return { x: Math.round(p.x), y: Math.round(p.y) };
	}
	return null;
});
if (!marker) {
	out('SKIP reactivity tap — no marker in viewport');
} else {
	const cbox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();
	await page.touchscreen.tap(marker.x + (cbox?.x ?? 0), marker.y + (cbox?.y ?? 0));
	await page.waitForTimeout(700);
	s = await readState();
	out('after marker tap:', JSON.stringify(s));
	// Two legitimate outcomes prove the reactive chain is alive:
	//   • single marker → jobStack/selectedFeature set, sheet opens to Here;
	//   • "+N" stack    → exact-IDs listView, sheet opens to Postings
	//     (Map.svelte's applyMarkerStackIdsListView path — selectedFeature
	//     intentionally stays null there).
	// A frozen graph shows expanded with none of those state changes.
	const drove =
		s.expanded &&
		((s.page === 'here' && (s.selSource !== null || s.stackSet)) ||
			(s.page === 'list' && s.listScope === 'ids'));
	check(drove, 'marker tap still drives the sheet after detent cycle (no freeze)');
}

out('================');
if (errors.length) out('page/console errors:', errors.slice(0, 6));
out(failures === 0 ? `ALL CHECKS PASSED` : `${failures} CHECK(S) FAILED`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
