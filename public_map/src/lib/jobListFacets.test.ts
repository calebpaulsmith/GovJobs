import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FACETS, rowMatchesSearch, type FacetKey } from './jobListFacets';
import type { JobDetails } from './data';

function job(overrides: Partial<JobDetails> = {}): JobDetails {
	return {
		id: 1,
		title: 'Program Analyst',
		agency: 'Department of Veterans Affairs',
		agency_code: 'VATA',
		series: '0343',
		pay_plan: 'GS',
		grade_low: '12',
		grade_high: '13',
		salary_min: 95_000,
		salary_max: 124_000,
		salary_type: 'per_year',
		remote_status: 'no remote',
		open_date: '2026-05-01',
		close_date: '2026-06-01',
		hiring_paths: 'public',
		locality_code: 'DCB',
		locations: [{ city: 'Washington', state: 'DC', location_text: 'Washington, DC' }],
		...overrides
	};
}

function facet(key: FacetKey) {
	const def = FACETS.find((f) => f.key === key);
	if (!def) throw new Error(`facet ${key} missing`);
	return def;
}

// --- FACETS ordering (PR contract) ---

describe('FACETS', () => {
	it('exports the four PR-C facets in the spec order', () => {
		expect(FACETS.map((f) => f.key)).toEqual([
			'gs_family',
			'remote_eligible',
			'closing_7d',
			'hide_viewed'
		]);
	});

	it('each facet has a human label', () => {
		for (const f of FACETS) {
			expect(typeof f.label).toBe('string');
			expect(f.label.length).toBeGreaterThan(0);
		}
	});
});

// --- gs_family ---

describe('gs_family facet', () => {
	const f = facet('gs_family');
	it('matches GS', () => {
		expect(f.match(job({ pay_plan: 'GS' }))).toBe(true);
	});
	it('matches every G-prefixed plan code', () => {
		for (const code of ['GS', 'GL', 'GM', 'GP', 'GR', 'GG', 'GW', 'gs']) {
			expect(f.match(job({ pay_plan: code }))).toBe(true);
		}
	});
	it('rejects non-G plans', () => {
		for (const code of ['ES', 'WG', 'WS', 'AD', 'FP', 'AT', 'SV', 'NH']) {
			expect(f.match(job({ pay_plan: code }))).toBe(false);
		}
	});
	it('rejects null / empty pay_plan', () => {
		expect(f.match(job({ pay_plan: null }))).toBe(false);
		expect(f.match(job({ pay_plan: '' }))).toBe(false);
	});
});

// --- remote_eligible ---

describe('remote_eligible facet', () => {
	const f = facet('remote_eligible');
	it('matches remote', () => {
		expect(f.match(job({ remote_status: 'remote' }))).toBe(true);
		expect(f.match(job({ remote_status: 'Remote' }))).toBe(true);
	});
	it('matches hybrid', () => {
		expect(f.match(job({ remote_status: 'hybrid' }))).toBe(true);
		expect(f.match(job({ remote_status: 'HYBRID' }))).toBe(true);
	});
	it('rejects onsite / unknown / null', () => {
		expect(f.match(job({ remote_status: 'onsite' }))).toBe(false);
		expect(f.match(job({ remote_status: 'no remote' }))).toBe(false);
		expect(f.match(job({ remote_status: null }))).toBe(false);
		expect(f.match(job({ remote_status: '' }))).toBe(false);
	});
});

// --- closing_7d ---

describe('closing_7d facet', () => {
	const f = facet('closing_7d');

	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-05-20T12:00:00Z'));
	});
	afterEach(() => {
		vi.useRealTimers();
	});

	it('matches closing today (critical)', () => {
		expect(f.match(job({ close_date: '2026-05-20' }))).toBe(true);
	});
	it('matches closing tomorrow (critical)', () => {
		expect(f.match(job({ close_date: '2026-05-21' }))).toBe(true);
	});
	it('matches closing in 7 days (soon)', () => {
		expect(f.match(job({ close_date: '2026-05-27' }))).toBe(true);
	});
	it('rejects closing in 8 days', () => {
		expect(f.match(job({ close_date: '2026-05-28' }))).toBe(false);
	});
	it('rejects already-closed postings', () => {
		expect(f.match(job({ close_date: '2026-05-01' }))).toBe(false);
	});
	it('rejects missing close_date', () => {
		expect(f.match(job({ close_date: null }))).toBe(false);
	});
});

// --- hide_viewed ---

describe('hide_viewed facet', () => {
	const f = facet('hide_viewed');
	it('keeps un-viewed jobs', () => {
		expect(f.match(job({ id: 1 }), { isViewed: () => false })).toBe(true);
	});
	it('drops viewed jobs', () => {
		expect(f.match(job({ id: 1 }), { isViewed: (id) => id === '1' })).toBe(false);
	});
	it('treats missing context as keep-all (defensive)', () => {
		expect(f.match(job({ id: 1 }))).toBe(true);
	});
});

// --- rowMatchesSearch ---

describe('rowMatchesSearch', () => {
	it('empty / whitespace query returns true', () => {
		expect(rowMatchesSearch(job(), {}, '')).toBe(true);
		expect(rowMatchesSearch(job(), {}, '   ')).toBe(true);
	});

	it('matches against title (case-insensitive)', () => {
		expect(rowMatchesSearch(job({ title: 'Program Analyst' }), {}, 'analyst')).toBe(true);
		expect(rowMatchesSearch(job({ title: 'Program Analyst' }), {}, 'ANALYST')).toBe(true);
	});

	it('matches against agency display name', () => {
		expect(rowMatchesSearch(job({ agency: 'NASA' }), {}, 'nasa')).toBe(true);
	});

	it('matches against locality_code', () => {
		expect(rowMatchesSearch(job({ locality_code: 'DCB' }), {}, 'dcb')).toBe(true);
	});

	it('matches against locations[].city and locations[].state', () => {
		const j = job({
			locations: [
				{ city: 'Chicago', state: 'IL' },
				{ city: 'Boston', state: 'MA' }
			]
		});
		expect(rowMatchesSearch(j, {}, 'chicago')).toBe(true);
		expect(rowMatchesSearch(j, {}, 'IL')).toBe(true);
		expect(rowMatchesSearch(j, {}, 'boston')).toBe(true);
		expect(rowMatchesSearch(j, {}, 'MA')).toBe(true);
	});

	it('falls back to scoped-mode props when detail is undefined', () => {
		expect(
			rowMatchesSearch(undefined, { title: 'Border Patrol Agent', city: 'El Paso' }, 'patrol')
		).toBe(true);
		expect(
			rowMatchesSearch(undefined, { title: 'Border Patrol Agent', city: 'El Paso' }, 'el paso')
		).toBe(true);
	});

	it('returns false when the needle is nowhere', () => {
		expect(rowMatchesSearch(job(), {}, 'zzznomatch')).toBe(false);
	});

	it('handles missing optional fields without throwing', () => {
		const sparse = job({
			agency: null,
			agency_code: null,
			locality_code: null,
			locations: undefined
		});
		expect(rowMatchesSearch(sparse, {}, 'program')).toBe(true);
		expect(rowMatchesSearch(sparse, {}, 'zzz')).toBe(false);
	});
});
