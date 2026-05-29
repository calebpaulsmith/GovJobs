// Reproduces the operator's "frozen Here screen" scenario step-by-step.
// 1. Tap a locality polygon → confirm sheet shows the locality.
// 2. With the sheet open, tap the Filters FAB → does mapState.filterSheetOpen flip?
// 3. Tap the sheet's grabber to toggle → does mapState.browseSheetExpanded flip?
// 4. Tap a SECOND locality polygon → does selectedFeature update?
//
// Captures EVERY console.error (especially Svelte's state_unsafe_mutation
// bailout) and every state transition so we can see which mutation stopped
// propagating.

import { chromium, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[freeze]', ...a);

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });
const page = await ctx.newPage();

const BLANK_PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
await ctx.route(/tile\.openstreetmap\.org\//, (route) =>
	route.fulfill({ status: 200, contentType: 'image/png', body: BLANK_PNG, headers: { 'access-control-allow-origin': '*' } })
);
await ctx.route(/events\.mapbox\.com/, (route) => route.fulfill({ status: 204, body: '' }));

const errors = [];
const warnings = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => {
	const t = m.text();
	if (m.type() === 'error') errors.push(t);
	if (m.type() === 'warning' || /state_unsafe|effect|svelte/i.test(t)) warnings.push(`[${m.type()}] ${t}`);
});

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(500);

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const canvasBox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();

const snap = async (label) => {
	const s = await page.evaluate((m) => ({
		sel: m.selectedFeature ? { src: m.selectedFeature.source, code: m.selectedFeature.properties?.code ?? m.selectedFeature.properties?.name } : null,
		focused: m.focusedArea ? { src: m.focusedArea.source, label: m.focusedArea.label } : null,
		sheetExpanded: m.browseSheetExpanded,
		sheetPage: m.browseSheetPage,
		filterSheetOpen: m.filterSheetOpen,
		savedDrawerOpen: m.savedDrawerOpen,
		domSheet: document.querySelector('.sheet')?.className,
		domFab: !!document.querySelector('.filters-fab'),
		fabRect: document.querySelector('.filters-fab')?.getBoundingClientRect()
	}), handle);
	out(label, JSON.stringify(s));
	return s;
};

// Jump to a viewport with locality polygons exposed AND less marker density.
await page.evaluate(() => window.__ffMap.jumpTo({ center: [-121, 38.5], zoom: 6 }));
await page.waitForTimeout(900);
await snap('initial');

// Pick a polygon-clean pixel for L1.
const L1 = await page.evaluate(() => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	for (let x = 30; x < w - 30; x += 16) {
		for (let y = 30; y < h - 80; y += 16) {
			const hits = m.queryRenderedFeatures([x, y]);
			const loc = hits.find((f) => f.layer?.id === 'localities-fill');
			if (!loc) continue;
			const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
			if (hasMarker) continue;
			return { x, y, name: loc.properties?.name, code: loc.properties?.code };
		}
	}
	return null;
});
if (!L1) { out('FAIL: no clean locality pixel'); await browser.close(); process.exit(1); }

out(`STEP 1: tap locality L1 (${L1.name}) @ (${L1.x},${L1.y})`);
await page.touchscreen.tap(L1.x + (canvasBox?.x ?? 0), L1.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(1200);
await snap('after L1 tap');

// STEP 2: tap the Filters FAB.
const fabBox = await page.locator('.filters-fab').boundingBox();
out(`STEP 2: tap Filters FAB @ (${Math.round(fabBox.x + fabBox.width / 2)},${Math.round(fabBox.y + fabBox.height / 2)})`);
await page.touchscreen.tap(fabBox.x + fabBox.width / 2, fabBox.y + fabBox.height / 2);
await page.waitForTimeout(500);
await snap('after Filters FAB tap');

// If the filter sheet opened, dismiss it via its overlay.
const filterOpen = await page.evaluate((m) => m.filterSheetOpen, handle);
if (filterOpen) {
	out('  → FilterSheet IS open. Closing via overlay.');
	await page.evaluate((m) => (m.filterSheetOpen = false), handle);
	await page.waitForTimeout(300);
}

// STEP 3: tap the sheet grabber (the bar above the panel content).
const grabberBox = await page.locator('.sheet .grabber').boundingBox();
out(`STEP 3: tap sheet grabber @ (${Math.round(grabberBox.x + grabberBox.width / 2)},${Math.round(grabberBox.y + grabberBox.height / 2)})`);
const wasExpanded = await page.evaluate((m) => m.browseSheetExpanded, handle);
await page.touchscreen.tap(grabberBox.x + grabberBox.width / 2, grabberBox.y + grabberBox.height / 2);
await page.waitForTimeout(500);
const nowExpanded = await page.evaluate((m) => m.browseSheetExpanded, handle);
out(`  grabber tap → expanded ${wasExpanded} → ${nowExpanded}`, wasExpanded === nowExpanded ? 'FROZEN' : 'WORKED');
await snap('after grabber tap');

// Re-expand the sheet so the second locality tap exercises the same path
// the operator hits (auto-expand effect).
await page.evaluate((m) => (m.browseSheetExpanded = true), handle);
await page.waitForTimeout(200);

// STEP 4: find a DIFFERENT locality in the post-L1 viewport (top half only,
// since sheet now covers the bottom 50%).
const L2 = await page.evaluate((excludeCode) => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	for (let x = 30; x < w - 30; x += 16) {
		for (let y = 30; y < h * 0.5 - 20; y += 16) {
			const hits = m.queryRenderedFeatures([x, y]);
			const loc = hits.find((f) => f.layer?.id === 'localities-fill');
			if (!loc) continue;
			const code = loc.properties?.code;
			if (code === excludeCode) continue;
			const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
			if (hasMarker) continue;
			return { x, y, name: loc.properties?.name, code };
		}
	}
	return null;
}, L1.code);

if (!L2) {
	out('STEP 4 SKIP: no second locality visible in top half after L1 fitBounds');
} else {
	out(`STEP 4: tap locality L2 (${L2.name}) @ (${L2.x},${L2.y})`);
	const before = await page.evaluate((m) => m.selectedFeature?.properties?.code, handle);
	await page.touchscreen.tap(L2.x + (canvasBox?.x ?? 0), L2.y + (canvasBox?.y ?? 0));
	await page.waitForTimeout(1200);
	const after = await page.evaluate((m) => m.selectedFeature?.properties?.code, handle);
	out(`  L2 tap → selectedFeature.code ${before} → ${after}`, before === after ? 'FROZEN' : 'WORKED');
	await snap('after L2 tap');
}

out('--- console errors ---');
for (const e of errors) out(' ', e.slice(0, 300));
out('--- end errors ---');
out('--- console warnings (Svelte / effect related) ---');
for (const w of warnings) out(' ', w.slice(0, 300));
out('--- end warnings ---');

await browser.close();
