import { describe, it, expect } from 'vitest';
import {
	localityMetaFromGeoJson,
	computeLocalityRollup,
	sortRollup,
	rollupTotals,
	formatPayPlanMix,
	type LocalityRollupRow
} from './localities';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import type { JobDetails, FeatureCollection } from './data';

function job(overrides: Partial<JobDetails> = {}): JobDetails {
	return {
		id: 1,
		title: 'Analyst',
		agency_code: 'HSCB',
		series: '0343',
		pay_plan: 'GS',
		grade_low: '12',
		grade_high: '13',
		salary_min: 90000,
		salary_max: 120000,
		remote_status: 'onsite',
		locality_code: 'DCB',
		...overrides
	};
}

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return { ...DEFAULT_FILTERS, ...overrides };
}

const META: FeatureCollection = {
	type: 'FeatureCollection',
	features: [
		{
			type: 'Feature',
			geometry: { type: 'Point', coordinates: [0, 0] },
			properties: { code: 'DCB', name: 'Washington-Baltimore', rpp_overall: 112.3, gs13_step1_locality: 130000, adjustment_pct: 33.26 }
		},
		{
			type: 'Feature',
			geometry: { type: 'Point', coordinates: [0, 0] },
			properties: { code: 'SEA', name: 'Seattle-Tacoma, WA', adjustment_pct: 29.0 } // no rpp_overall → state fallback via name token
		}
	]
} as unknown as FeatureCollection;

// locality_code lives on jobs.geojson FEATURE properties (not jobs_detail), so
// the rollup aggregates over a FeatureCollection. Each posting may appear as
// several features (one per duty station); the rollup dedupes by id per locality.
function feat(props: Record<string, unknown>): unknown {
	return { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: props };
}
const jobs: FeatureCollection = {
	type: 'FeatureCollection',
	features: [
		feat({ id: 1, locality_code: 'DCB', pay_plan: 'GS', salary_min: 90000, salary_max: 120000, agency_code: 'HSCB' }),
		feat({ id: 2, locality_code: 'DCB', pay_plan: 'GS', salary_min: 70000, salary_max: 100000, agency_code: 'HSCB' }),
		feat({ id: 3, locality_code: 'DCB', pay_plan: 'WG', salary_min: 60000, salary_max: 80000, agency_code: 'HSCB' }),
		feat({ id: 4, locality_code: 'SEA', pay_plan: 'GS', salary_min: 95000, salary_max: 140000, agency_code: 'HSCB' }),
		// A posting with two duty stations in the SAME locality must count once.
		feat({ id: 2, locality_code: 'DCB', pay_plan: 'GS', salary_min: 70000, salary_max: 100000, agency_code: 'HSCB' }),
		feat({ id: 5, locality_code: '', pay_plan: 'GS', agency_code: 'HSCB' }) // no locality → excluded
	]
} as unknown as FeatureCollection;
// jobs_detail backs the keyword filter / pay backstop; carries no locality_code.
const details: Record<string, JobDetails> = {};

describe('localityMetaFromGeoJson', () => {
	it('parses code/name/rpp/gs13 and flags missing rpp', () => {
		const meta = localityMetaFromGeoJson(META);
		expect(meta.get('DCB')?.name).toBe('Washington-Baltimore');
		expect(meta.get('DCB')?.rppOverall).toBe(112.3);
		expect(meta.get('DCB')?.gs13Step1).toBe(130000);
		expect(meta.get('SEA')?.rppOverall).toBeNull();
	});
});

describe('computeLocalityRollup', () => {
	const meta = localityMetaFromGeoJson(META);

	it('groups by locality, counts postings, and excludes blank-locality jobs', () => {
		const rows = computeLocalityRollup(jobs, details, meta, filters());
		const byCode = Object.fromEntries(rows.map((r) => [r.code, r]));
		expect(byCode.DCB.postings).toBe(3);
		expect(byCode.SEA.postings).toBe(1);
		expect(rows.find((r) => r.code === '')).toBeUndefined(); // job 5 dropped
	});

	it('derives pay range across postings from PositionRemuneration (any plan, not GS-anchored)', () => {
		const rows = computeLocalityRollup(jobs, details, meta, filters());
		const dcb = rows.find((r) => r.code === 'DCB')!;
		expect(dcb.salaryMin).toBe(60000); // includes the WG posting's floor
		expect(dcb.salaryMax).toBe(120000);
	});

	it('builds a pay-plan mix and reports GS coverage honestly', () => {
		const rows = computeLocalityRollup(jobs, details, meta, filters());
		const dcb = rows.find((r) => r.code === 'DCB')!;
		expect(dcb.payPlanMix.find((p) => p.plan === 'GS')?.count).toBe(2);
		expect(dcb.payPlanMix.find((p) => p.plan === 'WG')?.count).toBe(1);
		expect(dcb.gsCount).toBe(2);
		expect(dcb.gsCoveragePct).toBe(67); // 2/3
		expect(formatPayPlanMix(dcb.payPlanMix)).toContain('GS 67%');
	});

	it('honors non-geographic filters and ignores geography/radius chips', () => {
		// A locality geography chip must NOT restrict the rollup (geography is the
		// variable here) — but a pay-plan filter must.
		const withGeo = computeLocalityRollup(jobs, details, meta, filters({ geographies: ['locality:DCB'] }));
		expect(withGeo.find((r) => r.code === 'SEA')).toBeDefined(); // geo chip ignored
		const wgOnly = computeLocalityRollup(jobs, details, meta, filters({ payPlans: ['WG'] }));
		const dcb = wgOnly.find((r) => r.code === 'DCB')!;
		expect(dcb.postings).toBe(1); // only the WG posting
		expect(wgOnly.find((r) => r.code === 'SEA')).toBeUndefined(); // SEA has no WG
	});

	it('uses locality RPP when present and falls back to state RPP flagged approximate', () => {
		const stateRpp = { WA: { rpp_overall: 108.0, year: 2023, source: 'bea:rpp' } };
		const rows = computeLocalityRollup(jobs, details, meta, filters(), { stateRpp });
		const dcb = rows.find((r) => r.code === 'DCB')!;
		expect(dcb.rppOverall).toBe(112.3);
		expect(dcb.rppApproximate).toBe(false);
		const sea = rows.find((r) => r.code === 'SEA')!;
		expect(sea.rppOverall).toBe(108.0); // fell back to WA state RPP
		expect(sea.rppApproximate).toBe(true);
		expect(sea.rppState).toBe('WA');
	});
});

describe('sortRollup', () => {
	const rows: LocalityRollupRow[] = [
		{ code: 'A', name: 'Alpha', postings: 5, salaryMin: 50, salaryMax: 100, payPlanMix: [], gsCount: 5, gsCoveragePct: 100, rppOverall: 110, rppApproximate: false, rppState: null },
		{ code: 'B', name: 'Bravo', postings: 20, salaryMin: 60, salaryMax: 200, payPlanMix: [], gsCount: 10, gsCoveragePct: 50, rppOverall: null, rppApproximate: false, rppState: null },
		{ code: 'C', name: 'Charlie', postings: 12, salaryMin: 40, salaryMax: 150, payPlanMix: [], gsCount: 12, gsCoveragePct: 100, rppOverall: 95, rppApproximate: true, rppState: 'TX' }
	];

	it('sorts postings descending by default order', () => {
		expect(sortRollup(rows, 'postings', 'desc').map((r) => r.code)).toEqual(['B', 'C', 'A']);
	});
	it('sorts name ascending', () => {
		expect(sortRollup(rows, 'name', 'asc').map((r) => r.code)).toEqual(['A', 'B', 'C']);
	});
	it('ranks pay by top of range', () => {
		expect(sortRollup(rows, 'pay', 'desc').map((r) => r.code)).toEqual(['B', 'C', 'A']);
	});
	it('sorts nulls last regardless of direction', () => {
		expect(sortRollup(rows, 'rpp', 'asc').map((r) => r.code)).toEqual(['C', 'A', 'B']); // B(null) last
		expect(sortRollup(rows, 'rpp', 'desc').map((r) => r.code)).toEqual(['A', 'C', 'B']); // B(null) still last
	});
});

describe('rollupTotals', () => {
	it('sums postings and counts localities', () => {
		const rows = computeLocalityRollup(jobs, details, localityMetaFromGeoJson(META), filters());
		const t = rollupTotals(rows);
		expect(t.postings).toBe(4); // 3 DCB + 1 SEA (blank-locality job excluded)
		expect(t.localities).toBe(2);
	});
});
