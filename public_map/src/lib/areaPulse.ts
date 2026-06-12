// D.5.28 area pulse — computed CLIENT-SIDE from data the bundle already
// ships, resolving the ROADMAP's "precompute vs. lazy-fetch" question for
// `area_pulse`: neither. A precomputed file keyed by (scope, code,
// filter_hash) is combinatorially impossible (the pulse must honor the live
// filter set exactly), and a lazy Function would pull HistoricJoa for
// numbers the open-postings list and the trailing-90-day closed overlay —
// the one historic slice invariant #22 allows in the bundle — already
// contain. So `SmallestAreaCard` feeds its already-filtered jobs through
// `computeAreaPulse` and publishes the result to `mapState.areaPulse`.
//
// Honesty rules (CLAUDE.md hard rule 2 / invariant #20 spirit):
//   • The four headline numbers come from the open postings themselves.
//   • The only delta we can derive without fabrication is "new in last 7d
//     vs. the trailing-90-day weekly average of posting openings", built
//     from open_date across open postings ∪ closed-within-90d features.
//     Anything else (e.g. an "open postings vs. 90d avg" delta) would need
//     daily snapshots we don't have — so it is NOT emitted.
//   • Deltas/annotation are omitted entirely when the baseline is too thin
//     (fewer than MIN_BASELINE_OPENINGS openings in the window) or when the
//     closed overlay is empty — the UI then shows plain numbers, no claims.

import type { Feature, JobDetails } from './data';
import type { AreaPulse } from './store.svelte';

const DAY_MS = 86_400_000;
/** Baseline window: [now-90d, now-7d) — the current week is excluded so the
 *  delta compares "this week" against *prior* weeks. */
const BASELINE_DAYS = 83;
/** Minimum openings in the baseline window before we publish a delta —
 *  below this a percentage would be noise dressed up as insight. */
export const MIN_BASELINE_OPENINGS = 8;

function parseDate(raw: unknown): number | null {
	if (!raw) return null;
	const t = Date.parse(String(raw).slice(0, 10));
	return Number.isFinite(t) ? t : null;
}

function median(values: number[]): number | null {
	if (values.length === 0) return null;
	const sorted = [...values].sort((a, b) => a - b);
	const mid = Math.floor(sorted.length / 2);
	return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Compute the pulse for one area scope. `openJobs` and `closedFeatures` must
 * already be narrowed by the active filters (and thereby the area's
 * geography chips) — this function only counts.
 */
export function computeAreaPulse(
	openJobs: JobDetails[],
	closedFeatures: Feature[],
	area: { scope: string; code: string; label: string },
	now: Date = new Date()
): AreaPulse {
	const nowMs = now.getTime();
	const weekAgo = nowMs - 7 * DAY_MS;
	const baselineStart = nowMs - 90 * DAY_MS;
	const threeDaysOut = nowMs + 3 * DAY_MS;

	let newLast7d = 0;
	let closingSoon3d = 0;
	const windows: number[] = [];
	const openingDatesInBaseline: number[] = [];

	for (const job of openJobs) {
		const opened = parseDate(job.open_date);
		const closes = parseDate(job.close_date);
		if (opened != null) {
			if (opened >= weekAgo && opened <= nowMs) newLast7d += 1;
			if (opened >= baselineStart && opened < weekAgo) openingDatesInBaseline.push(opened);
			if (closes != null && closes >= opened) {
				windows.push(Math.round((closes - opened) / DAY_MS));
			}
		}
		if (closes != null && closes >= nowMs && closes <= threeDaysOut) closingSoon3d += 1;
	}

	// Closed-overlay features are per duty location — dedupe to postings.
	const seenClosed = new Set<string>();
	for (const feature of closedFeatures) {
		const props = feature.properties ?? {};
		const id = String(props.id ?? '');
		if (id && seenClosed.has(id)) continue;
		if (id) seenClosed.add(id);
		const opened = parseDate(props.open_date);
		if (opened != null && opened >= baselineStart && opened < weekAgo) {
			openingDatesInBaseline.push(opened);
		}
	}

	let deltas: AreaPulse['deltas'];
	let annotation: string | null = null;
	const baselineCount = openingDatesInBaseline.length;
	if (baselineCount >= MIN_BASELINE_OPENINGS) {
		const weeklyAvg = baselineCount / (BASELINE_DAYS / 7);
		if (weeklyAvg > 0) {
			const pct = Math.round(((newLast7d - weeklyAvg) / weeklyAvg) * 100);
			const clamped = Math.max(-999, Math.min(999, pct));
			deltas = { newLast7d: clamped };
			const where = area.scope === 'nationwide' ? 'nationwide' : `for ${area.label}`;
			annotation =
				clamped > 0
					? `↑ ${clamped}% above the trailing-90-day weekly average ${where}`
					: clamped < 0
						? `↓ ${Math.abs(clamped)}% below the trailing-90-day weekly average ${where}`
						: `On pace with the trailing-90-day weekly average ${where}`;
		}
	}

	return {
		scope: area.scope,
		code: area.code,
		openPostings: openJobs.length,
		newLast7d,
		medianWindowDays: median(windows) != null ? Math.round(median(windows)!) : null,
		closingSoon3d,
		deltas,
		annotation
	};
}
