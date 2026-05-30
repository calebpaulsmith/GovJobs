// Reproduces the operator scenario: tap a locality (sheet auto-expands),
// MANUALLY MINIMIZE the sheet (simulating tap on grabber), then tap a
// DIFFERENT locality. The bug: when the sheet starts minimized, the
// second tap does not re-expand the sheet and the content doesn't change.

import { chromium, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[mini]', ...a);

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
page.on('console', (m) => {
	if (m.type() === 'error') errors.push(m.text());
});

await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(500);

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.t s')).mapState).catch(() => null);
const handle2 = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);

const canvasBox = await page.locator('canvas.mapboxgl-canvas, canvas.maplibregl-canvas').first().boundingBox();

const snap = async (label) => {
	const s = await page.evaluate((m) => ({
		selCode: m.selectedFeature?.properties?.code ?? null,
		selSrc: m.selectedFeature?.source ?? null,
		focused: m.focusedArea?.label ?? null,
		sheetExpanded: m.browseSheetExpanded,
		sheetPage: m.browseSheetPage,
		domSheetCls: document.querySelector('.sheet')?.className,
		domSheetH: document.querySelector('.sheet')?.getBoundingClientRect().height,
		peekText: document.querySelector('.peek-label')?.textContent ?? null
	}), handle2);
	out(label, JSON.stringify(s));
	return s;
};

await page.evaluate(() => window.__ffMap.jumpTo({ center: [-121, 38.5], zoom: 6 }));
await page.waitForTimeout(900);
await snap('initial (sheet collapsed, nothing selected)');

const findLocality = async (excludeCode) => page.evaluate((exclude) => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	for (let x = 30; x < w - 30; x += 12) {
		for (let y = 30; y < h - 80; y += 12) {
			const hits = m.queryRenderedFeatures([x, y]);
			const loc = hits.find((f) => f.layer?.id === 'localities-fill');
			if (!loc) continue;
			const code = loc.properties?.code;
			if (!code || code === exclude) continue;
			const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
			if (hasMarker) continue;
			return { x, y, code, name: loc.properties?.name };
		}
	}
	return null;
}, excludeCode);

// STEP 1: tap locality A
const A = await findLocality(null);
out(`STEP 1: tap A=${A.name} @ (${A.x},${A.y})`);
await page.touchscreen.tap(A.x + (canvasBox?.x ?? 0), A.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(1200);
await snap('after tap A');

// STEP 2: USER MANUALLY MINIMIZES the sheet by tapping the grabber.
out('STEP 2: tap sheet grabber to minimize');
const grabberBox = await page.locator('.sheet .grabber').boundingBox();
await page.touchscreen.tap(grabberBox.x + grabberBox.width / 2, grabberBox.y + grabberBox.height / 2);
await page.waitForTimeout(400);
await snap('after minimize');

// STEP 3: Without expanding the sheet, tap a DIFFERENT locality B.
const B = await findLocality(A.code);
if (!B) {
	out('SKIP — no different locality available after fitBounds. Resetting viewport for clean test.');
	await page.evaluate(() => window.__ffMap.jumpTo({ center: [-121, 38.5], zoom: 6 }));
	await page.waitForTimeout(900);
}
const Bret = B ?? await findLocality(A.code);
out(`STEP 3: tap B=${Bret.name} @ (${Bret.x},${Bret.y}) WITHOUT re-expanding sheet`);
const before = await page.evaluate((m) => m.selectedFeature?.properties?.code, handle2);
await page.touchscreen.tap(Bret.x + (canvasBox?.x ?? 0), Bret.y + (canvasBox?.y ?? 0));
await page.waitForTimeout(1200);
const result = await snap('after tap B');

const expectedCode = Bret.code;
const actualCode = result.selCode;
const peek = result.peekText;
const expanded = result.sheetExpanded;

out('---');
if (actualCode === expectedCode && expanded && (peek ?? '').includes(Bret.name.slice(0, 10))) {
	out(`PASS — sheet re-expanded to B (${actualCode}), peek says ${peek}`);
} else if (actualCode === expectedCode && !expanded) {
	out(`PARTIAL FAIL — selectedFeature updated to B (${actualCode}) but sheet didn't auto-re-expand. peek=${peek}`);
} else if (actualCode === before) {
	out(`FULL FAIL — selectedFeature stayed on ${actualCode} (didn't update to B=${expectedCode}). peek=${peek} expanded=${expanded}`);
} else {
	out(`UNEXPECTED — selCode=${actualCode} expected=${expectedCode} expanded=${expanded} peek=${peek}`);
}

if (errors.length) out('errors:', errors.slice(0, 3));
await browser.close();
