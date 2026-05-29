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

// Verify #51's fix premise: iPhone 13 emulation should NOT report (hover: hover).
const hoverProbe = await page.evaluate(() => ({
	hoverHover: window.matchMedia('(hover: hover)').matches,
	hoverNone: window.matchMedia('(hover: none)').matches,
	pointerCoarse: window.matchMedia('(pointer: coarse)').matches,
	pointerFine: window.matchMedia('(pointer: fine)').matches,
	userAgent: navigator.userAgent
}));
out('matchMedia probe (iPhone 13 emulation):', JSON.stringify(hoverProbe));

// Wait until Map.svelte has finished its data-hydration (poll for the
// `jobs` source rather than trusting `map.idle`, which fires too early
// when tile requests are still in flight).
await page
	.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 })
	.catch(() => out('WARN: jobs source never added — Map.svelte data hydration stalled'));
await page.waitForTimeout(500);

const handle = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);

const snapshotWith = (h) => async (label) => {
	const s = await page.evaluate((m) => {
		const props = m.selectedFeature?.properties ?? {};
		return {
			selectedFeature: m.selectedFeature
				? {
					source: m.selectedFeature.source,
					id: props.id ?? null,
					code: props.code ?? null,
					name: props.name ?? null,
					city: props.city ?? null
				}
				: null,
			jobStack: m.jobStack ? { label: m.jobStack.label, count: m.jobStack.items?.length ?? 0 } : null,
			sheetPage: m.browseSheetPage,
			sheetExpanded: m.browseSheetExpanded
		};
	}, h);
	out(label, JSON.stringify(s));
	return s;
};
const snapshot = snapshotWith(handle);

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
	out(`MARKER PASS — selectedFeature updated A(${idA}) → B(${idB}), sheet expanded.`);
} else if (idA === idB && idA !== null) {
	out(`MARKER FAIL — selection stayed on id=${idA} across both taps. Stuck-sheet repro.`);
} else {
	out(`MARKER UNEXPECTED — idA=${idA} idB=${idB} expandedA=${expandedA} expandedB=${expandedB}`);
}

// =====================================================================
// CASE: tap one locality polygon, then another. Operator-reported repro.
// Localities only render at zoom 5–9 and the click handler calls
// fitFocusedFeature → fitBounds(..., maxZoom:7, duration:700). So the
// map animates between taps; the second tap has to wait for the
// animation OR has to be at a viewport that still includes a second
// locality.
// =====================================================================
out('');
out('--- locality → locality ---');
// Reload the page so the sheet is fresh-collapsed and no marker is
// selected. JSHandle writes to $state proxies don't reliably fire Svelte
// signals (the DOM stays in its prior expanded state even when the
// underlying $state value reads as false), so resetting via a clean
// navigation is the only reliable way to start this case.
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page
	.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 })
	.catch(() => out('WARN: jobs source not added after reload'));
await page.waitForTimeout(500);
// For each visible locality, scan a coarse pixel grid inside its bbox
// for a pixel where the click handler will route to the locality (no
// cluster/marker layer on top). Rural areas of locality polygons (away
// from city-centroid clusters) are where the operator's "tap polygon"
// gesture actually lands; the centroid is often city center, which is
// where markers cluster densely.
const CANDIDATES = [
	{ name: 'Denver', center: [-105.5, 39.5], zoom: 6 },
	{ name: 'Salt Lake', center: [-112, 40.5], zoom: 6 },
	{ name: 'Sacramento', center: [-121, 38.5], zoom: 6 },
	{ name: 'Phoenix', center: [-112, 33.5], zoom: 6 },
	{ name: 'East Coast wide', center: [-74, 41], zoom: 5 }
];

let chosen = null;
for (const cand of CANDIDATES) {
	await page.evaluate((c) => window.__ffMap.jumpTo({ center: c.center, zoom: c.zoom }), cand);
	await page.waitForTimeout(900);
	const probeRes = await page.evaluate(() => {
		const m = window.__ffMap;
		const w = m.getCanvas().clientWidth;
		const h = m.getCanvas().clientHeight;
		const rendered = m.queryRenderedFeatures(undefined, { layers: ['localities-fill'] });
		const byCode = new Map();
		for (const f of rendered) {
			const code = f.properties?.code ?? f.properties?.name ?? f.id;
			if (!code || byCode.has(code)) continue;
			byCode.set(code, { name: f.properties?.name ?? code });
		}
		// Sample a grid across the viewport, group hits by locality code,
		// and within each, prefer pixels where NO marker/cluster covers.
		const candidates = [];
		const STEP = 24;
		for (let x = 30; x < w - 30; x += STEP) {
			for (let y = 30; y < h - 80; y += STEP) {
				const hits = m.queryRenderedFeatures([x, y]);
				const loc = hits.find((f) => f.layer?.id === 'localities-fill');
				if (!loc) continue;
				const code = loc.properties?.code ?? loc.properties?.name ?? loc.id;
				if (!code) continue;
				const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
				candidates.push({ code, name: loc.properties?.name ?? code, x, y, clean: !hasMarker });
			}
		}
		// One clean pixel per code (or fall back to any pixel for that code).
		const dedup = new Map();
		for (const c of candidates) {
			const cur = dedup.get(c.code);
			if (!cur || (c.clean && !cur.clean)) dedup.set(c.code, c);
		}
		return Array.from(dedup.values());
	});
	const cleanOnes = probeRes.filter((t) => t.clean);
	if (cleanOnes.length >= 2) {
		chosen = { ...cand, candidates: cleanOnes };
		out(`viewport ${cand.name}: ${cleanOnes.length} clean polygon hit-points — using this.`);
		break;
	}
	out(`viewport ${cand.name}: ${cleanOnes.length} clean (of ${probeRes.length} unique localities sampled) — try next.`);
}

if (!chosen) {
	out('SKIP — no viewport gave 2 clean (no-cluster) locality centroids. The realistic operator scenario tap-on-cluster path is verified by CASE 1 already.');
}

// Re-acquire handle after the reload (the previous one points at a
// destroyed module instance).
const handle2 = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const snapshot2 = snapshotWith(handle2);

const localityHits = await page.evaluate(() => {
	const m = window.__ffMap;
	const diag = {
		zoom: m.getZoom(),
		visibility: m.getLayoutProperty('localities-fill', 'visibility') ?? 'visible',
		sourceFeatures: m.querySourceFeatures('localities').length,
		hasLayer: !!m.getLayer('localities-fill')
	};
	const rendered = m.queryRenderedFeatures(undefined, { layers: ['localities-fill'] });
	// For each centroid pixel, also report what OTHER layers cover that pixel.
	// The click handler's `layerOrder` puts clusters > markers > localitiesFill,
	// so a marker on top of the polygon centroid hijacks the click.
	const probe = (x, y) => m.queryRenderedFeatures([x, y]).map((f) => f.layer?.id).slice(0, 5);
	const seen = new Set();
	const inView = [];
	for (const f of rendered) {
		const code = f.properties?.code ?? f.properties?.name ?? f.id;
		if (!code || seen.has(code)) continue;
		seen.add(code);
		// Pick a centroid in pixel space by averaging vertices.
		const flat = [];
		const walk = (c) => { if (typeof c[0] === 'number') flat.push(c); else for (const e of c) walk(e); };
		walk(f.geometry.coordinates);
		const lng = flat.reduce((s, [x]) => s + x, 0) / flat.length;
		const lat = flat.reduce((s, [, y]) => s + y, 0) / flat.length;
		const p = m.project([lng, lat]);
		const here = probe(Math.round(p.x), Math.round(p.y));
		// "Clean" = no marker/cluster layer on top — locality should win
		// the click handler's layer-order race.
		const cleanForLocality = !here.some((id) => id === 'job-clusters' || id === 'job-markers' || id === 'job-markers-stack');
		inView.push({ code, name: f.properties?.name ?? code, x: Math.round(p.x), y: Math.round(p.y), here, cleanForLocality });
	}
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	const onScreen = inView.filter((t) => t.x > 20 && t.x < w - 20 && t.y > 20 && t.y < h - 80);
	return { diag, count: inView.length, onScreen };
});
out('locality diag:', JSON.stringify(localityHits.diag));
out('locality candidates on-screen:', localityHits.onScreen.length, 'of', localityHits.count);

const domState = await page.evaluate(() => {
	const sheet = document.querySelector('.sheet');
	const fab = document.querySelector('.filters-fab');
	return {
		sheetClass: sheet?.className,
		sheetHeight: sheet ? sheet.getBoundingClientRect().height : null,
		sheetTop: sheet ? sheet.getBoundingClientRect().top : null,
		fabRect: fab ? fab.getBoundingClientRect() : null
	};
});
out('DOM sheet state:', JSON.stringify(domState));

if (!chosen) {
	out('SKIP locality case — no viewport yielded 2 clean (no-cluster) locality centroids.');
} else {
	out('candidate localities:', JSON.stringify(chosen.candidates.map((t) => ({ name: t.name, x: t.x, y: t.y, clean: t.clean }))));
	const L1 = chosen.candidates[0];
	const L2 = chosen.candidates.slice(1).find((t) => Math.hypot(t.x - L1.x, t.y - L1.y) > 80) ?? chosen.candidates[1];

	const whatsAt = await page.evaluate(({ x, y }) => {
		const m = window.__ffMap;
		const all = m.queryRenderedFeatures([x, y]);
		return all.map((f) => ({ layer: f.layer?.id, src: f.source, hasGeom: !!f.geometry })).slice(0, 8);
	}, { x: L1.x, y: L1.y });
	out(`L1 pixel (${L1.x},${L1.y}) renders:`, JSON.stringify(whatsAt));

	// Hook the map's click event so we can verify the tap actually reaches
	// mapbox-gl's click dispatcher. If it doesn't fire, the tap is being
	// intercepted by a DOM overlay (popup, sheet, or other).
	await page.evaluate(() => {
		window.__ffClicks = [];
		window.__ffMap.on('click', (e) => {
			window.__ffClicks.push({ lng: e.lngLat.lng.toFixed(4), lat: e.lngLat.lat.toFixed(4), point: [e.point.x, e.point.y] });
		});
	});

	out(`tap L1 (${L1.name}) @ (${L1.x},${L1.y})`);
	await page.touchscreen.tap(L1.x + (canvasBox?.x ?? 0), L1.y + (canvasBox?.y ?? 0));
	// Wait for fitBounds animation (700ms in fitFocusedFeature) + a beat.
	await page.waitForTimeout(1100);
	const clicks = await page.evaluate(() => window.__ffClicks);
	out('map click events received:', JSON.stringify(clicks));
	const afterL1 = await snapshot2('after tap L1');

	// Restore the original viewport (the operator's real gesture: after
	// tapping a polygon, fitBounds animates in; they pan/zoom back out
	// to find another polygon before tapping it). Without this, the L2
	// pixel from the original viewport scan would hit a different feature
	// because the projection changed during fitBounds.
	await page.evaluate((c) => window.__ffMap.jumpTo({ center: c.center, zoom: c.zoom }), chosen);
	await page.waitForTimeout(900);
	// Grid-search for a clean L2 hit-point (locality with a code different from L1).
	const L2candidates = await page.evaluate((excludeCode) => {
		const m = window.__ffMap;
		const w = m.getCanvas().clientWidth;
		const h = m.getCanvas().clientHeight;
		const out = [];
		// After L1 selection the sheet auto-expands to 50% of the canvas,
		// so the bottom half is sheet, not map. L2 must be in the top half.
		const STEP = 24;
		const yMax = Math.floor(h * 0.5 - 20);
		for (let x = 30; x < w - 30; x += STEP) {
			for (let y = 30; y < yMax; y += STEP) {
				const hits = m.queryRenderedFeatures([x, y]);
				const loc = hits.find((f) => f.layer?.id === 'localities-fill');
				if (!loc) continue;
				const code = loc.properties?.code ?? loc.properties?.name ?? loc.id;
				if (!code || code === excludeCode) continue;
				const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
				out.push({ code, name: loc.properties?.name ?? code, x, y, clean: !hasMarker });
			}
		}
		const dedup = new Map();
		for (const c of out) {
			const cur = dedup.get(c.code);
			if (!cur || (c.clean && !cur.clean)) dedup.set(c.code, c);
		}
		return Array.from(dedup.values());
	}, L1.code);
	out(`after restoring viewport, L2 candidates (top half, ≠ L1):`, JSON.stringify(L2candidates.map((c) => ({ name: c.name, x: c.x, y: c.y, clean: c.clean }))));

	const L2pick = L2candidates.find((t) => t.clean) ?? L2candidates[0];
	if (!L2pick) {
		out('SKIP — no different locality in the top half after viewport restore. The expanded sheet covers half the canvas and the other locality is below it.');
	} else {
		out(`tap L2 (${L2pick.name}) @ (${L2pick.x},${L2pick.y})`);
		await page.touchscreen.tap(L2pick.x + (canvasBox?.x ?? 0), L2pick.y + (canvasBox?.y ?? 0));
		await page.waitForTimeout(1100);
		const afterL2 = await snapshot2('after tap L2');

		const a = afterL1.selectedFeature;
		const b = afterL2.selectedFeature;
		const aIsLocality = a?.source === 'localities-fill';
		const bIsLocality = b?.source === 'localities-fill';
		const aIdent = a?.code ?? a?.name;
		const bIdent = b?.code ?? b?.name;

		out('---');
		if (aIsLocality && bIsLocality && aIdent && bIdent && aIdent !== bIdent && afterL2.sheetExpanded) {
			out(`LOCALITY PASS — selection updated A(${aIdent}) → B(${bIdent}).`);
		} else if (aIsLocality && bIsLocality && aIdent === bIdent) {
			out(`LOCALITY FAIL — selection stayed on ${aIdent} across both locality taps. Stuck-sheet repro on polygons.`);
		} else {
			out(`LOCALITY UNEXPECTED — aSource=${a?.source} bSource=${b?.source} aIdent=${aIdent} bIdent=${bIdent} bExpanded=${afterL2.sheetExpanded}`);
			if (!aIsLocality) out('  L1 tap landed on:', a?.source ?? 'nothing');
			if (!bIsLocality) out('  L2 tap landed on:', b?.source ?? 'nothing');
		}
	}
}

// =====================================================================
// CASE: realistic locality → locality WITHOUT user panning back. After
// L1 the map fitBounds-animates into L1; the user sees a different view
// and taps another polygon visible in that new view. This is what the
// operator actually does.
// =====================================================================
out('');
out('--- locality → locality without viewport restore ---');
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(500);
const handle3 = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const snapshot3 = snapshotWith(handle3);
await page.evaluate(() => window.__ffMap.jumpTo({ center: [-121, 38.5], zoom: 6 }));
await page.waitForTimeout(900);

const findLocalityHit = async (excludeCode = null) => page.evaluate((exclude) => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	const found = [];
	const yMax = exclude == null ? h - 80 : Math.floor(h * 0.5 - 20);
	for (let x = 30; x < w - 30; x += 24) {
		for (let y = 30; y < yMax; y += 24) {
			const hits = m.queryRenderedFeatures([x, y]);
			const loc = hits.find((f) => f.layer?.id === 'localities-fill');
			if (!loc) continue;
			const code = loc.properties?.code ?? loc.properties?.name ?? loc.id;
			if (!code || code === exclude) continue;
			const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
			found.push({ code, name: loc.properties?.name ?? code, x, y, clean: !hasMarker });
		}
	}
	const dedup = new Map();
	for (const c of found) {
		const cur = dedup.get(c.code);
		if (!cur || (c.clean && !cur.clean)) dedup.set(c.code, c);
	}
	return Array.from(dedup.values());
}, excludeCode);

const r1 = await findLocalityHit(null);
out('initial locality hits:', JSON.stringify(r1.map((c) => ({ name: c.name, x: c.x, y: c.y, clean: c.clean }))));
const X1 = r1.find((c) => c.clean) ?? r1[0];
if (!X1) {
	out('SKIP no-restore — no locality hit on initial viewport');
} else {
	out(`tap X1 (${X1.name}) @ (${X1.x},${X1.y})`);
	await page.touchscreen.tap(X1.x + (canvasBox?.x ?? 0), X1.y + (canvasBox?.y ?? 0));
	await page.waitForTimeout(1100);
	const afterX1 = await snapshot3('after tap X1');

	// Do NOT restore. Find a different locality in the post-animation viewport.
	const r2 = await findLocalityHit(X1.code);
	out('post-animation top-half hits (≠ X1):', JSON.stringify(r2.map((c) => ({ name: c.name, x: c.x, y: c.y, clean: c.clean }))));
	const X2 = r2.find((c) => c.clean) ?? r2[0];
	if (!X2) {
		out('after fitBounds zoomed into X1, NO other locality is visible in the top half. To tap a second locality the operator would have to manually zoom out or pan first.');
	} else {
		out(`tap X2 (${X2.name}) @ (${X2.x},${X2.y})`);
		await page.touchscreen.tap(X2.x + (canvasBox?.x ?? 0), X2.y + (canvasBox?.y ?? 0));
		await page.waitForTimeout(1100);
		const afterX2 = await snapshot3('after tap X2');
		const aCode = afterX1.selectedFeature?.code;
		const bCode = afterX2.selectedFeature?.code;
		const aSrc = afterX1.selectedFeature?.source;
		const bSrc = afterX2.selectedFeature?.source;
		out('---');
		if (aSrc === 'localities-fill' && bSrc === 'localities-fill' && aCode !== bCode) {
			out(`NO-RESTORE LOCALITY PASS — selection updated A(${aCode}) → B(${bCode})`);
		} else if (aCode === bCode && aSrc === bSrc) {
			out(`NO-RESTORE LOCALITY FAIL — selection stayed on ${aCode}. Stuck-sheet repro.`);
		} else {
			out(`NO-RESTORE DIAGNOSTIC — aSrc=${aSrc}/${aCode} bSrc=${bSrc}/${bCode} expandedB=${afterX2.sheetExpanded}`);
		}
	}
}

// =====================================================================
// CASE: rapid double-tap on two polygons. The operator might tap B before
// L1's fitBounds animation (700ms) finishes — a race between the click
// handler's state mutation and the easing camera.
// =====================================================================
out('');
out('--- rapid locality → locality (no wait between taps) ---');
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForFunction(() => !!window.__ffMap?.getSource?.('jobs'), { timeout: 30000 });
await page.waitForTimeout(500);
const handle4 = await page.evaluateHandle(async () => (await import('/src/lib/store.svelte.ts')).mapState);
const snapshot4 = snapshotWith(handle4);
await page.evaluate(() => window.__ffMap.jumpTo({ center: [-121, 38.5], zoom: 6 }));
await page.waitForTimeout(900);

const fastHits = await page.evaluate(() => {
	const m = window.__ffMap;
	const w = m.getCanvas().clientWidth;
	const h = m.getCanvas().clientHeight;
	const found = [];
	for (let x = 30; x < w - 30; x += 24) {
		for (let y = 30; y < h - 80; y += 24) {
			const hits = m.queryRenderedFeatures([x, y]);
			const loc = hits.find((f) => f.layer?.id === 'localities-fill');
			if (!loc) continue;
			const code = loc.properties?.code ?? loc.properties?.name ?? loc.id;
			if (!code) continue;
			const hasMarker = hits.some((f) => ['job-clusters', 'job-markers', 'job-markers-stack'].includes(f.layer?.id));
			found.push({ code, name: loc.properties?.name ?? code, x, y, clean: !hasMarker });
		}
	}
	const dedup = new Map();
	for (const c of found) {
		const cur = dedup.get(c.code);
		if (!cur || (c.clean && !cur.clean)) dedup.set(c.code, c);
	}
	return Array.from(dedup.values()).filter((c) => c.clean);
});

if (fastHits.length < 2) {
	out('SKIP rapid case — fewer than 2 clean locality hits');
} else {
	const R1 = fastHits[0];
	const R2 = fastHits.slice(1).find((t) => Math.hypot(t.x - R1.x, t.y - R1.y) > 60) ?? fastHits[1];
	out(`rapid tap R1 (${R1.name}) → R2 (${R2.name}) with NO delay between taps`);
	// Two real touchscreen taps back-to-back, no wait.
	await page.touchscreen.tap(R1.x + (canvasBox?.x ?? 0), R1.y + (canvasBox?.y ?? 0));
	// Tiny delay to let the click handler fire but NOT for fitBounds to finish.
	await page.waitForTimeout(50);
	await page.touchscreen.tap(R2.x + (canvasBox?.x ?? 0), R2.y + (canvasBox?.y ?? 0));
	await page.waitForTimeout(1500);
	const afterRapid = await snapshot4('after rapid R1+R2');
	out('---');
	if (afterRapid.selectedFeature?.source === 'localities-fill') {
		const code = afterRapid.selectedFeature.code;
		if (code === R2.code) {
			out(`RAPID PASS — final selection = R2 (${code}). No race.`);
		} else if (code === R1.code) {
			out(`RAPID FAIL — final selection = R1 (${code}), R2 tap was eaten by animation. Stuck-sheet repro.`);
		} else {
			out(`RAPID DIAGNOSTIC — final selection = ${code}, neither R1 (${R1.code}) nor R2 (${R2.code}).`);
		}
	} else {
		out(`RAPID DIAGNOSTIC — final selection.source=${afterRapid.selectedFeature?.source ?? 'null'}`);
	}
}

if (errors.length) out('page/console errors:', errors.slice(0, 5));
await browser.close();
