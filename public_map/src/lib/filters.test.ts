import { describe, it, expect } from 'vitest';
import { DEFAULT_FILTERS, matchesJobDetail, filterJobDetails, type JobFilters } from './filters';
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

	it('matches pay plan exactly', () => {
		expect(matchesJobDetail(job(), filters({ payPlan: 'GS' }))).toBe(true);
		expect(matchesJobDetail(job({ pay_plan: 'WG' }), filters({ payPlan: 'GS' }))).toBe(false);
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

	it('enforces the salary minimum', () => {
		expect(matchesJobDetail(job(), filters({ salaryMin: '90000' }))).toBe(true);
		expect(matchesJobDetail(job(), filters({ salaryMin: '120000' }))).toBe(false);
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
