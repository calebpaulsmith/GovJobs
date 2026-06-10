import { describe, it, expect } from 'vitest';
import {
	DEFAULT_FILTERS,
	matchesJobDetail,
	filterJobDetails,
	isPostedWithin,
	normalizeFilters,
	filtersFromSearchParams,
	writeFiltersToSearchParams,
	parseHiringPaths,
	type JobFilters
} from './filters';
import type { JobDetails } from './data';

function job(overrides: Partial<JobDetails> = {}): JobDetails {
	return {
		id: 1,
		title: 'Emergency Management Specialist',
		agency: 'Federal Emergency Management Agency',
		department: 'Department of Homeland Security',
		agency_code: 'HSCB',
		series: '0089',
		pay_plan: 'GS',
		grade_low: '12',
		grade_high: '13',
		salary_min: 95000,
		salary_max: 130000,
		salary_type: 'per_year',
		remote_status: 'onsite',
		close_date: '2026-06-01',
		hiring_paths: 'public',
		url: 'https://example.gov/job/1',
		locations: [{ city: 'Chicago, Illinois', state: 'IL' }],
		...overrides
	};
}

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return { ...DEFAULT_FILTERS, agencies: [], geographies: [], ...overrides };
}

describe('matchesJobDetail', () => {
	it('passes every job when no filters are active', () => {
		expect(matchesJobDetail(job(), filters())).toBe(true);
	});

	it('matches agencies by code, not display text', () => {
		expect(matchesJobDetail(job(), filters({ agencies: ['HSCB'] }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ agencies: ['NN15'] }))).toBe(false);
		// Case-insensitive on the job's stored code.
		expect(matchesJobDetail(job({ agency_code: 'hscb' }), filters({ agencies: ['HSCB'] }))).toBe(true);
	});

	it('matches any selected pay plan (OR within the facet)', () => {
		expect(matchesJobDetail(job(), filters({ payPlans: ['GS'] }))).toBe(true);
		expect(matchesJobDetail(job({ pay_plan: 'WG' }), filters({ payPlans: ['GS'] }))).toBe(false);
		// Multiple selected pay plans are ORed.
		expect(matchesJobDetail(job({ pay_plan: 'WG' }), filters({ payPlans: ['GS', 'WG'] }))).toBe(true);
	});

	it('matches any selected series (OR within the facet)', () => {
		expect(matchesJobDetail(job(), filters({ series: ['0089'] }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ series: ['0301'] }))).toBe(false);
		expect(matchesJobDetail(job(), filters({ series: ['0301', '0089'] }))).toBe(true);
	});

	it('matches hiring paths parsed from a JSON-array string', () => {
		const j = job({ hiring_paths: '["fed-transition", "public"]' });
		expect(matchesJobDetail(j, filters({ hiringPaths: ['public'] }))).toBe(true);
		expect(matchesJobDetail(j, filters({ hiringPaths: ['vet'] }))).toBe(false);
		// OR across selected paths: matches because the job advertises "public".
		expect(matchesJobDetail(j, filters({ hiringPaths: ['vet', 'public'] }))).toBe(true);
		// Plain-string hiring_paths still works.
		expect(matchesJobDetail(job({ hiring_paths: 'public' }), filters({ hiringPaths: ['public'] }))).toBe(true);
	});

	it('matches remote status', () => {
		expect(matchesJobDetail(job({ remote_status: 'remote' }), filters({ remote: 'remote' }))).toBe(true);
		expect(matchesJobDetail(job({ remote_status: 'onsite' }), filters({ remote: 'remote' }))).toBe(false);
		expect(matchesJobDetail(job({ remote_status: 'hybrid' }), filters({ remote: 'hybrid' }))).toBe(true);
	});

	it('keyword searches title, agency, and location text', () => {
		expect(matchesJobDetail(job(), filters({ keyword: 'emergency' }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ keyword: 'chicago' }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ keyword: 'wildfire' }))).toBe(false);
	});

	it('matches a job whose grade range overlaps the filter range', () => {
		expect(matchesJobDetail(job(), filters({ gradeMin: '13', gradeMax: '15' }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ gradeMin: '14', gradeMax: '15' }))).toBe(false);
	});

	it('matches geography by any of the job locations', () => {
		expect(matchesJobDetail(job(), filters({ geographies: ['state:IL'] }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ geographies: ['state:TX'] }))).toBe(false);
		expect(
			matchesJobDetail(job(), filters({ geographies: ['state:TX', 'state:IL'] }))
		).toBe(true);
	});

	it('matches geography by locality_code', () => {
		expect(matchesJobDetail(job({ locality_code: 'CHI' }), filters({ geographies: ['locality:CHI'] }))).toBe(true);
		expect(matchesJobDetail(job({ locality_code: 'CHI' }), filters({ geographies: ['locality:DCB'] }))).toBe(false);
		// Case-insensitive on the job's stored code.
		expect(matchesJobDetail(job({ locality_code: 'chi' }), filters({ geographies: ['locality:CHI'] }))).toBe(true);
		// 'county:' chips are not yet supported — they match nothing.
		expect(matchesJobDetail(job({ locality_code: 'CHI' }), filters({ geographies: ['county:17031'] }))).toBe(false);
	});

	it('enforces the salary minimum', () => {
		expect(matchesJobDetail(job(), filters({ salaryMin: '90000' }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ salaryMin: '120000' }))).toBe(false);
	});

	it('filters by posted-within window using open_date', () => {
		const recent = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);
		expect(matchesJobDetail(job({ open_date: recent }), filters({ postedWithin: '7' }))).toBe(true);
		expect(matchesJobDetail(job({ open_date: '2000-01-01' }), filters({ postedWithin: '7' }))).toBe(false);
		// Unknown open_date can't be confirmed recent, so a real window excludes it.
		expect(matchesJobDetail(job({ open_date: null }), filters({ postedWithin: '30' }))).toBe(false);
		// All-time (default) ignores open_date entirely.
		expect(matchesJobDetail(job({ open_date: '2000-01-01' }), filters({ postedWithin: '' }))).toBe(true);
	});
});

describe('isPostedWithin', () => {
	const now = new Date('2026-05-27T12:00:00Z');

	it('treats an empty window as no constraint', () => {
		expect(isPostedWithin('2000-01-01', '', now)).toBe(true);
		expect(isPostedWithin(null, '', now)).toBe(true);
	});

	it('includes postings opened inside the window', () => {
		expect(isPostedWithin('2026-05-25', '7', now)).toBe(true);
		expect(isPostedWithin('2026-05-27', '1', now)).toBe(true);
	});

	it('excludes postings opened before the window', () => {
		expect(isPostedWithin('2026-05-10', '7', now)).toBe(false);
		expect(isPostedWithin('2026-05-25', '1', now)).toBe(false);
	});

	it('excludes a missing or unparseable open_date when a window is set', () => {
		expect(isPostedWithin(null, '7', now)).toBe(false);
		expect(isPostedWithin('', '7', now)).toBe(false);
		expect(isPostedWithin('not-a-date', '7', now)).toBe(false);
	});

	it('treats a non-positive or invalid window as no constraint', () => {
		expect(isPostedWithin(null, '0', now)).toBe(true);
		expect(isPostedWithin('not-a-date', 'abc', now)).toBe(true);
	});
});

describe('parseHiringPaths', () => {
	it('parses a JSON-array string into lowercased codes', () => {
		expect(parseHiringPaths('["fed-transition", "PUBLIC"]')).toEqual(['fed-transition', 'public']);
	});
	it('accepts a real array and a delimited string', () => {
		expect(parseHiringPaths(['public', 'vet'])).toEqual(['public', 'vet']);
		expect(parseHiringPaths('public, vet')).toEqual(['public', 'vet']);
	});
	it('returns an empty array for blank/garbage input', () => {
		expect(parseHiringPaths(null)).toEqual([]);
		expect(parseHiringPaths('')).toEqual([]);
		expect(parseHiringPaths('[not json')).toEqual(['[not json']);
	});
});

describe('normalizeFilters migration', () => {
	it('upgrades legacy single-string series/payPlan/hiringPath to arrays', () => {
		const f = normalizeFilters({ series: '0301', payPlan: 'gs', hiringPath: 'Public' });
		expect(f.series).toEqual(['0301']);
		expect(f.payPlans).toEqual(['GS']); // pay plans are uppercased
		expect(f.hiringPaths).toEqual(['public']); // hiring paths are lowercased
	});
	it('accepts the new array form and dedupes', () => {
		const f = normalizeFilters({ payPlans: ['GS', 'gs', 'WG'], series: ['0301', '0301'] });
		expect(f.payPlans).toEqual(['GS', 'WG']);
		expect(f.series).toEqual(['0301']);
	});
	it('defaults missing multi-select facets to empty arrays', () => {
		const f = normalizeFilters({});
		expect(f.series).toEqual([]);
		expect(f.payPlans).toEqual([]);
		expect(f.hiringPaths).toEqual([]);
	});
});

describe('URL round-trip', () => {
	it('reads repeated keys and a legacy single value the same way', () => {
		const fromRepeated = filtersFromSearchParams(
			new URLSearchParams('series=0301&series=0610&payPlan=GS&hiringPath=public')
		);
		expect(fromRepeated.series).toEqual(['0301', '0610']);
		expect(fromRepeated.payPlans).toEqual(['GS']);
		expect(fromRepeated.hiringPaths).toEqual(['public']);
	});
	it('writes each selected value as a repeated key', () => {
		const params = new URLSearchParams();
		writeFiltersToSearchParams(params, {
			...DEFAULT_FILTERS,
			series: ['0301', '0610'],
			payPlans: ['GS', 'WG'],
			hiringPaths: ['public']
		});
		expect(params.getAll('series')).toEqual(['0301', '0610']);
		expect(params.getAll('payPlan')).toEqual(['GS', 'WG']);
		expect(params.getAll('hiringPath')).toEqual(['public']);
	});
});

describe('filterJobDetails', () => {
	it('returns the input untouched when no filters are active', () => {
		const jobs = [job({ id: 1 }), job({ id: 2 })];
		expect(filterJobDetails(jobs, filters())).toBe(jobs);
	});

	it('filters the list down to matching jobs', () => {
		const jobs = [
			job({ id: 1, agency_code: 'HSCB' }),
			job({ id: 2, agency_code: 'VATA' }),
			job({ id: 3, agency_code: 'HSCB' })
		];
		const result = filterJobDetails(jobs, filters({ agencies: ['HSCB'] }));
		expect(result.map((j) => j.id)).toEqual([1, 3]);
	});
});

describe('radius filtering (D.5.30)', () => {
	// [lng, lat]
	const NYC: [number, number] = [-74.006, 40.7128];
	const NEAR_NYC: [number, number] = [-74.17, 40.73]; // ~9 mi from NYC
	const LA: [number, number] = [-118.2437, 34.0522];

	function coords(map: Record<string, Array<[number, number]>>): Map<string, Array<[number, number]>> {
		return new Map(Object.entries(map));
	}
	function radius(center: [number, number], miles = 50, includeRemote = true) {
		return { center, miles, label: 'Test', includeRemote };
	}

	it('keeps a posting whose duty station is in range, drops one that is not', () => {
		const coordsById = coords({ '1': [NEAR_NYC], '2': [LA] });
		const f = filters({ radii: [radius(NYC)] });
		expect(matchesJobDetail(job({ id: 1, remote_status: 'onsite' }), f, coordsById)).toBe(true);
		expect(matchesJobDetail(job({ id: 2, remote_status: 'onsite' }), f, coordsById)).toBe(false);
	});

	it('includes anywhere-remote postings by default, excludes them when the chip opts out', () => {
		const coordsById = coords({});
		const remoteJob = job({ id: 9, remote_status: 'remote' });
		expect(matchesJobDetail(remoteJob, filters({ radii: [radius(NYC, 50, true)] }), coordsById)).toBe(true);
		expect(matchesJobDetail(remoteJob, filters({ radii: [radius(NYC, 50, false)] }), coordsById)).toBe(false);
	});

	it('ORs radius with geography chips (invariant #17)', () => {
		const coordsById = coords({ '1': [LA] });
		// Job is in IL by state but its only coord is in LA. A radius near NYC
		// plus a state:IL chip should still match via the geography side.
		const inIllinois = job({ id: 1, remote_status: 'onsite', locations: [{ state: 'IL' }] });
		const f = filters({ radii: [radius(NYC)], geographies: ['state:IL'] });
		expect(matchesJobDetail(inIllinois, f, coordsById)).toBe(true);
		// With only the radius chip (no geo), the LA coord is out of range → drop.
		expect(matchesJobDetail(inIllinois, filters({ radii: [radius(NYC)] }), coordsById)).toBe(false);
	});

	it('multi-location posting matches if any duty station is in range', () => {
		const coordsById = coords({ '1': [LA, NEAR_NYC] });
		expect(matchesJobDetail(job({ id: 1, remote_status: 'onsite' }), filters({ radii: [radius(NYC)] }), coordsById)).toBe(true);
	});

	it('round-trips radius chips through URL params (lng,lat,miles[,xr])', () => {
		const f = filters({ radii: [radius(NYC, 50, true), radius(LA, 25, false)] });
		const params = new URLSearchParams();
		writeFiltersToSearchParams(params, f);
		expect(params.getAll('radius')).toEqual(['-74.006,40.7128,50', '-118.2437,34.0522,25,xr']);
		const restored = filtersFromSearchParams(params);
		expect(restored.radii).toHaveLength(2);
		expect(restored.radii[0].center).toEqual(NYC);
		expect(restored.radii[0].includeRemote).toBe(true);
		expect(restored.radii[1].miles).toBe(25);
		expect(restored.radii[1].includeRemote).toBe(false);
	});

	it('counts radii in activeFilterCount', () => {
		const f = filters({ radii: [radius(NYC)] });
		const params = new URLSearchParams();
		writeFiltersToSearchParams(params, f);
		// Sanity: a radius-only filter set is "active".
		expect(filterJobDetails([job({ id: 1 })], f, coords({ '1': [LA] }))).toEqual([]);
	});
});
