import { describe, it, expect } from 'vitest';
import {
	payPlanFacet,
	hiringPathFacet,
	seriesFacet,
	payPlanLabel,
	hiringPathLabel
} from './filterFacets';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import type { JobDetails } from './data';

function job(overrides: Partial<JobDetails> = {}): JobDetails {
	return {
		id: 1,
		title: 'Specialist',
		agency_code: 'HSCB',
		series: '0089',
		pay_plan: 'GS',
		grade_low: '12',
		grade_high: '13',
		remote_status: 'onsite',
		hiring_paths: '["public"]',
		locations: [{ city: 'Chicago', state: 'IL' }],
		...overrides
	};
}

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return { ...DEFAULT_FILTERS, agencies: [], geographies: [], ...overrides };
}

const corpus: JobDetails[] = [
	job({ id: 1, agency_code: 'HSCB', pay_plan: 'GS', series: '0089', hiring_paths: '["public"]' }),
	job({ id: 2, agency_code: 'HSCB', pay_plan: 'IT', series: '2210', hiring_paths: '["public","vet"]' }),
	job({ id: 3, agency_code: 'VATA', pay_plan: 'VN', series: '0610', hiring_paths: '["fed-internal-search"]' }),
	job({ id: 4, agency_code: 'VATA', pay_plan: 'GS', series: '0301', hiring_paths: '["public"]' })
];

describe('labels', () => {
	it('maps known codes and falls back to the raw code', () => {
		expect(payPlanLabel('gs')).toBe('General Schedule');
		expect(payPlanLabel('ZZ')).toBe('ZZ');
		expect(hiringPathLabel('public')).toBe('Open to the public');
		expect(hiringPathLabel('fed-internal-search')).toBe('Internal to an agency');
		// Unmapped code is humanized, not hidden.
		expect(hiringPathLabel('brand-new')).toBe('Brand new');
	});
});

describe('facet narrowing', () => {
	it('counts every value when no other filter is active', () => {
		const plans = payPlanFacet(corpus, filters());
		expect(plans.map((o) => o.value)).toEqual(['GS', 'IT', 'VN']); // GS=2 first, then IT/VN alpha
		expect(plans.find((o) => o.value === 'GS')?.count).toBe(2);
	});

	it('narrows pay-plan options to the current agency filter', () => {
		// With VATA selected, only the pay plans VATA posts (GS, VN) appear.
		const plans = payPlanFacet(corpus, filters({ agencies: ['VATA'] }));
		expect(plans.map((o) => o.value).sort()).toEqual(['GS', 'VN']);
		expect(plans.find((o) => o.value === 'IT')).toBeUndefined();
	});

	it("ignores the pay-plan facet's own selection so a second plan can be added", () => {
		// Selecting GS must NOT remove IT/VN from the pay-plan dropdown.
		const plans = payPlanFacet(corpus, filters({ payPlans: ['GS'] }));
		expect(plans.map((o) => o.value)).toContain('IT');
		expect(plans.map((o) => o.value)).toContain('VN');
	});

	it('tallies each hiring path a job advertises', () => {
		const paths = hiringPathFacet(corpus, filters());
		const counts = Object.fromEntries(paths.map((o) => [o.value, o.count]));
		expect(counts.public).toBe(3);
		expect(counts.vet).toBe(1);
		expect(counts['fed-internal-search']).toBe(1);
	});

	it('labels series from the supplied code->title map', () => {
		const series = seriesFacet(corpus, filters({ agencies: ['HSCB'] }), {
			'2210': 'Information Technology Management'
		});
		expect(series.map((o) => o.value).sort()).toEqual(['0089', '2210']);
		const it = series.find((o) => o.value === '2210');
		expect(it?.label).toBe('2210 — Information Technology Management');
	});
});
