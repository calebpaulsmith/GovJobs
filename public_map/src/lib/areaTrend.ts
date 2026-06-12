// D.5.28 — Here-card 12-month posting volume trend.
//
// This module resolves the ROADMAP's `posting_volume_history.json`
// precompute-vs-on-demand question: **on-demand, via the existing
// `/api/job-history` Pages Function (ADR-0029)** — no new bundle file and no
// new endpoint. A precomputed agency × locality × series × month file is
// combinatorially explosive (and invariant #22 forbids bulk HistoricJoa in
// the bundle anyway), while the Function already returns exactly the monthly
// buckets the sparkline needs, edge-cached for 24 hours.
//
// Pure helpers only — the AreaTrendSparkline component does the fetching.
// Honesty rules (hard rule 2 / invariant #20 spirit):
//   • HistoricJoa cannot honor every public-map filter. We send what it (and
//     the Function's post-filter) supports — agency, series, grade, state —
//     and surface everything else as an explicit approximation note. The
//     caption always states exactly which slice the trend reflects.
//   • OPM localities are not a HistoricJoa filter; a locality-scoped card
//     falls back to the locality's primary state and says so.
//   • Months with zero postings render as zero-height bars, not gaps — a
//     missing bucket and "no postings that month" must look different from
//     "month not in window".

import type { JobFilters } from './filters';
import type { ResolvedArea } from './areaCard';
import { cacheKey, type MonthlyBucket, type PostingHistoryQuery, type WindowKey } from './jobHistory';
import { localityPrimaryState } from './compensation';

/** The sparkline is fixed to the trailing year per the ROADMAP slice
 *  ("monthly counts for trailing 12 months"). The JobCard's Posting
 *  Intelligence tab keeps the full window-pill set. */
export const TREND_WINDOW: WindowKey = '1yr';

export interface AreaTrendQuery {
	query: PostingHistoryQuery;
	/** Short human-readable slice description, e.g. "agency HSCB · state CO". */
	description: string;
	/** Explicit approximation notes (locality→state fallback, ignored extra
	 *  chips). Empty when the query reflects the area + filters exactly. */
	notes: string[];
	/** Stable key for staleness detection — when the live filters/area drift
	 *  from the loaded payload, the UI offers a reload instead of silently
	 *  showing the old slice (and never auto-refetches). */
	key: string;
}

/**
 * Map the resolved area + active filters onto the `/api/job-history`
 * contract. Only fields HistoricJoa (or the Function's post-filter) actually
 * supports are sent; everything dropped is named in `notes`. `window`
 * defaults to the sparkline's 1yr; the What-to-watch note passes 3yr.
 */
export function buildAreaTrendQuery(
	area: ResolvedArea,
	filters: JobFilters,
	window: WindowKey = TREND_WINDOW
): AreaTrendQuery {
	const notes: string[] = [];

	let state: string | undefined;
	if (area.scope === 'state') {
		state = area.code;
	} else if (area.scope === 'locality') {
		const primary = localityPrimaryState(area.code, area.label);
		if (primary) {
			state = primary;
			notes.push(
				`HistoricJoa has no locality filter — trend uses ${area.label}'s primary state (${primary}), so it is approximate.`
			);
		} else {
			notes.push(
				`HistoricJoa has no locality filter and ${area.label} could not be mapped to a state — trend is nationwide.`
			);
		}
	}

	const agencies = filters.agencies ?? [];
	const agencyCode = (agencies[0] ?? '').trim() || undefined;
	if (agencies.length > 1) {
		notes.push(
			`Only the first agency chip (${agencies[0]}) anchors the history query; ${agencies.length - 1} more chip${agencies.length > 2 ? 's are' : ' is'} not included.`
		);
	}

	const seriesList = filters.series ?? [];
	const series = (seriesList[0] ?? '').trim() || undefined;
	if (seriesList.length > 1) {
		notes.push(
			`Only the first series chip (${seriesList[0]}) anchors the history query; ${seriesList.length - 1} more chip${seriesList.length > 2 ? 's are' : ' is'} not included.`
		);
	}

	const grade = (filters.gradeMin ?? '').trim() || undefined;

	const query: PostingHistoryQuery = { agencyCode, series, grade, state };

	const parts: string[] = [];
	if (agencyCode) parts.push(`agency ${agencyCode.toUpperCase()}`);
	if (series) parts.push(`series ${series}`);
	if (grade) parts.push(`grade ${grade}`);
	if (state) parts.push(`state ${state.toUpperCase()}`);
	const description = parts.length ? parts.join(' · ') : 'all federal postings';

	return { query, description, notes, key: cacheKey(query, window) };
}

/**
 * Zero-fill the Function's sparse monthly buckets across the payload's
 * [start_date, end_date] range (inclusive of both endpoint months) so the
 * sparkline renders one bar per calendar month. Malformed dates fall back to
 * the buckets as-given rather than guessing.
 */
export function fillMonths(
	monthly: MonthlyBucket[],
	startDate: string,
	endDate: string
): MonthlyBucket[] {
	const start = parseMonth(startDate);
	const end = parseMonth(endDate);
	if (!start || !end || cmp(start, end) > 0) return monthly;

	const counts = new Map<string, number>();
	for (const bucket of monthly) counts.set(bucket.month, bucket.count);

	const out: MonthlyBucket[] = [];
	let [year, month] = start;
	// Hard ceiling well above any supported window so a bad date pair can
	// never loop unbounded.
	for (let i = 0; i < 200; i++) {
		const key = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}`;
		out.push({ month: key, count: counts.get(key) ?? 0 });
		if (year === end[0] && month === end[1]) break;
		month += 1;
		if (month > 12) {
			month = 1;
			year += 1;
		}
	}
	return out;
}

function parseMonth(date: string): [number, number] | null {
	const m = /^(\d{4})-(\d{2})/.exec(String(date ?? ''));
	if (!m) return null;
	const year = Number(m[1]);
	const month = Number(m[2]);
	if (!Number.isFinite(year) || month < 1 || month > 12) return null;
	return [year, month];
}

function cmp(a: [number, number], b: [number, number]): number {
	return a[0] !== b[0] ? a[0] - b[0] : a[1] - b[1];
}
