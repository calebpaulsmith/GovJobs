import { describe, expect, it } from 'vitest';
import { relativeTime, summariseSavedSearch } from './savedTab';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import type { SavedSearch } from './savedSearches';

// "now" anchor for deterministic relative-time output.
const NOW = new Date('2026-05-20T12:00:00Z').getTime();
const MIN = 60_000;
const HOUR = 3_600_000;
const DAY = 86_400_000;

function search(overrides: Partial<SavedSearch> = {}): SavedSearch {
	const createdAt = overrides.createdAt ?? '2026-05-18T09:00:00Z';
	return {
		id: 'srch-1',
		name: 'Chicago FEMA mid-grade',
		createdAt,
		updatedAt: overrides.updatedAt ?? createdAt,
		filters: overrides.filters ?? filters(),
		metric: overrides.metric ?? 'postings',
		...overrides
	};
}

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return {
		...DEFAULT_FILTERS,
		agencies: [],
		geographies: [],
		...overrides
	};
}

describe('relativeTime', () => {
	it('returns "just now" for sub-minute deltas', () => {
		expect(relativeTime(NOW, NOW)).toBe('just now');
		expect(relativeTime(NOW - 30_000, NOW)).toBe('just now');
	});

	it('returns "just now" for future timestamps (clock skew)', () => {
		expect(relativeTime(NOW + 5_000, NOW)).toBe('just now');
	});

	it('renders minutes, hours, yesterday, and days for the first week', () => {
		expect(relativeTime(NOW - 5 * MIN, NOW)).toBe('5m ago');
		expect(relativeTime(NOW - 2 * HOUR, NOW)).toBe('2h ago');
		expect(relativeTime(NOW - 1 * DAY, NOW)).toBe('yesterday');
		expect(relativeTime(NOW - 3 * DAY, NOW)).toBe('3d ago');
		expect(relativeTime(NOW - 6 * DAY, NOW)).toBe('6d ago');
	});

	it('renders weeks, months, and years past one week', () => {
		expect(relativeTime(NOW - 8 * DAY, NOW)).toBe('1w ago');
		expect(relativeTime(NOW - 21 * DAY, NOW)).toBe('3w ago');
		expect(relativeTime(NOW - 40 * DAY, NOW)).toBe('1mo ago');
		expect(relativeTime(NOW - 200 * DAY, NOW)).toBe('6mo ago');
		expect(relativeTime(NOW - 400 * DAY, NOW)).toBe('1y ago');
		expect(relativeTime(NOW - 800 * DAY, NOW)).toBe('2y ago');
	});

	it('returns "unknown" for non-finite timestamps', () => {
		expect(relativeTime(Number.NaN, NOW)).toBe('unknown');
		expect(relativeTime(Number.POSITIVE_INFINITY, NOW)).toBe('unknown');
	});
});

describe('summariseSavedSearch', () => {
	it('reports "No filters" for the empty search', () => {
		const line = summariseSavedSearch(search({ filters: filters() }));
		expect(line.startsWith('No filters')).toBe(true);
		expect(line).toContain('saved 2026-05-18');
	});

	it('counts agency chips, keyword, grade, and remote as chips', () => {
		const line = summariseSavedSearch(
			search({
				filters: filters({
					agencies: ['HSCB', 'GS00'],
					keyword: 'analyst',
					gradeMin: '13',
					remote: 'remote'
				})
			})
		);
		// 2 agencies + 1 keyword + 1 gradeMin + 1 remote = 5 chips
		expect(line.startsWith('5 chips')).toBe(true);
	});

	it('renders "1 chip" (singular) for a single chip', () => {
		const line = summariseSavedSearch(
			search({ filters: filters({ keyword: 'analyst' }) })
		);
		expect(line.startsWith('1 chip ')).toBe(true);
	});

	it('appends a non-default metric in human-readable form', () => {
		const line = summariseSavedSearch(
			search({ metric: 'pay_vs_col', filters: filters() })
		);
		expect(line).toContain('pay vs col');
	});

	it('omits the metric clause when metric is the default postings', () => {
		const line = summariseSavedSearch(
			search({ metric: 'postings', filters: filters() })
		);
		expect(line).not.toContain('postings');
		// "saved 2026-05-18" must still appear so users see when they saved it.
		expect(line).toContain('saved 2026-05-18');
	});

	it('prefers updatedAt over createdAt when both are present', () => {
		const line = summariseSavedSearch(
			search({
				createdAt: '2026-05-01T09:00:00Z',
				updatedAt: '2026-05-19T15:00:00Z'
			})
		);
		expect(line).toContain('saved 2026-05-19');
		expect(line).not.toContain('saved 2026-05-01');
	});

	it('falls back to createdAt when updatedAt is missing or malformed', () => {
		const line = summariseSavedSearch(
			search({
				createdAt: '2026-04-15T09:00:00Z',
				updatedAt: 'not-a-date'
			})
		);
		expect(line).toContain('saved 2026-04-15');
	});

	it('counts geography chips toward the chip total', () => {
		const line = summariseSavedSearch(
			search({
				filters: filters({
					geographies: ['state:IL', 'locality:CHI']
				})
			})
		);
		expect(line.startsWith('2 chips')).toBe(true);
	});

	it('joins clauses with " · " separators', () => {
		const line = summariseSavedSearch(
			search({
				metric: 'pay_vs_col',
				filters: filters({ keyword: 'analyst' })
			})
		);
		const parts = line.split(' · ');
		// chips · metric · saved-date
		expect(parts).toHaveLength(3);
		expect(parts[0]).toBe('1 chip');
		expect(parts[1]).toBe('pay vs col');
		expect(parts[2].startsWith('saved ')).toBe(true);
	});
});
