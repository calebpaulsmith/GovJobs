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

export interface JobLocation {
	city?: string | null;
	state?: string | null;
	location_text?: string | null;
}

export interface JobDetails {
	id: number;
	title: string;
	agency?: string | null;
	department?: string | null;
	agency_code?: string | null;
	series?: string | null;
	pay_plan?: string | null;
	grade_low?: string | null;
	grade_high?: string | null;
	salary_min?: number | null;
	salary_max?: number | null;
	salary_type?: string | null;
	remote_status?: string | null;
	open_date?: string | null;
	close_date?: string | null;
	hiring_paths?: string | null;
	url?: string | null;
	locality_code?: string | null;
	locations?: JobLocation[];
}

export type PayTables = Record<string, Record<string, Record<string, Record<string, Record<string, number>>>>>;

let jobDetailsCache: Record<string, JobDetails> | null = null;
let payTablesCache: PayTables | null = null;

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

export async function loadJobDetails(id: string | number): Promise<JobDetails | null> {
	jobDetailsCache ??= await fetchJson<Record<string, JobDetails>>('jobs_detail.json', {});
	return jobDetailsCache[String(id)] ?? null;
}

export async function loadPayTables(): Promise<PayTables> {
	payTablesCache ??= await fetchJson<PayTables>('pay_tables.json', {});
	return payTablesCache;
}
