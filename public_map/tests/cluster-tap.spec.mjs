// Minimal cluster-tap repro: tap a cluster, wait, check whether
// PointJobList renders with the cluster's leaves.

import { chromium, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[cluster]', ...a);

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
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
const allLogs = [];
page.on('console', (m) => {
	if (m.type() === 'error') errors.push(m.text());
	if (m.text().includes('ff-stack') || m.text().includes('ff-event') || m.text().includes('ff-active') || m.text().includes('ff-pjl') || m.text().includes('[pjl]')) allLogs.push(m.text());
});

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(500);
await page.addStyleTag({ content: '.token-banner { display: none !important; }' });

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const canvasBox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();

await page.evaluate(() => window.__ffMap.jumpTo({ center: [-95, 39], zoom: 5 }));
await page.waitForTimeout(900);

// Find a cluster with the highest point count.
const target = await page.evaluate(() => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	const found = [];
	for (let x = 30; x < w - 30; x += 20) {
		for (let y = 30; y < h - 80; y += 20) {
			const hits = m.queryRenderedFeatures([x, y], { layers: ['job-clusters'] });
			for (const f of hits) {
				const id = f.properties?.cluster_id;
				if (id == null) continue;
				if (found.some((g) => g.cluster_id === id)) continue;
				const coords = f.geometry?.coordinates;
				if (!coords) continue;
				const p = m.project(coords);
				found.push({
					cluster_id: id,
					point_count: f.properties?.point_count,
					x: Math.round(p.x),
					y: Math.round(p.y)
				});
			}
		}
	}
	return found.sort((a, b) => (b.point_count ?? 0) - (a.point_count ?? 0))[0];
});

if (!target) {
	out('FAIL — no clusters on screen.');
	await browser.close();
	process.exit(1);
}

out(`tapping cluster id=${target.cluster_id} count=${target.point_count} @ (${target.x},${target.y})`);
await page.touchscreen.tap(target.x + (canvasBox?.x ?? 0), target.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(2000);

const dbgH2 = await page.evaluate(() => document.querySelector('.point-list h2')?.textContent);
out('DBG h2 text:', dbgH2);

const result = await page.evaluate((m) => ({
	stateJobStackItems: m.jobStack?.items?.length ?? 0,
	stateSheetExpanded: m.browseSheetExpanded,
	stateSelectedFeature: m.selectedFeature ? m.selectedFeature.source : null,
	domSheetClass: document.querySelector('.sheet')?.className,
	domSheetHeight: document.querySelector('.sheet')?.getBoundingClientRect()?.height,
	domPointList: !!document.querySelector('.point-list'),
	domPointListItems: document.querySelectorAll('.point-list li').length,
	panel0FirstChildTag: document.querySelector('.sheet .panel')?.firstElementChild?.tagName,
	panel0FirstChildClass: document.querySelector('.sheet .panel')?.firstElementChild?.className
}), handle);
out('result:', JSON.stringify(result));

out('---');
if (result.stateJobStackItems > 0 && result.domPointListItems === result.stateJobStackItems) {
	out(`PASS — ${result.stateJobStackItems} jobs in state AND ${result.domPointListItems} <li> rendered`);
} else if (result.stateJobStackItems > 0 && result.domPointList === false) {
	out(`FAIL — state has ${result.stateJobStackItems} jobs but PointJobList is NOT rendered. Panel shows: ${result.panel0FirstChildClass}`);
} else if (result.stateJobStackItems === 0) {
	out(`FAIL — jobStack is empty after cluster tap (cluster handler didn't populate it)`);
} else {
	out(`PARTIAL — state has ${result.stateJobStackItems} jobs, DOM has ${result.domPointListItems} <li>`);
}

// Diagnostic: force-write the same jobStack from page.evaluate. If DOM
// updates after this, the cluster path's write reached the proxy but
// Svelte's template subscription didn't re-evaluate for it.
const force = await page.evaluate(async (m) => {
	const stack = m.jobStack;
	const before = { items: m.jobStack?.items?.length, li: document.querySelectorAll('.point-list li').length };
	m.jobStack = { ...stack };
	await new Promise((r) => setTimeout(r, 200));
	const after = { items: m.jobStack?.items?.length, li: document.querySelectorAll('.point-list li').length };
	return { before, after };
}, handle);
out('force-write same stack:', JSON.stringify(force));

// Extra diagnostic: replace jobStack with a totally fresh object from
// page.evaluate AFTER the cluster path. {#key items.length} should fire
// the remount. Then check if items render.
const replaceTest = await page.evaluate(async (m) => {
	const before = { items: m.jobStack?.items?.length, li: document.querySelectorAll('.point-list li').length };
	const fresh = {
		label: 'Fresh replacement',
		selectedIndex: 0,
		items: Array.from({ length: 7 }, (_, i) => ({ properties: { id: `r-${i}`, title: `Job ${i}`, city: 'A', state: 'B' } }))
	};
	m.jobStack = fresh;
	await new Promise((r) => setTimeout(r, 200));
	const after = { items: m.jobStack?.items?.length, li: document.querySelectorAll('.point-list li').length };
	return { before, after };
}, handle);
out('replace test:', JSON.stringify(replaceTest));

// Now test direct SPLICE from page.evaluate. If this updates the DOM,
// splice DOES propagate via $state — meaning the cluster path's splice
// SHOULD work but something in the actor-callback context is suppressing
// the notification.
const spliceTest = await page.evaluate(async (m) => {
	const before = { items: m.jobStack?.items?.length, li: document.querySelectorAll('.point-list li').length };
	const replacement = Array.from({ length: 12 }, (_, i) => ({ properties: { id: `s-${i}`, title: `S ${i}`, city: 'A', state: 'B' } }));
	m.jobStack.items.splice(0, m.jobStack.items.length, ...replacement);
	await new Promise((r) => setTimeout(r, 200));
	const after = { items: m.jobStack?.items?.length, li: document.querySelectorAll('.point-list li').length };
	return { before, after };
}, handle);
out('splice test:', JSON.stringify(spliceTest));

out('stack logs:', JSON.stringify(allLogs));
if (errors.length) out('errors:', errors.slice(0, 3));
await browser.close();
