import { describe, expect, it } from 'vitest';
import type { Feature, FeatureCollection } from './data';
import { DEFAULT_FILTERS } from './filters';
import { geometryBbox, interiorPoint, pointInGeometry } from './geo';
import {
	NATIONWIDE_AREA,
	areaAtPoint,
	areaToParam,
	areasForLevel,
	filtersForArea,
	findArea,
	jobIdsInArea,
	levelForZoom,
	metroPrimaryState,
	parseAreaParam,
	areaParamForListScope,
	resolveDefaultArea,
	type AreaCollections
} from './analysisArea';

function square(x0: number, y0: number, x1: number, y1: number): GeoJSON.Polygon {
	return { type: 'Polygon', coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]] };
}
function fc(features: Feature[]): FeatureCollection {
	return { type: 'FeatureCollection', features } as FeatureCollection;
}
function feat(geometry: GeoJSON.Geometry, properties: Record<string, unknown>): Feature {
	return { type: 'Feature', geometry, properties };
}

// A toy world: state CO = [0,0]-[10,10]; locality DEN = [2,2]-[5,5];
// metro 19740 "Denver-Aurora, CO" = [1,1]-[6,6]; county 08031 = [3,3]-[4,4].
const cols: AreaCollections = {
	states: fc([feat(square(0, 0, 10, 10), { state: 'CO', name: 'Colorado' })]),
	localities: fc([feat(square(2, 2, 5, 5), { code: 'DEN', name: 'Denver-Aurora CO' })]),
	metros: fc([feat(square(1, 1, 6, 6), { cbsa_code: '19740', name: 'Denver-Aurora, CO' })]),
	counties: fc([feat(square(3, 3, 4, 4), { fips: '08031', name: 'Denver', state: 'CO' })])
};

describe('point-in-polygon', () => {
	it('handles inside, outside and holes', () => {
		const withHole: GeoJSON.Polygon = {
			type: 'Polygon',
			coordinates: [square(0, 0, 10, 10).coordinates[0], square(4, 4, 6, 6).coordinates[0]]
		};
		expect(pointInGeometry([1, 1], withHole)).toBe(true);
		expect(pointInGeometry([5, 5], withHole)).toBe(false);
		expect(pointInGeometry([11, 1], withHole)).toBe(false);
	});
	it('handles MultiPolygon', () => {
		const mp: GeoJSON.MultiPolygon = {
			type: 'MultiPolygon',
			coordinates: [square(0, 0, 1, 1).coordinates, square(5, 5, 6, 6).coordinates]
		};
		expect(pointInGeometry([5.5, 5.5], mp)).toBe(true);
		expect(pointInGeometry([3, 3], mp)).toBe(false);
		expect(geometryBbox(mp)).toEqual([0, 0, 6, 6]);
	});
	it('interiorPoint lands inside a concave shape', () => {
		// L-shape whose bbox center (5,5) is outside.
		const L: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 2], [2, 2], [2, 10], [0, 10], [0, 0]]] };
		const p = interiorPoint(L)!;
		expect(pointInGeometry(p, L)).toBe(true);
	});
});

describe('analysis areas', () => {
	it('finds areas by code with labels and primary states', () => {
		expect(findArea('county', '08031', cols)).toMatchObject({ label: 'Denver County, CO', primaryState: 'CO' });
		expect(findArea('metro', '19740', cols)).toMatchObject({ label: 'Denver-Aurora, CO', primaryState: 'CO' });
		expect(findArea('locality', 'den', cols)).toMatchObject({ code: 'DEN', primaryState: 'CO' });
		expect(findArea('state', 'CO', cols)).toMatchObject({ label: 'Colorado', primaryState: 'CO' });
		expect(findArea('nationwide', null, cols)).toBe(NATIONWIDE_AREA);
		expect(findArea('county', '99999', cols)).toBeNull();
	});

	it('resolves the enclosing area at each level from a point', () => {
		const pt: [number, number] = [3.5, 3.5];
		expect(areaAtPoint('county', pt, cols)?.code).toBe('08031');
		expect(areaAtPoint('metro', pt, cols)?.code).toBe('19740');
		expect(areaAtPoint('locality', pt, cols)?.code).toBe('DEN');
		expect(areaAtPoint('state', pt, cols)?.code).toBe('CO');
		expect(areaAtPoint('county', [8, 8], cols)).toBeNull();
		expect(areaAtPoint('state', pt, cols)?.anchor).toEqual(pt);
	});

	it('maps zoom to a level', () => {
		expect(levelForZoom(3.5)).toBe('nationwide');
		expect(levelForZoom(5.5)).toBe('state');
		expect(levelForZoom(7)).toBe('locality');
		expect(levelForZoom(9)).toBe('county');
		expect(levelForZoom(undefined)).toBe('nationwide');
	});

	it('default area: tapped polygon > geography chip > map center > nationwide', () => {
		const vp = { center: [3.5, 3.5] as [number, number], zoom: 9 };
		expect(
			resolveDefaultArea({ selected: { level: 'metro', code: '19740' }, filters: { geographies: ['state:CO'] }, viewport: vp }, cols).level
		).toBe('metro');
		expect(resolveDefaultArea({ selected: null, filters: { geographies: ['state:CO', 'locality:DEN'] }, viewport: vp }, cols).level).toBe('locality');
		expect(resolveDefaultArea({ selected: null, filters: { geographies: [] }, viewport: vp }, cols).level).toBe('county');
		expect(resolveDefaultArea({ selected: null, filters: null, viewport: { center: [3.5, 3.5], zoom: 4 } }, cols)).toBe(NATIONWIDE_AREA);
		// Zoomed to county level outside any county/metro → falls back to the state.
		expect(resolveDefaultArea({ selected: null, filters: null, viewport: { center: [8, 8], zoom: 9 } }, cols).level).toBe('state');
		// Nothing at all under the point → nationwide.
		expect(resolveDefaultArea({ selected: null, filters: null, viewport: { center: [50, 50], zoom: 9 } }, cols)).toBe(NATIONWIDE_AREA);
	});

	it('metroPrimaryState parses the trailing state list', () => {
		expect(metroPrimaryState('Allentown-Bethlehem-Easton, PA-NJ')).toBe('PA');
		expect(metroPrimaryState('No state here')).toBeNull();
	});

	it('URL codec round-trips and rejects junk', () => {
		expect(areaToParam({ level: 'county', code: '08031' })).toBe('county:08031');
		expect(areaToParam(NATIONWIDE_AREA)).toBe('nationwide');
		expect(parseAreaParam('county:08031')).toEqual({ level: 'county', code: '08031' });
		expect(parseAreaParam('nationwide')).toEqual({ level: 'nationwide', code: null });
		expect(parseAreaParam('planet:3')).toBeNull();
		expect(parseAreaParam('state:')).toBeNull();
		expect(parseAreaParam(null)).toBeNull();
	});

	it('filtersForArea replaces geography/radius chips and keeps the rest', () => {
		const base = { ...DEFAULT_FILTERS, agencies: ['HSCB'], geographies: ['state:TX'], radii: [{ center: [0, 0] as [number, number], miles: 50, label: 'x', includeRemote: true }] };
		const st = filtersForArea(base, findArea('state', 'CO', cols)!);
		expect(st.geographies).toEqual(['state:CO']);
		expect(st.radii).toEqual([]);
		expect(st.agencies).toEqual(['HSCB']);
		expect(filtersForArea(base, findArea('county', '08031', cols)!).geographies).toEqual([]);
		expect(filtersForArea(base, NATIONWIDE_AREA).geographies).toEqual([]);
	});

	it('jobIdsInArea scopes by any duty station inside the polygon', () => {
		const coords = new Map<string, Array<[number, number]>>([
			['a', [[3.5, 3.5]]],
			['b', [[8, 8], [3.2, 3.9]]],
			['c', [[8, 8]]]
		]);
		expect([...jobIdsInArea(findArea('county', '08031', cols)!, coords)].sort()).toEqual(['a', 'b']);
	});

	it('areasForLevel lists sorted picker options', () => {
		expect(areasForLevel('county', cols)).toEqual([{ code: '08031', label: 'Denver County, CO' }]);
		expect(areasForLevel('nationwide', cols)).toEqual([]);
	});

	it('areaParamForListScope maps Browse list scopes to analysis areas', () => {
		expect(areaParamForListScope('cbsa', '19740')).toBe('metro:19740');
		expect(areaParamForListScope('county', '08031')).toBe('county:08031');
		expect(areaParamForListScope('state', 'CO')).toBe('state:CO');
		expect(areaParamForListScope('viewport', '')).toBeNull();
		expect(areaParamForListScope('ids', 'x')).toBeNull();
	});
});
