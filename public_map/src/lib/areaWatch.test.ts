import { describe, expect, it } from 'vitest';
import { computeWatchNote, MIN_CLOSE_WINDOW_SAMPLES } from './areaWatch';
import type { HistoryPayload, MonthlyBucket, TrimmedRecord } from './jobHistory';

// Default range: 2023-06 .. 2026-06 (37 filled months). The trailing partial
// month (2026-06) is dropped, so "complete" = 2023-06 .. 2026-05 (36 months),
// recent-12 = 2025-06 .. 2026-05, prior-12 = 2024-06 .. 2025-05.
function payload(over: Partial<HistoryPayload> = {}): HistoryPayload {
	return {
		status: 'ok',
		window: '3yr',
		as_of: '2026-06-12T00:00:00.000Z',
		start_date: '2023-06-12',
		end_date: '2026-06-12',
		total: 0,
		truncated: false,
		page_cap: 5,
		monthly: [],
		records: [],
		source: 'usajobs:historicjoa',
		...over
	};
}

// Generate one bucket per month from `fromYm` for `n` months, all with `count`.
function run(fromYm: string, n: number, count: number): MonthlyBucket[] {
	let [y, m] = fromYm.split('-').map(Number);
	const out: MonthlyBucket[] = [];
	for (let i = 0; i < n; i++) {
		out.push({ month: `${y}-${String(m).padStart(2, '0')}`, count });
		m += 1;
		if (m > 12) {
			m = 1;
			y += 1;
		}
	}
	return out;
}

function rec(open: string | null, close: string | null): TrimmedRecord {
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
		open_date: open,
		close_date: close,
		city: null,
		state: null,
		hiring_path: null
	};
}

function windowRecs(days: number, n: number): TrimmedRecord[] {
	const close = `2025-01-${String(1 + days).padStart(2, '0')}`;
	return Array.from({ length: n }, () => rec('2025-01-01', close));
}

describe('computeWatchNote', () => {
	it('returns null for an unavailable payload', () => {
		expect(computeWatchNote(payload({ status: 'unavailable' }))).toBeNull();
	});

	it('emits an upward year-over-year line', () => {
		const note = computeWatchNote(
			payload({
				monthly: [...run('2024-06', 12, 2), ...run('2025-06', 12, 3)],
				total: 60
			})
		);
		expect(note?.lines.some((l) => l.includes('36 openings — ↑ 50% vs the prior 12 months (24)'))).toBe(true);
	});

	it('emits a downward year-over-year line', () => {
		const note = computeWatchNote(
			payload({
				monthly: [...run('2024-06', 12, 3), ...run('2025-06', 12, 2)],
				total: 60
			})
		);
		expect(note?.lines.some((l) => l.includes('↓ 33% vs the prior 12 months (36)'))).toBe(true);
	});

	it('says "on pace" when the years match', () => {
		const note = computeWatchNote(
			payload({ monthly: [...run('2024-06', 12, 3), ...run('2025-06', 12, 3)], total: 72 })
		);
		expect(note?.lines.some((l) => l.includes('on pace with the prior 12 months'))).toBe(true);
	});

	it('withholds year-over-year when the prior year is too thin', () => {
		const note = computeWatchNote(
			payload({
				monthly: [...run('2024-06', 5, 1), ...run('2025-06', 12, 2)],
				total: 29
			})
		);
		expect(note?.lines.some((l) => l.includes('vs the prior 12 months'))).toBe(false);
		expect(note?.withheld.some((w) => w.includes('only 5 openings in the prior 12 months'))).toBe(
			true
		);
	});

	it('withholds year-over-year and seasonality on a truncated payload, and the basis says so', () => {
		const note = computeWatchNote(
			payload({
				monthly: [...run('2024-06', 12, 50), ...run('2025-06', 12, 60)],
				total: 1320,
				truncated: true
			})
		);
		expect(note?.lines.some((l) => l.includes('vs the prior'))).toBe(false);
		expect(note?.lines.some((l) => l.includes('seasonal'))).toBe(false);
		expect(note?.withheld.some((w) => w.includes('upstream record cap'))).toBe(true);
		expect(note?.basis).toContain('capped at the upstream page limit');
	});

	it('withholds year-over-year when the window has fewer than 24 complete months', () => {
		const note = computeWatchNote(
			payload({
				start_date: '2025-06-12',
				end_date: '2026-06-12',
				monthly: run('2025-06', 12, 3),
				total: 36
			})
		);
		expect(note?.withheld.some((w) => w.includes('fewer than 24 complete months'))).toBe(true);
		expect(note?.withheld.some((w) => w.includes('Seasonality withheld'))).toBe(true);
	});

	it('detects a single seasonal peak month', () => {
		// March = 12 each year, every other month = 1.
		const monthly: MonthlyBucket[] = [];
		for (const bucket of run('2023-06', 36, 1)) {
			monthly.push(bucket.month.endsWith('-03') ? { ...bucket, count: 12 } : bucket);
		}
		const note = computeWatchNote(payload({ monthly, total: 102 }));
		expect(note?.lines.some((l) => l.includes('historically peaked in March.'))).toBe(true);
	});

	it('names two months when the runner-up is within 90% of the peak', () => {
		const monthly: MonthlyBucket[] = [];
		for (const bucket of run('2023-06', 36, 1)) {
			if (bucket.month.endsWith('-03')) monthly.push({ ...bucket, count: 12 });
			else if (bucket.month.endsWith('-04')) monthly.push({ ...bucket, count: 11 });
			else monthly.push(bucket);
		}
		const note = computeWatchNote(payload({ monthly, total: 132 }));
		expect(note?.lines.some((l) => l.includes('peaked in March and April.'))).toBe(true);
	});

	it('reports no strong seasonal pattern for a flat year', () => {
		const note = computeWatchNote(
			payload({ monthly: run('2023-06', 36, 2), total: 72 })
		);
		expect(note?.lines.some((l) => l.includes('No strong seasonal pattern'))).toBe(true);
	});

	it('withholds seasonality when the sample is too thin', () => {
		const note = computeWatchNote(
			payload({ monthly: run('2025-01', 10, 2), total: 20 })
		);
		expect(note?.withheld.some((w) => w.includes('Seasonality withheld'))).toBe(true);
	});

	it('emits the median posting window with the apply-early nudge when short', () => {
		const note = computeWatchNote(payload({ records: windowRecs(10, 9), total: 9 }));
		expect(
			note?.lines.some(
				(l) => l.includes('median of 10 days') && l.includes('applying early')
			)
		).toBe(true);
	});

	it('omits the apply-early nudge for long windows', () => {
		const note = computeWatchNote(payload({ records: windowRecs(30, 9), total: 9 }));
		const line = note?.lines.find((l) => l.includes('median of 30 days'));
		expect(line).toBeDefined();
		expect(line).not.toContain('applying early');
	});

	it('withholds the posting window below the sample floor', () => {
		const note = computeWatchNote(
			payload({ records: windowRecs(10, MIN_CLOSE_WINDOW_SAMPLES - 1), total: 7 })
		);
		expect(note?.withheld.some((w) => w.includes('Typical posting window withheld'))).toBe(true);
	});

	it('skips records with missing or inverted dates when computing the window', () => {
		const records = [
			...windowRecs(10, 8),
			rec(null, '2025-02-01'),
			rec('2025-02-10', '2025-02-01')
		];
		const note = computeWatchNote(payload({ records, total: 10 }));
		expect(note?.lines.some((l) => l.includes('median of 10 days'))).toBe(true);
	});
});
