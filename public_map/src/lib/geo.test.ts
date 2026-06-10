import { describe, it, expect } from 'vitest';
import {
	haversineMiles,
	nearestRadiusMiles,
	radiusMatch,
	coordsByJobId,
	radiusToParam,
	radiusFromParam,
	normalizeRadii,
	type RadiusChip
} from './geo';
import type { FeatureCollection } from './data';

// [lng, lat]
const NYC: [number, number] = [-74.006, 40.7128];
const LA: [number, number] = [-118.2437, 34.0522];
const CHI: [number, number] = [-87.6298, 41.8781];
const ANC: [number, number] = [-149.9003, 61.2181];

const chip = (center: [number, number], miles: number, includeRemote = true): RadiusChip => ({
	center,
	miles,
	label: 'X',
	includeRemote
});

describe('haversineMiles', () => {
	it('matches known great-circle distances within tolerance', () => {
		// City-center great-circle distances (statute miles). Bands are ±15 mi
		// around the accepted values so the test confirms correctness without
		// pinning to one source's exact airport-vs-center coordinates.
		expect(haversineMiles(NYC, LA)).toBeGreaterThan(2435);
		expect(haversineMiles(NYC, LA)).toBeLessThan(2460);
		expect(haversineMiles(NYC, CHI)).toBeGreaterThan(695);
		expect(haversineMiles(NYC, CHI)).toBeLessThan(725);
		expect(haversineMiles(CHI, LA)).toBeGreaterThan(1730);
		expect(haversineMiles(CHI, LA)).toBeLessThan(1760);
		expect(haversineMiles(ANC, NYC)).toBeGreaterThan(3355);
		expect(haversineMiles(ANC, NYC)).toBeLessThan(3385);
	});
	it('is zero for identical points and symmetric', () => {
		expect(haversineMiles(NYC, NYC)).toBeCloseTo(0, 5);
		expect(haversineMiles(NYC, LA)).toBeCloseTo(haversineMiles(LA, NYC), 6);
	});
	it('returns Infinity for non-finite input', () => {
		expect(haversineMiles([NaN, 0], NYC)).toBe(Number.POSITIVE_INFINITY);
	});
});

describe('nearestRadiusMiles', () => {
	it('returns the closest in-range chip distance, else null', () => {
		const radii = [chip(CHI, 50), chip(NYC, 50)];
		// A point ~10 mi from NYC is inside the NYC chip.
		const nearNyc: [number, number] = [-74.17, 40.73];
		const d = nearestRadiusMiles(nearNyc, radii);
		expect(d).not.toBeNull();
		expect(d!).toBeLessThan(50);
		// A point far from every chip is null.
		expect(nearestRadiusMiles(LA, radii)).toBeNull();
	});
	it('null when no coord or no chips', () => {
		expect(nearestRadiusMiles(null, [chip(NYC, 50)])).toBeNull();
		expect(nearestRadiusMiles(NYC, [])).toBeNull();
	});
});

describe('radiusMatch', () => {
	it('true when a coord is within any chip', () => {
		expect(radiusMatch([[-74.17, 40.73]], false, [chip(NYC, 50)])).toBe(true);
		expect(radiusMatch([LA], false, [chip(NYC, 50)])).toBe(false);
	});
	it('multiple chips OR together', () => {
		expect(radiusMatch([LA], false, [chip(NYC, 50), chip(LA, 50)])).toBe(true);
	});
	it('anywhere-remote is included by a remote-including chip, excluded otherwise', () => {
		expect(radiusMatch([], true, [chip(NYC, 50, true)])).toBe(true);
		expect(radiusMatch([], true, [chip(NYC, 50, false)])).toBe(false);
	});
	it('no chips means no constraint (true)', () => {
		expect(radiusMatch([LA], false, [])).toBe(true);
	});
	it('multi-location posting matches if ANY coord is in range', () => {
		expect(radiusMatch([LA, [-74.17, 40.73]], false, [chip(NYC, 50)])).toBe(true);
	});
});

describe('coordsByJobId', () => {
	it('collects all coordinates per posting id', () => {
		const fc: FeatureCollection = {
			type: 'FeatureCollection',
			features: [
				{ type: 'Feature', geometry: { type: 'Point', coordinates: NYC }, properties: { id: 1 } },
				{ type: 'Feature', geometry: { type: 'Point', coordinates: LA }, properties: { id: 1 } },
				{ type: 'Feature', geometry: { type: 'Point', coordinates: CHI }, properties: { id: 2 } },
				{ type: 'Feature', geometry: null, properties: { id: 3 } }
			]
		} as unknown as FeatureCollection;
		const map = coordsByJobId(fc);
		expect(map.get('1')).toHaveLength(2);
		expect(map.get('2')).toHaveLength(1);
		expect(map.has('3')).toBe(false);
	});
	it('null collection yields empty map', () => {
		expect(coordsByJobId(null).size).toBe(0);
	});
});

describe('radius URL param round-trip', () => {
	it('encodes lng,lat,miles and the exclude-remote flag', () => {
		expect(radiusToParam(chip(NYC, 50, true))).toBe('-74.006,40.7128,50');
		expect(radiusToParam(chip(NYC, 25, false))).toBe('-74.006,40.7128,25,xr');
	});
	it('parses back, defaulting includeRemote to true', () => {
		const a = radiusFromParam('-74.006,40.7128,50');
		expect(a?.center).toEqual([-74.006, 40.7128]);
		expect(a?.miles).toBe(50);
		expect(a?.includeRemote).toBe(true);
		const b = radiusFromParam('-87.6298,41.8781,100,xr');
		expect(b?.miles).toBe(100);
		expect(b?.includeRemote).toBe(false);
	});
	it('rejects malformed values', () => {
		expect(radiusFromParam('')).toBeNull();
		expect(radiusFromParam('1,2')).toBeNull();
		expect(radiusFromParam('a,b,c')).toBeNull();
		expect(radiusFromParam('1,2,0')).toBeNull();
	});
});

describe('normalizeRadii', () => {
	it('coerces objects, drops bad entries, dedups by center+miles', () => {
		const out = normalizeRadii([
			{ center: NYC, miles: 50, label: 'NYC', includeRemote: true },
			{ center: NYC, miles: 50, label: 'NYC dup', includeRemote: true },
			{ center: [1], miles: 50 }, // bad center
			{ center: LA, miles: 0 }, // bad miles
			'nonsense'
		]);
		expect(out).toHaveLength(1);
		expect(out[0].center).toEqual(NYC);
	});
	it('non-array yields []', () => {
		expect(normalizeRadii(undefined)).toEqual([]);
	});
});
