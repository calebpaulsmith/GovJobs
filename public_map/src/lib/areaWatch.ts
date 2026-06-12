// D.5.28 — "What to watch" note on the Here card (per ADR-0036).
//
// Resolves the ROADMAP's "on-demand area summary" slice the way the operator
// decided on 2026-06-12: **deterministic and keyless** — no LLM call, no new
// Pages Function, no secret in the deployment. The note is derived
// client-side from a 3-year `/api/job-history` payload (the existing
// ADR-0029 edge-cached Function), so the only upstream is the same public,
// key-less HistoricJoa endpoint everything else uses.
//
// Every claim has an explicit evidence bar, and anything that fails the bar
// is *surfaced* in `withheld` with the reason — never silently dropped and
// never fabricated (hard rule 2 / invariant #20 spirit):
//   • Year-over-year: trailing 12 complete months vs the 12 before. Needs
//     24 complete months, an untruncated payload, and ≥ MIN_PRIOR_YEAR
//     openings in the prior year (a % against a tiny base is noise).
//   • Seasonality: average openings per calendar month across the window.
//     Claims a peak only when the peak month is ≥ PEAK_RATIO × the monthly
//     mean; otherwise says (defensibly) that no strong pattern exists.
//     Withheld entirely when truncated or the sample is thin.
//   • Typical posting window: median open→close days across the returned
//     records. A per-record property, so it survives truncation, but still
//     needs ≥ MIN_CLOSE_WINDOW_SAMPLES usable date pairs.
//   • The basis line always states the sample size, date range, and the
//     upstream cap when it fired.

import { fillMonths } from './areaTrend';
import type { HistoryPayload, TrimmedRecord, WindowKey } from './jobHistory';

/** The watch note needs multiple samples of each calendar month; 3yr is the
 *  smallest window that gives three. Longer windows raise truncation risk on
 *  busy slices without improving the claims much. */
export const WATCH_WINDOW: WindowKey = '3yr';

export const MIN_PRIOR_YEAR_OPENINGS = 12;
export const MIN_SEASONALITY_TOTAL = 24;
export const SEASONALITY_PEAK_RATIO = 1.5;
export const MIN_CLOSE_WINDOW_SAMPLES = 8;

export interface WatchNote {
	/** Claims that passed their evidence bar, in display order. */
	lines: string[];
	/** Sample size + date range + truncation caveat. Always present. */
	basis: string;
	/** Claims that were withheld, with the reason each failed its bar. */
	withheld: string[];
}

const MONTH_NAMES = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December'
];

const DAY_MS = 86_400_000;

export function computeWatchNote(payload: HistoryPayload): WatchNote | null {
	if (payload.status !== 'ok') return null;

	const lines: string[] = [];
	const withheld: string[] = [];

	const months = fillMonths(payload.monthly, payload.start_date, payload.end_date);
	// The final bucket is the in-progress month — drop it so neither the
	// year-over-year split nor the seasonal averages compare partial data
	// against complete months.
	const complete = months.slice(0, -1);

	// --- Year-over-year ------------------------------------------------------
	if (payload.truncated) {
		withheld.push(
			'Year-over-year and seasonality withheld — the result hit the upstream record cap, so monthly counts are floors, not totals.'
		);
	} else if (complete.length < 24) {
		withheld.push(
			'Year-over-year withheld — the loaded window covers fewer than 24 complete months.'
		);
	} else {
		const recent = complete.slice(-12).reduce((sum, m) => sum + m.count, 0);
		const prior = complete.slice(-24, -12).reduce((sum, m) => sum + m.count, 0);
		if (prior < MIN_PRIOR_YEAR_OPENINGS) {
			withheld.push(
				`Year-over-year withheld — only ${prior} opening${prior === 1 ? '' : 's'} in the prior 12 months (a percentage against that base would be noise).`
			);
		} else {
			const pct = Math.round(((recent - prior) / prior) * 100);
			if (pct > 0) {
				lines.push(
					`Trailing 12 months: ${recent.toLocaleString()} openings — ↑ ${pct}% vs the prior 12 months (${prior.toLocaleString()}).`
				);
			} else if (pct < 0) {
				lines.push(
					`Trailing 12 months: ${recent.toLocaleString()} openings — ↓ ${Math.abs(pct)}% vs the prior 12 months (${prior.toLocaleString()}).`
				);
			} else {
				lines.push(
					`Trailing 12 months: ${recent.toLocaleString()} openings — on pace with the prior 12 months (${prior.toLocaleString()}).`
				);
			}
		}
	}

	// --- Seasonality -----------------------------------------------------------
	// (Truncation withholding above already covers this branch.)
	if (!payload.truncated) {
		const total = complete.reduce((sum, m) => sum + m.count, 0);
		if (complete.length < 24 || total < MIN_SEASONALITY_TOTAL) {
			withheld.push(
				`Seasonality withheld — ${total.toLocaleString()} opening${total === 1 ? '' : 's'} across ${complete.length} complete months is too thin to call a pattern (need ≥ ${MIN_SEASONALITY_TOTAL} over ≥ 24 months).`
			);
		} else {
			// Average per calendar month, normalized by how many times each
			// calendar month appears in the window (a 3yr window holds three
			// Marches but the leading/trailing partial year may not).
			const sums = new Array<number>(12).fill(0);
			const occurrences = new Array<number>(12).fill(0);
			for (const bucket of complete) {
				const idx = Number(bucket.month.slice(5, 7)) - 1;
				if (idx < 0 || idx > 11) continue;
				sums[idx] += bucket.count;
				occurrences[idx] += 1;
			}
			const averages = sums.map((sum, i) => (occurrences[i] > 0 ? sum / occurrences[i] : 0));
			const mean = averages.reduce((a, b) => a + b, 0) / 12;
			const peak = Math.max(...averages);
			if (mean > 0 && peak >= SEASONALITY_PEAK_RATIO * mean) {
				const peakIdx = averages.indexOf(peak);
				const runnerUp = averages
					.map((avg, i) => ({ avg, i }))
					.filter(({ i }) => i !== peakIdx)
					.sort((a, b) => b.avg - a.avg)[0];
				const monthsLabel =
					runnerUp && runnerUp.avg >= 0.9 * peak
						? `${MONTH_NAMES[peakIdx]} and ${MONTH_NAMES[runnerUp.i]}`
						: MONTH_NAMES[peakIdx];
				lines.push(`Openings in this slice have historically peaked in ${monthsLabel}.`);
			} else {
				lines.push('No strong seasonal pattern — openings are spread across the year.');
			}
		}
	}

	// --- Typical posting window -------------------------------------------------
	const windows: number[] = [];
	for (const record of payload.records) {
		const days = closeWindowDays(record);
		if (days != null) windows.push(days);
	}
	if (windows.length >= MIN_CLOSE_WINDOW_SAMPLES) {
		const med = Math.round(median(windows));
		lines.push(
			`Historic postings in this slice stayed open a median of ${med} day${med === 1 ? '' : 's'}${med <= 14 ? ' — short windows favor applying early' : ''}.`
		);
	} else {
		withheld.push(
			`Typical posting window withheld — only ${windows.length} historic posting${windows.length === 1 ? '' : 's'} had usable open/close dates (need ≥ ${MIN_CLOSE_WINDOW_SAMPLES}).`
		);
	}

	const basis = `Based on ${payload.total.toLocaleString()} HistoricJoa postings, ${payload.start_date} → ${payload.end_date}${payload.truncated ? ' (capped at the upstream page limit)' : ''}.`;

	return { lines, basis, withheld };
}

function closeWindowDays(record: TrimmedRecord): number | null {
	const open = parseDate(record.open_date);
	const close = parseDate(record.close_date);
	if (open == null || close == null || close < open) return null;
	return Math.round((close - open) / DAY_MS);
}

function parseDate(raw: unknown): number | null {
	if (!raw) return null;
	const t = Date.parse(String(raw).slice(0, 10));
	return Number.isFinite(t) ? t : null;
}

function median(values: number[]): number {
	const sorted = [...values].sort((a, b) => a - b);
	const mid = Math.floor(sorted.length / 2);
	return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
