import { describe, it, expect } from 'vitest';
import { resolveArea, urgencyCounts } from './areaCard';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import type { Feature, FeatureCollection, JobDetails } from './data';

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return { ...DEFAULT_FILTERS, agencies: [], geographies: [], ...overrides };
}

function stateFeature(code: string, name: string, extras: Record<string, unknown> = {}): Feature {
	return {
		type: 'Feature',
		geometry: null,
		properties: { state: code, name, ...extras }
	};
}

function localityFeature(code: string, name: string, extras: Record<string, unknown> = {}): Feature {
	return {
		type: 'Feature',
		geometry: null,
		properties: { code, name, ...extras }
	};
}

function fc(features: Feature[]): FeatureCollection {
	return { type: 'FeatureCollection', features };
}

function job(overrides: Partial<JobDetails> = {}): JobDetails {
	return {
		id: 1,
		title: 'Test',
		close_date: null,
		...overrides
	};
}

describe('resolveArea', () => {
	const states = fc([
		stateFeature('IL', 'Illinois', { postings: 47 }),
		stateFeature('TX', 'Texas')
	]);
	const localities = fc([
		localityFeature('CHI', 'Chicago–Naperville, IL–IN–WI', { postings: 47 }),
		localityFeature('DCB', 'Washington–Baltimore, DC–MD–VA–WV–PA')
	]);

	it('returns Nationwide when no geo chips are set', () => {
		const area = resolveArea(filters(), states, localities);
		expect(area.scope).toBe('nationwide');
		expect(area.label).toBe('Nationwide');
		expect(area.code).toBeNull();
		expect(area.feature).toBeNull();
	});

	it('returns Nationwide when only county chips are present', () => {
		const area = resolveArea(filters({ geographies: ['county:17031'] }), states, localities);
		expect(area.scope).toBe('nationwide');
	});

	it('returns Nationwide when the geographies array is empty/undefined', () => {
		const area = resolveArea({ ...filters(), geographies: [] }, states, localities);
		expect(area.scope).toBe('nationwide');
	});

	it('resolves a state chip to the matching state feature', () => {
		const area = resolveArea(filters({ geographies: ['state:IL'] }), states, localities);
		expect(area.scope).toBe('state');
		expect(area.code).toBe('IL');
		expect(area.label).toBe('Illinois');
		expect(area.feature?.properties?.name).toBe('Illinois');
	});

	it('resolves a state chip even when no state collection feature matches', () => {
		const area = resolveArea(filters({ geographies: ['state:ZZ'] }), states, localities);
		expect(area.scope).toBe('state');
		expect(area.code).toBe('ZZ');
		expect(area.label).toBe('ZZ');
		expect(area.feature).toBeNull();
	});

	it('resolves a locality chip and prefers it over a state chip', () => {
		const area = resolveArea(
			filters({ geographies: ['state:IL', 'locality:CHI'] }),
			states,
			localities
		);
		expect(area.scope).toBe('locality');
		expect(area.code).toBe('CHI');
		expect(area.label).toBe('Chicago–Naperville, IL–IN–WI');
		expect(area.feature?.properties?.code).toBe('CHI');
	});

	it('uses the first chip when multiple chips of the same type are present', () => {
		const area = resolveArea(
			filters({ geographies: ['state:IL', 'state:TX'] }),
			states,
			localities
		);
		expect(area.scope).toBe('state');
		expect(area.code).toBe('IL');
	});

	it('skips county chips and falls through to the next chip', () => {
		const area = resolveArea(
			filters({ geographies: ['county:17031', 'state:IL'] }),
			states,
			localities
		);
		expect(area.scope).toBe('state');
		expect(area.code).toBe('IL');
	});

	it('is case-insensitive on chip codes', () => {
		const area = resolveArea(filters({ geographies: ['locality:chi'] }), states, localities);
		expect(area.scope).toBe('locality');
		expect(area.code).toBe('CHI');
	});
});

describe('urgencyCounts', () => {
	// Pin "today" so the time-of-day part is irrelevant.
	const today = new Date('2026-05-20T12:00:00');

	function days(offset: number): string {
		const d = new Date(today);
		d.setDate(d.getDate() + offset);
		return d.toISOString().slice(0, 10);
	}

	it('returns zero counts for empty input', () => {
		expect(urgencyCounts([], today)).toEqual({ today: 0, le3d: 0, le7d: 0 });
	});

	it('counts a job closing today in all three buckets', () => {
		expect(urgencyCounts([job({ close_date: days(0) })], today)).toEqual({
			today: 1,
			le3d: 1,
			le7d: 1
		});
	});

	it('counts a job closing in 3 days in le3d and le7d but not today', () => {
		expect(urgencyCounts([job({ close_date: days(3) })], today)).toEqual({
			today: 0,
			le3d: 1,
			le7d: 1
		});
	});

	it('counts a job closing in 7 days in le7d only', () => {
		expect(urgencyCounts([job({ close_date: days(7) })], today)).toEqual({
			today: 0,
			le3d: 0,
			le7d: 1
		});
	});

	it('ignores jobs closing more than 7 days out', () => {
		expect(urgencyCounts([job({ close_date: days(14) })], today)).toEqual({
			today: 0,
			le3d: 0,
			le7d: 0
		});
	});

	it('ignores jobs with no close_date or already-closed dates', () => {
		const list = [
			job({ id: 1, close_date: null }),
			job({ id: 2, close_date: undefined }),
			job({ id: 3, close_date: days(-1) }),
			job({ id: 4, close_date: 'not-a-date' })
		];
		expect(urgencyCounts(list, today)).toEqual({ today: 0, le3d: 0, le7d: 0 });
	});

	it('aggregates a mixed batch correctly', () => {
		const list = [
			job({ id: 1, close_date: days(0) }), // today: +1, le3: +1, le7: +1
			job({ id: 2, close_date: days(1) }), // le3: +1, le7: +1
			job({ id: 3, close_date: days(3) }), // le3: +1, le7: +1
			job({ id: 4, close_date: days(5) }), // le7: +1
			job({ id: 5, close_date: days(8) }), // ignored
			job({ id: 6, close_date: null }) // ignored
		];
		expect(urgencyCounts(list, today)).toEqual({ today: 1, le3d: 3, le7d: 4 });
	});
});
