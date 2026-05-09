// D.5.24 — Posting Intelligence helper tests.
//
// These cover the pure helpers shared by the Cloudflare Pages Function and
// the JobCard tab. The Function itself is exercised in integration during
// Cloudflare deploys; the helpers here are what determine whether an upstream
// query is correct, a record is trimmed correctly, and the bucketed timeline
// matches what the chart will render.

import { describe, expect, it } from 'vitest';
import {
	bucketByMonth,
	buildHistoricJoaParams,
	cacheKey,
	DEFAULT_WINDOW,
	isWindowKey,
	normalizeWindow,
	postFilter,
	trimRecord,
	WINDOW_KEYS,
	windowToDateRange,
	type TrimmedRecord
} from './jobHistory';

const FIXED_AS_OF = new Date('2026-05-09T00:00:00Z');

describe('windowToDateRange', () => {
	it('produces a 30-day range for 1mo', () => {
		const range = windowToDateRange('1mo', FIXED_AS_OF);
		expect(range.end).toBe('2026-05-09');
		expect(range.start).toBe('2026-04-09');
	});

	it('produces a 365-day range for 1yr', () => {
		const range = windowToDateRange('1yr', FIXED_AS_OF);
		expect(range.end).toBe('2026-05-09');
		expect(range.start).toBe('2025-05-09');
	});

	it('produces a 10-year range for 10yr', () => {
		const range = windowToDateRange('10yr', FIXED_AS_OF);
		expect(range.end).toBe('2026-05-09');
		// 10 * 365 = 3650 days back from 2026-05-09 lands us a few days short
		// of the calendar decade because of leap years. We assert the year is
		// 2016 rather than chasing the leap-day arithmetic.
		expect(range.start.startsWith('2016-')).toBe(true);
	});
});

describe('buildHistoricJoaParams', () => {
	it('always sets the date range', () => {
		const params = buildHistoricJoaParams({}, '1mo', FIXED_AS_OF);
		expect(params.get('StartPositionOpenDate')).toBe('2026-04-09');
		expect(params.get('EndPositionOpenDate')).toBe('2026-05-09');
	});

	it('maps agencyCode to HiringAgencyCodes and uppercases it', () => {
		const params = buildHistoricJoaParams(
			{ agencyCode: 'hscb' },
			'3mo',
			FIXED_AS_OF
		);
		expect(params.get('HiringAgencyCodes')).toBe('HSCB');
	});

	it('passes series through as PositionSeries', () => {
		const params = buildHistoricJoaParams(
			{ series: '0301' },
			'1yr',
			FIXED_AS_OF
		);
		expect(params.get('PositionSeries')).toBe('0301');
	});

	it('does not send grade or state — those are post-filtered', () => {
		const params = buildHistoricJoaParams(
			{ grade: '13', state: 'IL', agencyCode: 'HSCB' },
			'1yr',
			FIXED_AS_OF
		);
		expect(params.has('grade')).toBe(false);
		expect(params.has('state')).toBe(false);
		expect(params.has('PositionSeries')).toBe(false);
		expect(params.get('HiringAgencyCodes')).toBe('HSCB');
	});

	it('passes a control number as USAJOBSControlNumbers', () => {
		const params = buildHistoricJoaParams(
			{ controlNumber: '847434900' },
			'1yr',
			FIXED_AS_OF
		);
		expect(params.get('USAJOBSControlNumbers')).toBe('847434900');
	});
});

describe('trimRecord', () => {
	const SAMPLE_RAW = {
		agencyLevel: 2,
		announcementNumber: 'FEE-0602-ICU-25-09-09',
		appointmentType: 'Temporary',
		hiringAgencyCode: 'VATA',
		hiringAgencyName: 'Veterans Health Administration',
		hiringDepartmentCode: 'VA',
		hiringDepartmentName: 'Department of Veterans Affairs',
		hiringpaths: [{ hiringPath: 'The public' }],
		jobcategories: [{ series: '0602' }],
		maximumGrade: '00',
		maximumSalary: 3200.0,
		minimumGrade: '00',
		minimumSalary: 3200.0,
		payScale: 'FB',
		positionCloseDate: '2026-12-31',
		positionOpenDate: '2026-01-01',
		positionTitle: 'ICU fee basis Physician',
		positionlocations: [
			{
				positionLocationCity: 'Albuquerque',
				positionLocationCountry: 'United States',
				positionLocationState: 'New Mexico'
			}
		],
		usajobsControlNumber: 847434900,
		// Long-text fields the trimmer should drop:
		summary: 'A very long summary that should never end up in the trimmed payload…',
		requirementsQualifications: 'Even longer qualifications text that we never want to ship.'
	};

	it('extracts the public-map fields and ignores long text', () => {
		const trimmed = trimRecord(SAMPLE_RAW);
		expect(trimmed).toMatchObject({
			control_number: 847434900,
			announcement_number: 'FEE-0602-ICU-25-09-09',
			title: 'ICU fee basis Physician',
			agency_code: 'VATA',
			agency_name: 'Veterans Health Administration',
			department_code: 'VA',
			series: '0602',
			pay_plan: 'FB',
			grade_low: '00',
			grade_high: '00',
			salary_min: 3200,
			salary_max: 3200,
			open_date: '2026-01-01',
			close_date: '2026-12-31',
			city: 'Albuquerque',
			state: 'New Mexico',
			hiring_path: 'The public'
		});
		// Confirm long-text fields did not survive.
		expect(Object.keys(trimmed)).not.toContain('summary');
		expect(Object.keys(trimmed)).not.toContain('requirementsQualifications');
	});

	it('handles missing nested arrays gracefully', () => {
		const trimmed = trimRecord({ positionTitle: 'Only the title' });
		expect(trimmed.title).toBe('Only the title');
		expect(trimmed.city).toBeNull();
		expect(trimmed.state).toBeNull();
		expect(trimmed.series).toBeNull();
		expect(trimmed.hiring_path).toBeNull();
		expect(trimmed.salary_min).toBeNull();
	});

	it('coerces salary strings to numbers and unparseable values to null', () => {
		const trimmed = trimRecord({
			minimumSalary: '50000',
			maximumSalary: 'see notes'
		});
		expect(trimmed.salary_min).toBe(50000);
		expect(trimmed.salary_max).toBeNull();
	});
});

describe('postFilter', () => {
	const RECORDS: TrimmedRecord[] = [
		baseRecord({ grade_low: '13', grade_high: '13', state: 'Illinois' }),
		baseRecord({ grade_low: '13', grade_high: '14', state: 'New Mexico' }),
		baseRecord({ grade_low: '11', grade_high: '12', state: 'IL' }),
		baseRecord({ grade_low: '15', grade_high: '15', state: 'New York' })
	];

	it('returns the input unchanged when grade and state are blank', () => {
		expect(postFilter(RECORDS, {})).toBe(RECORDS);
	});

	it('matches grade against either low or high', () => {
		const filtered = postFilter(RECORDS, { grade: '14' });
		expect(filtered).toHaveLength(1);
		expect(filtered[0].state).toBe('New Mexico');
	});

	it('matches state by both postal code and full name', () => {
		const filtered = postFilter(RECORDS, { state: 'IL' });
		expect(filtered).toHaveLength(2);
		expect(filtered.map((r) => r.state).sort()).toEqual(['IL', 'Illinois']);
	});

	it('combines grade and state with AND', () => {
		const filtered = postFilter(RECORDS, { grade: '13', state: 'IL' });
		expect(filtered).toHaveLength(1);
		expect(filtered[0].grade_low).toBe('13');
		expect(filtered[0].state).toBe('Illinois');
	});
});

describe('bucketByMonth', () => {
	it('groups records by YYYY-MM of open date and sorts ascending', () => {
		const records = [
			baseRecord({ open_date: '2026-01-15' }),
			baseRecord({ open_date: '2026-01-31' }),
			baseRecord({ open_date: '2025-11-04' }),
			baseRecord({ open_date: '2026-03-01' }),
			baseRecord({ open_date: '' }) // skipped
		];
		expect(bucketByMonth(records)).toEqual([
			{ month: '2025-11', count: 1 },
			{ month: '2026-01', count: 2 },
			{ month: '2026-03', count: 1 }
		]);
	});

	it('returns an empty array when no records have a usable open date', () => {
		expect(bucketByMonth([baseRecord({ open_date: null })])).toEqual([]);
	});
});

describe('normalizeWindow / isWindowKey', () => {
	it('accepts every documented window key', () => {
		for (const key of WINDOW_KEYS) {
			expect(isWindowKey(key)).toBe(true);
			expect(normalizeWindow(key)).toBe(key);
		}
	});

	it('falls back to the default for unknown values', () => {
		expect(normalizeWindow('forever')).toBe(DEFAULT_WINDOW);
		expect(normalizeWindow(null)).toBe(DEFAULT_WINDOW);
		expect(normalizeWindow(undefined)).toBe(DEFAULT_WINDOW);
	});
});

describe('cacheKey', () => {
	it('includes the window and uppercases agency / state', () => {
		const key = cacheKey({ agencyCode: 'hscb', state: 'il', series: '0301' }, '1yr');
		expect(key).toBe('window=1yr&agency=HSCB&series=0301&state=IL');
	});

	it('omits empty fields', () => {
		expect(cacheKey({}, '6mo')).toBe('window=6mo');
	});
});

function baseRecord(overrides: Partial<TrimmedRecord>): TrimmedRecord {
	return {
		control_number: null,
		announcement_number: null,
		title: null,
		agency_code: null,
		agency_name: null,
		department_code: null,
		series: null,
		pay_plan: null,
		grade_low: null,
		grade_high: null,
		salary_min: null,
		salary_max: null,
		open_date: null,
		close_date: null,
		city: null,
		state: null,
		hiring_path: null,
		...overrides
	};
}
