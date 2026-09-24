// ADR-0039 — the Analysis screen's area model.
//
// Browse is for finding jobs; Analysis is for trends and metrics about a
// place. The Analysis screen analyzes ONE area at a time, at one of five
// levels. The user picks the level (and the area within it); on arrival the
// screen defaults to the level/area that best matches where they were in
// Browse:
//
//   1. the polygon they had tapped (state / locality / county / metro), else
//   2. their geography filter chip (locality > state), else
//   3. the map center, at a level chosen from the zoom (national → state →
//      locality/metro → county as you zoom in).
//
// Switching levels keeps the user in the same place: every area carries an
// `anchor` point, and the new level resolves to the area containing it.
//
// Postings are scoped to the area separately from the user's other filters:
// Analysis drops the Browse geography/radius chips and applies the area
// instead (state/locality via the existing chip matchers; county/metro by
// point-in-polygon over duty-station coordinates, since jobs carry no county
// FIPS or CBSA code). Everything else in the filter set — agency, series,
// grade, pay plan, … — carries over unchanged.

import type { Feature, FeatureCollection } from './data';
import type { JobFilters } from './filters';
import { localityPrimaryState } from './compensation';
import { geometryBbox, interiorPoint, pointInGeometry } from './geo';

export type AnalysisLevel = 'nationwide' | 'state' | 'locality' | 'metro' | 'county';

export const ANALYSIS_LEVELS: ReadonlyArray<{ key: AnalysisLevel; label: string }> = [
	{ key: 'nationwide', label: 'Nationwide' },
	{ key: 'state', label: 'State' },
	{ key: 'locality', label: 'Locality' },
	{ key: 'metro', label: 'Metro' },
	{ key: 'county', label: 'County' }
];

export interface AnalysisArea {
	level: AnalysisLevel;
	/** State postal, locality code, CBSA code, or county FIPS. null = nationwide. */
	code: string | null;
	label: string;
	feature: Feature | null;
	/** Best single state for state-only data (HistoricJoa trend, workforce). */
	primaryState: string | null;
	/** A point inside the area, used to find the enclosing area at another level. */
	anchor: [number, number] | null;
}

export interface AreaCollections {
	states: FeatureCollection | null;
	localities: FeatureCollection | null;
	metros: FeatureCollection | null;
	counties: FeatureCollection | null;
}

export const NATIONWIDE_AREA: AnalysisArea = {
	level: 'nationwide',
	code: null,
	label: 'Nationwide',
	feature: null,
	primaryState: null,
	anchor: null
};

const STATE_RE = /^[A-Z]{2}$/;

function codeOf(level: AnalysisLevel, feature: Feature): string {
	const p = feature.properties ?? {};
	switch (level) {
		case 'state':
			return String(p.state ?? '').toUpperCase();
		case 'locality':
			return String(p.code ?? '').toUpperCase();
		case 'metro':
			return String(p.cbsa_code ?? '');
		case 'county':
			return String(p.fips ?? '');
		default:
			return '';
	}
}

function collectionFor(level: AnalysisLevel, cols: AreaCollections): FeatureCollection | null {
	switch (level) {
		case 'state':
			return cols.states;
		case 'locality':
			return cols.localities;
		case 'metro':
			return cols.metros;
		case 'county':
			return cols.counties;
		default:
			return null;
	}
}

/** "Aberdeen, SD" / "Allentown-Bethlehem-Easton, PA-NJ" → "SD" / "PA". */
export function metroPrimaryState(name: string): string | null {
	const comma = name.lastIndexOf(',');
	if (comma === -1) return null;
	const first = name.slice(comma + 1).trim().split(/[-\s]/)[0]?.toUpperCase() ?? '';
	return STATE_RE.test(first) ? first : null;
}

function labelFor(level: AnalysisLevel, feature: Feature): string {
	const p = feature.properties ?? {};
	const name = String(p.name ?? '').trim();
	if (level === 'county') {
		const st = String(p.state ?? '').trim();
		const base = name || String(p.fips ?? '');
		return st ? `${base} County, ${st}` : `${base} County`;
	}
	return name || codeOf(level, feature);
}

function primaryStateFor(level: AnalysisLevel, feature: Feature): string | null {
	const p = feature.properties ?? {};
	switch (level) {
		case 'state':
			return codeOf('state', feature) || null;
		case 'county': {
			const st = String(p.state ?? '').toUpperCase();
			return STATE_RE.test(st) ? st : null;
		}
		case 'locality':
			return localityPrimaryState(codeOf('locality', feature), String(p.name ?? ''));
		case 'metro':
			return metroPrimaryState(String(p.name ?? ''));
		default:
			return null;
	}
}

/** Build an AnalysisArea from a feature at a level. */
export function areaFromFeature(
	level: Exclude<AnalysisLevel, 'nationwide'>,
	feature: Feature,
	anchor?: [number, number] | null
): AnalysisArea {
	return {
		level,
		code: codeOf(level, feature),
		label: labelFor(level, feature),
		feature,
		primaryState: primaryStateFor(level, feature),
		anchor: anchor ?? interiorPoint(feature.geometry)
	};
}

/** Look an area up by level + code. Nationwide ignores the code. */
export function findArea(level: AnalysisLevel, code: string | null, cols: AreaCollections): AnalysisArea | null {
	if (level === 'nationwide') return NATIONWIDE_AREA;
	if (!code) return null;
	const fc = collectionFor(level, cols);
	if (!fc) return null;
	const target = level === 'state' || level === 'locality' ? code.toUpperCase() : code;
	for (const f of fc.features) {
		if (codeOf(level, f) === target) return areaFromFeature(level, f);
	}
	return null;
}

/** The area at `level` containing `point`, or null (e.g. no metro there). */
export function areaAtPoint(
	level: AnalysisLevel,
	point: [number, number] | null,
	cols: AreaCollections
): AnalysisArea | null {
	if (level === 'nationwide') return NATIONWIDE_AREA;
	if (!point) return null;
	const fc = collectionFor(level, cols);
	if (!fc) return null;
	const [lng, lat] = point;
	for (const f of fc.features) {
		const bbox = geometryBbox(f.geometry);
		if (!bbox || lng < bbox[0] || lng > bbox[2] || lat < bbox[1] || lat > bbox[3]) continue;
		if (pointInGeometry(point, f.geometry)) return areaFromFeature(level, f, point);
	}
	return null;
}

/** Zoom → the level that matches what the map was showing. */
export function levelForZoom(zoom: number | null | undefined): AnalysisLevel {
	const z = Number(zoom);
	if (!Number.isFinite(z) || z < 5) return 'nationwide';
	if (z < 6.5) return 'state';
	if (z < 8) return 'locality';
	return 'county';
}

export interface BrowseContext {
	/** A polygon the user had tapped in Browse, if any. */
	selected: { level: Exclude<AnalysisLevel, 'nationwide'>; code: string } | null;
	filters: Pick<JobFilters, 'geographies'> | null;
	viewport: { center: [number, number]; zoom: number } | null;
}

/**
 * Pick the default Analysis area from where the user was in Browse.
 * Falls back one level coarser when the preferred level has nothing at the
 * point (a locality-zoom map center outside every locality → its metro →
 * its state), and finally to Nationwide.
 */
export function resolveDefaultArea(ctx: BrowseContext, cols: AreaCollections): AnalysisArea {
	if (ctx.selected) {
		const hit = findArea(ctx.selected.level, ctx.selected.code, cols);
		if (hit) return hit;
	}
	let firstLocality: string | null = null;
	let firstState: string | null = null;
	for (const chip of ctx.filters?.geographies ?? []) {
		const sep = chip.indexOf(':');
		if (sep === -1) continue;
		const type = chip.slice(0, sep).toLowerCase();
		const code = chip.slice(sep + 1).toUpperCase();
		if (type === 'locality' && firstLocality === null) firstLocality = code;
		else if (type === 'state' && firstState === null) firstState = code;
	}
	if (firstLocality) {
		const hit = findArea('locality', firstLocality, cols);
		if (hit) return hit;
	}
	if (firstState) {
		const hit = findArea('state', firstState, cols);
		if (hit) return hit;
	}
	const vp = ctx.viewport;
	if (vp) {
		const preferred = levelForZoom(vp.zoom);
		const chain: AnalysisLevel[] =
			preferred === 'county'
				? ['county', 'metro', 'state']
				: preferred === 'locality'
					? ['locality', 'metro', 'state']
					: preferred === 'state'
						? ['state']
						: [];
		for (const level of chain) {
			const hit = areaAtPoint(level, vp.center, cols);
			if (hit) return hit;
		}
	}
	return NATIONWIDE_AREA;
}

/** Selectable areas at a level, sorted by label, for the picker. */
export function areasForLevel(level: AnalysisLevel, cols: AreaCollections): Array<{ code: string; label: string }> {
	const fc = collectionFor(level, cols);
	if (!fc) return [];
	const out: Array<{ code: string; label: string }> = [];
	for (const f of fc.features) {
		const code = codeOf(level, f);
		if (!code) continue;
		out.push({ code, label: labelFor(level, f) });
	}
	out.sort((a, b) => a.label.localeCompare(b.label));
	return out;
}

// --- URL codec: ?area=nationwide | state:CO | locality:DEN | metro:19740 | county:08031
export function areaToParam(area: Pick<AnalysisArea, 'level' | 'code'>): string {
	return area.level === 'nationwide' || !area.code ? 'nationwide' : `${area.level}:${area.code}`;
}

export function parseAreaParam(value: string | null | undefined): { level: AnalysisLevel; code: string | null } | null {
	if (!value) return null;
	if (value === 'nationwide') return { level: 'nationwide', code: null };
	const sep = value.indexOf(':');
	if (sep === -1) return null;
	const level = value.slice(0, sep) as AnalysisLevel;
	const code = value.slice(sep + 1).trim();
	if (!code || !ANALYSIS_LEVELS.some((l) => l.key === level) || level === 'nationwide') return null;
	return { level, code };
}

/**
 * The filter set Analysis applies for an area: the user's filters with
 * Browse's geography + radius chips replaced by the area. County and metro
 * carry no chip (no job field to match) — callers scope those by
 * `jobIdsInArea` instead.
 */
export function filtersForArea(filters: JobFilters, area: AnalysisArea): JobFilters {
	const geographies =
		area.level === 'state' || area.level === 'locality' ? [`${area.level}:${area.code}`] : [];
	return { ...filters, geographies, radii: [] };
}

/** True when the area needs point-in-polygon scoping (no job field to match). */
export function needsPolygonScope(area: AnalysisArea): boolean {
	return area.level === 'metro' || area.level === 'county';
}

/**
 * Posting ids with at least one duty station inside the area's polygon.
 * Only meaningful for metro/county; bbox-prefiltered.
 */
export function jobIdsInArea(
	area: AnalysisArea,
	coordsById: Map<string, Array<[number, number]>>
): Set<string> {
	const out = new Set<string>();
	const geom = area.feature?.geometry;
	const bbox = geometryBbox(geom);
	if (!geom || !bbox) return out;
	for (const [id, coords] of coordsById) {
		for (const pt of coords) {
			if (pt[0] < bbox[0] || pt[0] > bbox[2] || pt[1] < bbox[1] || pt[1] > bbox[3]) continue;
			if (pointInGeometry(pt, geom)) {
				out.add(id);
				break;
			}
		}
	}
	return out;
}

/**
 * `?area=` value for a Browse polygon-scoped list (the "Analyze this area"
 * link), or null for non-area scopes (viewport, cluster ids).
 */
export function areaParamForListScope(scope: string, code: string): string | null {
	if (!code) return null;
	switch (scope) {
		case 'state':
		case 'locality':
		case 'county':
			return `${scope}:${code}`;
		case 'cbsa':
			return `metro:${code}`;
		default:
			return null;
	}
}
