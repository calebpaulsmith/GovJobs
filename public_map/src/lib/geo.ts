// Radius-search geometry helpers (D.5.30, per ADR-0033).
//
// Pure functions only — no Svelte, no DOM — so both the filter pipeline and
// the unit tests can use them. Distances are great-circle (haversine) miles
// against each posting's published duty-station coordinates.

import type { FeatureCollection } from './data';

export interface RadiusChip {
	/** Center as [lng, lat] to match GeoJSON / mapbox coordinate order. */
	center: [number, number];
	/** One of RADIUS_OPTIONS. Stored as a number so math is direct. */
	miles: number;
	/** Human label for the chip, e.g. "Chicago, IL". */
	label: string;
	/**
	 * Anywhere-remote postings are included by default (a remote job could be
	 * worked from inside the radius). Per-chip opt-out flips this to false.
	 */
	includeRemote: boolean;
}

export const RADIUS_OPTIONS = [25, 50, 100, 250] as const;
export const DEFAULT_RADIUS_MILES = 50;

const EARTH_RADIUS_MI = 3958.7613; // mean Earth radius in statute miles

function toRad(deg: number): number {
	return (deg * Math.PI) / 180;
}

/** Great-circle distance in statute miles between two [lng, lat] points. */
export function haversineMiles(a: [number, number], b: [number, number]): number {
	const [lng1, lat1] = a;
	const [lng2, lat2] = b;
	if (![lng1, lat1, lng2, lat2].every(Number.isFinite)) return Number.POSITIVE_INFINITY;
	const dLat = toRad(lat2 - lat1);
	const dLng = toRad(lng2 - lng1);
	const s =
		Math.sin(dLat / 2) ** 2 +
		Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
	return 2 * EARTH_RADIUS_MI * Math.asin(Math.min(1, Math.sqrt(s)));
}

/** Smallest distance (miles) from `coord` to any chip center it falls under, or null. */
export function nearestRadiusMiles(
	coord: [number, number] | null | undefined,
	radii: RadiusChip[]
): number | null {
	if (!coord || !radii.length) return null;
	let best: number | null = null;
	for (const chip of radii) {
		const d = haversineMiles(coord, chip.center);
		if (d <= chip.miles && (best === null || d < best)) best = d;
	}
	return best;
}

/**
 * Does any of a posting's coordinates fall inside any radius chip — or is the
 * posting anywhere-remote and at least one chip includes remote?
 *
 * `coords` is the list of duty-station coordinates for one posting (a posting
 * can have several). `isRemoteAnywhere` is true when the posting's remote
 * status is "remote" (no fixed duty station).
 */
export function radiusMatch(
	coords: Array<[number, number]>,
	isRemoteAnywhere: boolean,
	radii: RadiusChip[]
): boolean {
	if (!radii.length) return true;
	if (isRemoteAnywhere && radii.some((chip) => chip.includeRemote)) return true;
	for (const coord of coords) {
		for (const chip of radii) {
			if (haversineMiles(coord, chip.center) <= chip.miles) return true;
		}
	}
	return false;
}

/**
 * Build a posting-id → [[lng, lat], ...] index from the per-location
 * jobs.geojson FeatureCollection. A multi-location posting contributes several
 * Point features sharing one `id`; all of their coordinates are collected so
 * radius matching can test every duty station.
 */
export function coordsByJobId(jobs: FeatureCollection | null): Map<string, Array<[number, number]>> {
	const out = new Map<string, Array<[number, number]>>();
	if (!jobs) return out;
	for (const feature of jobs.features) {
		const id = String(feature.properties?.id ?? '');
		if (!id) continue;
		const geom = feature.geometry;
		if (!geom || geom.type !== 'Point') continue;
		const lng = Number(geom.coordinates?.[0]);
		const lat = Number(geom.coordinates?.[1]);
		if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
		const list = out.get(id);
		if (list) list.push([lng, lat]);
		else out.set(id, [[lng, lat]]);
	}
	return out;
}

/** Serialize a chip to the URL value `lng,lat,miles[,xr]` (xr = exclude remote). */
export function radiusToParam(chip: RadiusChip): string {
	const core = `${chip.center[0]},${chip.center[1]},${chip.miles}`;
	return chip.includeRemote ? core : `${core},xr`;
}

/** Parse a `lng,lat,miles[,xr]` URL value back into a chip, or null if malformed. */
export function radiusFromParam(value: string): RadiusChip | null {
	const parts = String(value ?? '').split(',');
	if (parts.length < 3) return null;
	const lng = Number(parts[0]);
	const lat = Number(parts[1]);
	const miles = Number(parts[2]);
	if (![lng, lat, miles].every(Number.isFinite) || miles <= 0) return null;
	const includeRemote = parts[3]?.trim().toLowerCase() !== 'xr';
	return {
		center: [lng, lat],
		miles,
		// The URL form is intentionally label-free (ADR-0033 `radius=lng,lat,miles`);
		// synthesize a coordinate label so a chip restored from a bare URL still reads.
		label: `${lat.toFixed(2)}, ${lng.toFixed(2)}`,
		includeRemote
	};
}

/** Normalize an unknown value (from saved searches / URL) into a RadiusChip[]. */
export function normalizeRadii(value: unknown): RadiusChip[] {
	if (!Array.isArray(value)) return [];
	const out: RadiusChip[] = [];
	const seen = new Set<string>();
	for (const raw of value) {
		const chip = coerceChip(raw);
		if (!chip) continue;
		const key = radiusToParam(chip);
		if (seen.has(key)) continue;
		seen.add(key);
		out.push(chip);
	}
	return out;
}

function coerceChip(raw: unknown): RadiusChip | null {
	if (!raw || typeof raw !== 'object') return null;
	const r = raw as Record<string, unknown>;
	const center = r.center;
	if (!Array.isArray(center) || center.length < 2) return null;
	const lng = Number(center[0]);
	const lat = Number(center[1]);
	const miles = Number(r.miles);
	if (![lng, lat, miles].every(Number.isFinite) || miles <= 0) return null;
	return {
		center: [lng, lat],
		miles,
		label: String(r.label ?? `${lat.toFixed(2)}, ${lng.toFixed(2)}`),
		includeRemote: r.includeRemote !== false
	};
}
