// Data bundle loaders. The export script writes 12 files into static/data/;
// see scripts/export_public_map.py. We fetch them with `cache: 'force-cache'`
// since Cloudflare CDNs the bundle and the nightly push busts the cache.
//
// If a file is missing (e.g. before the first export run), we resolve to an
// empty FeatureCollection rather than throwing, so the map skeleton still
// renders for sanity-checking.

const DATA_BASE = (import.meta.env.VITE_DATA_BASE as string | undefined) ?? '/data';

export interface FeatureCollection {
	type: 'FeatureCollection';
	features: Feature[];
}
export interface Feature {
	type: 'Feature';
	geometry: GeoJSON.Geometry | null;
	properties: Record<string, unknown> | null;
}

const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] };

async function fetchJson<T>(filename: string, fallback: T): Promise<T> {
	const url = `${DATA_BASE}/${filename}`;
	try {
		const response = await fetch(url, { cache: 'force-cache' });
		if (!response.ok) {
			console.warn(`[public_map] ${url} returned ${response.status}; using empty fallback.`);
			return fallback;
		}
		return (await response.json()) as T;
	} catch (err) {
		console.warn(`[public_map] failed to fetch ${url}:`, err);
		return fallback;
	}
}

export const loadStates = () =>
	fetchJson<FeatureCollection>('states.geojson', EMPTY_COLLECTION);
export const loadCounties = () =>
	fetchJson<FeatureCollection>('counties.geojson', EMPTY_COLLECTION);
export const loadMetros = () =>
	fetchJson<FeatureCollection>('metros.geojson', EMPTY_COLLECTION);
export const loadLocalities = () =>
	fetchJson<FeatureCollection>('localities.geojson', EMPTY_COLLECTION);
export const loadJobs = () => fetchJson<FeatureCollection>('jobs.geojson', EMPTY_COLLECTION);
export const loadManifest = () => fetchJson<unknown>('manifest.json', null);
