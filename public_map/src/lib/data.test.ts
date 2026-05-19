import { describe, expect, it } from 'vitest';
import { mergeDicts, mergeFeatureCollections, partFilename } from './data';
import type { Feature, FeatureCollection } from './data';

function feature(id: number): Feature {
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [id, -id] },
		properties: { id }
	};
}

function collection(ids: number[]): FeatureCollection {
	return { type: 'FeatureCollection', features: ids.map(feature) };
}

describe('partFilename', () => {
	it('keeps the original name for part 1', () => {
		expect(partFilename('jobs.geojson', 1)).toBe('jobs.geojson');
	});

	it('inserts the part number before the final extension', () => {
		expect(partFilename('jobs.geojson', 2)).toBe('jobs.2.geojson');
		expect(partFilename('jobs.geojson', 3)).toBe('jobs.3.geojson');
		expect(partFilename('jobs_detail.json', 2)).toBe('jobs_detail.2.json');
	});

	it('appends the index when there is no extension', () => {
		expect(partFilename('noext', 2)).toBe('noext.2');
	});
});

describe('mergeFeatureCollections', () => {
	it('concatenates features from every part in order', () => {
		const merged = mergeFeatureCollections([collection([1, 2]), collection([3, 4, 5])]);
		expect(merged.type).toBe('FeatureCollection');
		expect(merged.features.map((f) => f.properties?.id)).toEqual([1, 2, 3, 4, 5]);
	});

	it('round-trips a single part unchanged', () => {
		const original = collection([10, 11, 12]);
		const merged = mergeFeatureCollections([original]);
		expect(merged.features).toEqual(original.features);
	});

	it('handles empty parts', () => {
		const merged = mergeFeatureCollections([collection([]), collection([7]), collection([])]);
		expect(merged.features.map((f) => f.properties?.id)).toEqual([7]);
	});
});

describe('mergeDicts', () => {
	it('shallow-merges several dicts into one', () => {
		const merged = mergeDicts([
			{ a: { id: 1 }, b: { id: 2 } },
			{ c: { id: 3 } }
		]);
		expect(Object.keys(merged).sort()).toEqual(['a', 'b', 'c']);
		expect(merged.c).toEqual({ id: 3 });
	});

	it('round-trips a single dict unchanged', () => {
		const original = { x: { id: 9 }, y: { id: 8 } };
		expect(mergeDicts([original])).toEqual(original);
	});

	it('lets later parts override earlier keys', () => {
		const merged = mergeDicts([{ k: { id: 1 } }, { k: { id: 2 } }]);
		expect(merged.k).toEqual({ id: 2 });
	});

	it('returns an empty dict for no parts', () => {
		expect(mergeDicts([])).toEqual({});
	});
});
