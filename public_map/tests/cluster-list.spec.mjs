// Repro for "tap a cluster bubble, Postings list is empty" on Browse mobile.
// Targets the CURRENT listView (scope:'ids') -> JobList path, not the old
// jobStack/PointJobList path.

import { chromium, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[repro]', ...a);

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
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(800);
await page.addStyleTag({ content: '.token-banner { display: none !important; }' });

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const canvasBox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();

await page.evaluate(() => window.__ffMap.jumpTo({ center: [-95, 39], zoom: 5 }));
await page.waitForTimeout(900);

const target = await page.evaluate(() => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	const found = [];
	for (let x = 30; x < w - 30; x += 20) {
		for (let y = 30; y < h - 220; y += 20) {
			const hits = m.queryRenderedFeatures([x, y], { layers: ['job-clusters'] });
			for (const f of hits) {
				const id = f.properties?.cluster_id;
				if (id == null) continue;
				if (found.some((g) => g.cluster_id === id)) continue;
				const coords = f.geometry?.coordinates;
				if (!coords) continue;
				const p = m.project(coords);
				found.push({ cluster_id: id, point_count: f.properties?.point_count, x: Math.round(p.x), y: Math.round(p.y) });
			}
		}
	}
	return found.sort((a, b) => (b.point_count ?? 0) - (a.point_count ?? 0))[0];
});

if (!target) { out('FAIL — no clusters on screen.'); await browser.close(); process.exit(1); }
out(`tapping cluster id=${target.cluster_id} count=${target.point_count} @ (${target.x},${target.y})`);

await page.touchscreen.tap(target.x + (canvasBox?.x ?? 0), target.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(2500);

const result = await page.evaluate((m) => {
	const lv = m.listView;
	return {
		filtersActive: JSON.stringify(m.filters),
		listViewScope: lv?.scope,
		listViewLabel: lv?.label,
		listViewIdsSize: lv?.ids ? lv.ids.size : null,
		listViewIdsSample: lv?.ids ? Array.from(lv.ids).slice(0, 5) : null,
		browseSheetPage: m.browseSheetPage,
		allJobsLen: m.allJobs?.features?.length ?? null,
		// Does inScope-style membership actually match allJobs by id?
		idsPresentInAllJobs: (() => {
			if (!lv?.ids || !m.allJobs) return null;
			const set = new Set(m.allJobs.features.map((f) => String(f.properties?.id ?? '')));
			let hit = 0;
			for (const id of lv.ids) if (set.has(String(id))) hit++;
			return `${hit}/${lv.ids.size}`;
		})(),
		// DOM: how many job rows actually rendered in the sheet's Postings list
		domSheetClass: document.querySelector('.sheet')?.className,
		domJobListRows: document.querySelectorAll('.sheet .job-list li, .sheet .job-list article, .sheet .job-list .row').length,
		domNote: document.querySelector('.sheet .job-list .note, .sheet .job-list .empty')?.textContent?.trim() ?? null,
		domH3: document.querySelector('.sheet .job-list h3')?.textContent?.trim() ?? null
	};
}, handle);

out('RESULT:', JSON.stringify(result, null, 2));
if (errors.length) out('errors:', errors.slice(0, 5));
await browser.close();

// Regression assertions for the "tap a cluster -> empty Postings list" bug:
// a cluster of multi-location postings must render rows and must not throw
// each_key_duplicate (which blanks the list).
const dupErr = errors.find((e) => e.includes('each_key_duplicate'));
if (dupErr) {
	out('FAIL — each_key_duplicate thrown (duplicate posting ids blank the list)');
	process.exit(1);
}
if (result.listViewIdsSize > 0 && result.domJobListRows === 0) {
	out(`FAIL — listView resolved ${result.listViewIdsSize} postings but 0 rows rendered`);
	process.exit(1);
}
out(`PASS — ${result.listViewIdsSize} postings in scope, rows rendered, no key crash`);
