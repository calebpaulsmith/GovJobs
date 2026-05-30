// Verifies the viewport/polygon-scoped JobList wiring (PR replacing the
// cluster-jobStack path). After a polygon tap, the Postings tab should
// auto-render with that polygon's jobs and a header like "Postings in
// California". After a cluster tap, the camera zooms in and the
// Postings tab shows the viewport-scoped jobs.

import { chromium, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[scope]', ...a);

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'], ignoreHTTPSErrors: true });
const page = await ctx.newPage();
const BLANK = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=',
	'base64'
);
await ctx.route(/tile\.openstreetmap\.org\//, (route) =>
	route.fulfill({ status: 200, contentType: 'image/png', body: BLANK, headers: { 'access-control-allow-origin': '*' } })
);
await ctx.route(/events\.mapbox\.com/, (route) => route.fulfill({ status: 204, body: '' }));

const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => {
	if (m.type() === 'error') errors.push(m.text());
	if (m.text().includes('ff-click') || m.text().includes('ff-jl')) console.log('[scope]   ' + m.text());
});
page.on('request', (r) => {
	if (/jobs\.geojson|jobs_detail/.test(r.url())) console.log(`[scope] req → ${r.url().slice(0, 90)}`);
});
page.on('response', (r) => {
	if (/jobs\.geojson|jobs_detail/.test(r.url())) console.log(`[scope] res ${r.status()} ${r.url().slice(0, 90)}`);
});
page.on('requestfailed', (r) => {
	if (/jobs\.geojson|jobs_detail/.test(r.url())) console.log(`[scope] FAIL ${r.failure()?.errorText} ${r.url().slice(0, 90)}`);
});

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(500);
await page.addStyleTag({ content: '.token-banner { display: none !important; }' });

await page.evaluate(() => {
	window.__ffMap.on('click', (e) => {
		console.log('[ff-click] mapbox click at', e.point.x, e.point.y);
	});
});

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const canvasBox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();

const snap = async (label) => {
	const s = await page.evaluate((m) => ({
		listView: m.listView,
		sheetPage: m.browseSheetPage,
		sheetExpanded: m.browseSheetExpanded,
		domEyebrow: document.querySelector('.sheet .scoped-head .eyebrow')?.textContent,
		domJobRowCount: document.querySelectorAll('.sheet .job-list ul > li').length,
		domJobListInnerStart: document.querySelector('.sheet .job-list')?.innerHTML?.slice(0, 600),
		domViewportBounds: m.viewport.bounds,
		mapStateAllJobs: m.allJobs?.features?.length ?? null,
		panelHtmlStart: document.querySelector('.sheet .panel')?.innerHTML?.slice(0, 300) ?? null
	}), handle);
	out(label, JSON.stringify(s));
	return s;
};

// ===== CASE 1: tap a state polygon, verify scoped list. =====
out('--- CASE 1: state polygon tap ---');
await page.evaluate(() => window.__ffMap.jumpTo({ center: [-95, 39], zoom: 4 }));
await page.waitForTimeout(900);

// Find a state-fill pixel that doesn't have a cluster on top.
const stateTap = await page.evaluate(() => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	// Start y below the Filters FAB (top-left ~y=80 absolute,
	// canvas-relative ~y=10 + ~30 px fab height); start x past the FAB
	// width too.
	for (let x = 120; x < w - 30; x += 24) {
		for (let y = 90; y < h - 80; y += 24) {
			const hits = m.queryRenderedFeatures([x, y]);
			const state = hits.find((f) => f.layer?.id === 'states-fill');
			if (!state) continue;
			const hasMarker = hits.some((f) => ['job-clusters', 'job-markers'].includes(f.layer?.id));
			if (hasMarker) continue;
			return { x, y, name: state.properties?.name, state: state.properties?.state };
		}
	}
	return null;
});
if (!stateTap) {
	out('SKIP CASE 1: no clean state-fill pixel.');
} else {
	out(`tap state ${stateTap.name} (${stateTap.state}) @ (${stateTap.x},${stateTap.y})`);
	const absX = stateTap.x + (canvasBox?.x ?? 0);
	const absY = stateTap.y + (canvasBox?.y ?? 0);
	const topEl = await page.evaluate(({ x, y }) => {
		const el = document.elementFromPoint(x, y);
		if (!el) return null;
		const cls = String(el.getAttribute('class') || '').split(/\s+/).slice(0, 2).join('.');
		return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}`;
	}, { x: absX, y: absY });
	out(`tap absolute=(${absX.toFixed(1)},${absY.toFixed(1)}) topElement=${topEl}`);
	await page.touchscreen.tap(absX, absY);
	await page.waitForTimeout(1500);
	// Switch to Postings tab to render the scoped list.
	await page.evaluate((m) => { m.browseSheetPage = 'list'; }, handle);
	// Wait for JobList to render rows OR show a definite empty/error
	// state.
	await page
		.waitForFunction(() => {
			const root = document.querySelector('.sheet .job-list');
			if (!root) return false;
			if (root.querySelector('ul li')) return true;
			const note = root.querySelector('.note')?.textContent ?? '';
			if (note.includes('No postings')) return true;
			return false;
		}, { timeout: 30000 })
		.catch(() => out('WARN: JobList neither loaded rows nor reported empty'));
	await page.waitForTimeout(400);
	// Diagnostic: force-toggle the inner `loading` $state somehow. We can't
	// reach it directly, but if mapState reactivity is fine then writing a
	// new listView object should force JobList's `rows` derived to
	// recompute. Then the {#if loading} should re-evaluate too.
	const afterState = await snap('after state tap → Postings');
	const innerNote = await page.evaluate(() => document.querySelector('.sheet .job-list .note')?.outerHTML);
	out('inner note html:', innerNote);
	// Directly read JobList's allJobs via internal — can't easily, so
	// instead just probe whether scope='viewport' clean writes propagate.
	await page.evaluate((m) => { m.listView = { scope: 'viewport', code: '', label: 'forced' }; }, handle);
	await page.waitForTimeout(2000);
	const afterForce = await snap('after force viewport');
	const okScope = afterState.listView?.scope === 'state' && afterState.listView?.code === stateTap.state;
	const okHeader = afterState.domEyebrow?.includes(stateTap.name);
	const okRows = afterState.domJobRowCount > 0;
	out(
		`CASE 1: ${okScope ? 'PASS scope' : 'FAIL scope'} | ${okHeader ? 'PASS header' : 'FAIL header'} | ${okRows ? `PASS ${afterState.domJobRowCount} rows` : 'FAIL no rows'}`
	);
}

// ===== CASE 2: tap a cluster, verify viewport-scoped list. =====
out('');
out('--- CASE 2: cluster tap ---');
// Reset to a wide view first.
await page.evaluate(() => window.__ffMap.jumpTo({ center: [-95, 39], zoom: 5 }));
await page.waitForTimeout(900);
await page.evaluate((m) => { m.listView = null; m.selectedFeature = null; m.focusedArea = null; }, handle);
await page.waitForTimeout(300);

const clusterTap = await page.evaluate(() => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	const found = [];
	for (let x = 120; x < w - 30; x += 20) {
		for (let y = 90; y < h - 80; y += 20) {
			const hits = m.queryRenderedFeatures([x, y], { layers: ['job-clusters'] });
			for (const f of hits) {
				const id = f.properties?.cluster_id;
				if (id == null || found.some((g) => g.cluster_id === id)) continue;
				const coords = f.geometry?.coordinates;
				if (!coords) continue;
				const p = m.project(coords);
				found.push({ cluster_id: id, point_count: f.properties?.point_count, x: Math.round(p.x), y: Math.round(p.y) });
			}
		}
	}
	return found.sort((a, b) => (b.point_count ?? 0) - (a.point_count ?? 0))[0];
});

if (!clusterTap) {
	out('SKIP CASE 2: no cluster on screen.');
} else {
	out(`tap cluster id=${clusterTap.cluster_id} count=${clusterTap.point_count} @ (${clusterTap.x},${clusterTap.y})`);
	await page.touchscreen.tap(clusterTap.x + (canvasBox?.x ?? 0), clusterTap.y + (canvasBox?.y ?? 0));
	// Wait for easeTo + viewport update + jobs.geojson fetch.
	// Wait for JobList to render rows OR show a definite empty/error
	// state.
	await page
		.waitForFunction(() => {
			const root = document.querySelector('.sheet .job-list');
			if (!root) return false;
			if (root.querySelector('ul li')) return true;
			const note = root.querySelector('.note')?.textContent ?? '';
			if (note.includes('No postings')) return true;
			return false;
		}, { timeout: 30000 })
		.catch(() => out('WARN: JobList neither loaded rows nor reported empty'));
	await page.waitForTimeout(400);
	const afterCluster = await snap('after cluster tap');
	const okScope = afterCluster.listView?.scope === 'viewport';
	const okPage = afterCluster.sheetPage === 'list';
	const okExpanded = afterCluster.sheetExpanded === true;
	const okRows = afterCluster.domJobRowCount > 0;
	out(
		`CASE 2: ${okScope ? 'PASS viewport' : 'FAIL scope'} | ${okPage ? 'PASS list tab' : 'FAIL tab'} | ${okExpanded ? 'PASS open' : 'FAIL collapsed'} | ${okRows ? `PASS ${afterCluster.domJobRowCount} rows` : 'FAIL no rows'}`
	);
}

if (errors.length) out('errors:', errors.slice(0, 3));
await browser.close();
