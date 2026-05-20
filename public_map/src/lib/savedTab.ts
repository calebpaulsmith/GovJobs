// Pure helpers for SavedTab.svelte (the Saved tab on /browse).
//
// Kept in a plain .ts module so the helpers are easy to import from vitest
// (which runs in Node without the Svelte plugin) — see savedTab.test.ts.
//
// The component itself (SavedTab.svelte) composes these with the reactive
// jobProfile store, loadSavedSearches/saveSavedSearches, and the
// loadJobDetailsIndex bundle file.

import type { JobFilters } from './filters';
import type { SavedSearch } from './savedSearches';

const MINUTE_MS = 60_000;
const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

/**
 * Short human-readable "saved 2d ago" / "saved just now" style label.
 *
 * Deliberately small — no Intl.RelativeTimeFormat — because we want
 * deterministic output for tests and consistency with the mock copy.
 * Pass `now` to control "now" in tests; production passes Date.now().
 */
export function relativeTime(tsMs: number, now: number): string {
	if (!Number.isFinite(tsMs)) return 'unknown';
	const diff = now - tsMs;
	if (diff < 0) {
		// Future timestamps shouldn't happen in this store, but if a clock
		// skews we shouldn't print a confusing negative number.
		return 'just now';
	}
	if (diff < MINUTE_MS) return 'just now';
	if (diff < HOUR_MS) {
		const mins = Math.floor(diff / MINUTE_MS);
		return `${mins}m ago`;
	}
	if (diff < DAY_MS) {
		const hours = Math.floor(diff / HOUR_MS);
		return `${hours}h ago`;
	}
	const days = Math.floor(diff / DAY_MS);
	if (days === 1) return 'yesterday';
	if (days < 7) return `${days}d ago`;
	if (days < 30) {
		const weeks = Math.floor(days / 7);
		return weeks === 1 ? '1w ago' : `${weeks}w ago`;
	}
	if (days < 365) {
		const months = Math.floor(days / 30);
		return months === 1 ? '1mo ago' : `${months}mo ago`;
	}
	const years = Math.floor(days / 365);
	return years === 1 ? '1y ago' : `${years}y ago`;
}

/**
 * Count the active filter chips on a saved search. Mirrors the spirit of
 * `activeFilterCount` but operates on a JobFilters payload directly without
 * cross-import.
 */
function countChips(filters: JobFilters): number {
	let n = 0;
	if (filters.keyword?.trim()) n += 1;
	if (filters.agencies?.length) n += filters.agencies.length;
	if (filters.series?.trim()) n += 1;
	if (filters.gradeMin?.trim()) n += 1;
	if (filters.gradeMax?.trim()) n += 1;
	if (filters.salaryMin?.trim()) n += 1;
	if (filters.remote && filters.remote !== 'any') n += 1;
	if (filters.hiringPath?.trim()) n += 1;
	if (filters.payPlan?.trim()) n += 1;
	if (filters.geographies?.length) n += filters.geographies.length;
	return n;
}

/**
 * One-line fact summary under a saved-search row's title. Honest about empty
 * filters ("No filters") so users can recognise the "everything" search.
 * Date is the `updatedAt` ISO string from the SavedSearch — the search is
 * either freshly saved (createdAt === updatedAt) or renamed.
 */
export function summariseSavedSearch(search: SavedSearch): string {
	const parts: string[] = [];
	const chips = countChips(search.filters);
	parts.push(chips === 0 ? 'No filters' : `${chips} chip${chips === 1 ? '' : 's'}`);
	if (search.metric && search.metric !== 'postings') {
		parts.push(search.metric.replace(/_/g, ' '));
	}
	const date = isoDateOrNull(search.updatedAt) ?? isoDateOrNull(search.createdAt);
	if (date) parts.push(`saved ${date}`);
	return parts.join(' · ');
}

function isoDateOrNull(value: string | undefined): string | null {
	if (!value) return null;
	const d = new Date(value);
	if (Number.isNaN(d.getTime())) return null;
	// YYYY-MM-DD — short, locale-stable, readable.
	return d.toISOString().slice(0, 10);
}
