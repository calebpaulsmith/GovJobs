// Pure helpers for the Here tab's SmallestAreaCard.
//
// `resolveArea` reads the active JobFilters and picks the most precise
// geography chip (locality > state). It returns a discriminated union so
// callers can fall through to "Nationwide" without null checks. `county:`
// chips are intentionally ignored — jobs_detail.json carries no county
// FIPS yet, so a county chip cannot localize anything; per the spec we
// fall through to the next chip or to Nationwide.
//
// `urgencyCounts` buckets job details by their close_date relative to
// today (today's date is supplied so tests are deterministic).

import type { Feature, FeatureCollection, JobDetails } from './data';
import type { JobFilters } from './filters';

export type ResolvedArea =
	| {
			scope: 'locality';
			code: string;
			label: string;
			feature: Feature;
	  }
	| {
			scope: 'state';
			code: string;
			label: string;
			feature: Feature | null;
	  }
	| {
			scope: 'nationwide';
			code: null;
			label: 'Nationwide';
			feature: null;
	  };

export interface UrgencyCounts {
	today: number;
	le3d: number;
	le7d: number;
}

const NATIONWIDE: ResolvedArea = {
	scope: 'nationwide',
	code: null,
	label: 'Nationwide',
	feature: null
};

function findLocalityFeature(
	collection: FeatureCollection | null | undefined,
	code: string
): Feature | null {
	if (!collection || !Array.isArray(collection.features)) return null;
	const target = code.toUpperCase();
	for (const feature of collection.features) {
		const props = feature.properties ?? {};
		if (String(props.code ?? '').toUpperCase() === target) return feature;
	}
	return null;
}

function findStateFeature(
	collection: FeatureCollection | null | undefined,
	code: string
): Feature | null {
	if (!collection || !Array.isArray(collection.features)) return null;
	const target = code.toUpperCase();
	for (const feature of collection.features) {
		const props = feature.properties ?? {};
		if (String(props.state ?? '').toUpperCase() === target) return feature;
	}
	return null;
}

/**
 * Pick the highest-precision geography chip from the filter and resolve it
 * against the loaded states/localities feature collections.
 *
 * Precedence:
 *   1. locality:* (any chip wins over a state chip)
 *   2. state:*
 *   3. Nationwide (no chip, or only county:* / unknown chips)
 *
 * Multiple geo chips of the same type: just use the first.
 */
export function resolveArea(
	filters: JobFilters,
	states: FeatureCollection | null | undefined,
	localities: FeatureCollection | null | undefined
): ResolvedArea {
	const geographies = filters?.geographies ?? [];
	let firstLocality: string | null = null;
	let firstState: string | null = null;

	for (const chip of geographies) {
		const sep = chip.indexOf(':');
		if (sep === -1) continue;
		const type = chip.slice(0, sep).toLowerCase();
		const code = chip.slice(sep + 1).toUpperCase();
		if (!code) continue;
		if (type === 'locality' && firstLocality === null) firstLocality = code;
		else if (type === 'state' && firstState === null) firstState = code;
		// county: chips are intentionally skipped — see header comment.
	}

	if (firstLocality !== null) {
		const feature = findLocalityFeature(localities, firstLocality);
		const name = feature ? String(feature.properties?.name ?? firstLocality) : firstLocality;
		return {
			scope: 'locality',
			code: firstLocality,
			label: name,
			feature: feature ?? ({ type: 'Feature', geometry: null, properties: { code: firstLocality, name: firstLocality } } as Feature)
		};
	}

	if (firstState !== null) {
		const feature = findStateFeature(states, firstState);
		const name = feature ? String(feature.properties?.name ?? firstState) : firstState;
		return {
			scope: 'state',
			code: firstState,
			label: name,
			feature
		};
	}

	return NATIONWIDE;
}

/**
 * Bucket job details by `close_date` relative to `today`.
 *
 *   today: closing today (days == 0)
 *   le3d:  closing in <= 3 days (inclusive of today)
 *   le7d:  closing in <= 7 days (inclusive of today)
 *
 * Jobs with no close_date or a parsed date in the past are excluded. `today`
 * defaults to the current date at local midnight; pass a Date explicitly in
 * tests for determinism.
 */
export function urgencyCounts(jobs: JobDetails[], today: Date = new Date()): UrgencyCounts {
	const base = new Date(today);
	base.setHours(0, 0, 0, 0);
	const baseMs = base.getTime();

	let countToday = 0;
	let countLe3 = 0;
	let countLe7 = 0;

	for (const job of jobs) {
		if (!job.close_date) continue;
		const close = new Date(job.close_date);
		if (Number.isNaN(close.getTime())) continue;
		close.setHours(0, 0, 0, 0);
		const days = Math.round((close.getTime() - baseMs) / 86400000);
		if (days < 0) continue;
		if (days === 0) countToday += 1;
		if (days <= 3) countLe3 += 1;
		if (days <= 7) countLe7 += 1;
	}

	return { today: countToday, le3d: countLe3, le7d: countLe7 };
}
