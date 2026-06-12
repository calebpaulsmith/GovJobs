import { describe, expect, it } from 'vitest';
import { buildAreaTrendQuery, fillMonths, TREND_WINDOW } from './areaTrend';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import type { ResolvedArea } from './areaCard';

const NATIONWIDE: ResolvedArea = { scope: 'nationwide', code: null, label: 'Nationwide', feature: null };

function stateArea(code: string, label: string): ResolvedArea {
	return { scope: 'state', code, label, feature: null };
}

function localityArea(code: string, label: string): ResolvedArea {
	return {
		scope: 'locality',
		code,
		label,
		feature: { type: 'Feature', geometry: null, properties: { code, name: label } } as never
	};
}

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return { ...DEFAULT_FILTERS, ...overrides };
}

describe('buildAreaTrendQuery', () => {
	it('nationwide + empty filters sends nothing and says "all federal postings"', () => {
		const built = buildAreaTrendQuery(NATIONWIDE, filters());
		expect(built.query).toEqual({
			agencyCode: undefined,
			series: undefined,
			grade: undefined,
			state: undefined
		});
		expect(built.description).toBe('all federal postings');
		expect(built.notes).toEqual([]);
	});

	it('state scope sends the state code', () => {
		const built = buildAreaTrendQuery(stateArea('CO', 'Colorado'), filters());
		expect(built.query.state).toBe('CO');
		expect(built.description).toContain('state CO');
		expect(built.notes).toEqual([]);
	});

	it('locality scope falls back to the primary state with an explicit note', () => {
		// DEN resolves via the locality name's trailing state list.
		const built = buildAreaTrendQuery(
			localityArea('DEN', 'DENVER-AURORA, CO'),
			filters()
		);
		expect(built.query.state).toBe('CO');
		expect(built.notes.some((n) => n.includes('primary state'))).toBe(true);
		expect(built.notes.some((n) => n.includes('approximate'))).toBe(true);
	});

	it('unmappable locality sends no state and says the trend is nationwide', () => {
		const built = buildAreaTrendQuery(localityArea('ZZZ', 'Mystery Area'), filters());
		expect(built.query.state).toBeUndefined();
		expect(built.notes.some((n) => n.includes('nationwide'))).toBe(true);
	});

	it('first agency/series chips anchor the query; extra chips become a note', () => {
		const built = buildAreaTrendQuery(
			NATIONWIDE,
			filters({ agencies: ['HSCB', 'NTSB', 'AF1M'], series: ['0301', '2210'], gradeMin: '12' })
		);
		expect(built.query.agencyCode).toBe('HSCB');
		expect(built.query.series).toBe('0301');
		expect(built.query.grade).toBe('12');
		expect(built.description).toBe('agency HSCB · series 0301 · grade 12');
		expect(built.notes.some((n) => n.includes('(HSCB)') && n.includes('2 more chips'))).toBe(true);
		expect(built.notes.some((n) => n.includes('(0301)') && n.includes('1 more chip'))).toBe(true);
	});

	it('key is stable for equivalent inputs and differs when the slice changes', () => {
		const a = buildAreaTrendQuery(stateArea('CO', 'Colorado'), filters({ agencies: ['HSCB'] }));
		const b = buildAreaTrendQuery(stateArea('CO', 'Colorado'), filters({ agencies: ['HSCB'] }));
		const c = buildAreaTrendQuery(stateArea('IL', 'Illinois'), filters({ agencies: ['HSCB'] }));
		expect(a.key).toBe(b.key);
		expect(a.key).not.toBe(c.key);
		expect(a.key).toContain(`window=${TREND_WINDOW}`);
	});
});

describe('fillMonths', () => {
	it('zero-fills every month between start and end inclusive', () => {
		const filled = fillMonths(
			[
				{ month: '2025-08', count: 3 },
				{ month: '2025-11', count: 7 }
			],
			'2025-06-12',
			'2025-12-01'
		);
		expect(filled.map((m) => m.month)).toEqual([
			'2025-06',
			'2025-07',
			'2025-08',
			'2025-09',
			'2025-10',
			'2025-11',
			'2025-12'
		]);
		expect(filled.find((m) => m.month === '2025-08')?.count).toBe(3);
		expect(filled.find((m) => m.month === '2025-11')?.count).toBe(7);
		expect(filled.filter((m) => m.count === 0)).toHaveLength(5);
	});

	it('crosses year boundaries', () => {
		const filled = fillMonths([], '2025-11-30', '2026-02-01');
		expect(filled.map((m) => m.month)).toEqual(['2025-11', '2025-12', '2026-01', '2026-02']);
	});

	it('a 1yr window spans 13 calendar months', () => {
		const filled = fillMonths([], '2025-06-12', '2026-06-12');
		expect(filled).toHaveLength(13);
		expect(filled[0].month).toBe('2025-06');
		expect(filled[12].month).toBe('2026-06');
	});

	it('returns the buckets unchanged when dates are malformed or inverted', () => {
		const monthly = [{ month: '2025-08', count: 3 }];
		expect(fillMonths(monthly, 'garbage', '2025-12-01')).toBe(monthly);
		expect(fillMonths(monthly, '2026-01-01', '2025-01-01')).toBe(monthly);
	});
});
