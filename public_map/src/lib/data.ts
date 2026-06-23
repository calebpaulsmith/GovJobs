// Data bundle loaders. The export script writes 12 files into static/data/;
// see scripts/export_public_map.py. Cloudflare can cache the production bundle,
// but local dev should always re-read the latest exported files.
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

export interface AgencyOption {
	code: string | null;
	name: string;
	label?: string;
	department_code?: string | null;
	department_name?: string | null;
	aliases?: string[];
	postings: number;
}

export interface SeriesOption {
	code: string;
	label: string;
	postings: number;
}

// Country catalog (USAJOBS country code + display name + posting count),
// emitted by scripts/export_public_map.py as countries.json. Feeds the country
// scope multi-select for overseas US-fed jobs. "US" is included for domestic.
export interface CountryOption {
	code: string;
	name: string;
	postings: number;
}

export interface ZipCentroid {
	zip: string;
	lat: number;
	lon: number;
	city?: string;
	state?: string;
	county_fips?: string;
}

export interface PayGridLocality {
	code?: string | null;
	name?: string | null;
	adjustment_pct?: number | null;
	inclusion_type?: string | null;
	source?: string | null;
}

export type PayGridStatus = 'exact' | 'approximated' | 'unavailable';

export interface PayGrid {
	status: PayGridStatus;
	year: number;
	pay_plan?: string | null;
	locality?: PayGridLocality | null;
	method?: 'locality_row' | 'base_plus_adjustment' | null;
	grades?: Record<string, Record<string, number>>;
	notes?: string[];
	missing_reason?: string | null;
}

// Overseas US-fed pay (DSSR), precomputed at export from
// reference_data.overseas_compensation so the website and dashboard show the
// same traceable numbers. Present only on overseas postings; null for US.
export interface OverseasPayLine {
	label: string;
	dssr: string;
	pct: number | null;
	basis: string;
	amount: number | null; // null = withheld (e.g. salary outside the table)
	estimated: boolean;
	assumption?: string;
	source_url: string;
	effective_date?: string | null;
}

export interface OverseasPay {
	base_salary: number | null;
	matched_post: { country_name?: string | null; post_name?: string | null; match?: string | null } | null;
	lines: OverseasPayLine[];
	estimated_total: number | null;
	notes: string[];
	family_size: number;
}

export interface JobDetails {
	id: number;
	title: string;
	agency?: string | null;
	department?: string | null;
	agency_code?: string | null;
	// USAJOBS country code denormalized at export ("US" domestic; "IT", "JP", …
	// overseas). Drives the country scope filter on the Browse list path.
	country?: string | null;
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
	status?: string | null;
	closed_within_days?: number | null;
	hiring_paths?: string | null;
	url?: string | null;
	locality_code?: string | null;
	locations?: JobLocation[];
	pay_grid?: PayGrid | null;
	// Overseas US-fed pay breakdown (DSSR); null/undefined for US postings.
	overseas_pay?: OverseasPay | null;
	// D.5.28: <=200-char previews from job_text. Omitted (undefined) or null
	// when the announcement-text importer hasn't pulled this posting yet.
	summary_excerpt?: string | null;
	qualifications_excerpt?: string | null;
	// D.5.28: "3rd posting · 14 mo" from the latest Repost Detector run,
	// denormalized at export. Review evidence, not certainty — render dashed.
	historical_badge?: string | null;
}

export type PayTables = Record<string, Record<string, Record<string, Record<string, Record<string, number>>>>>;

export interface StateColRow {
	year: number | null;
	rpp_overall: number | null;
	rpp_goods: number | null;
	rpp_services: number | null;
	rpp_rents: number | null;
	source: string;
}
export interface CostOfLiving {
	by_state: Record<string, StateColRow>;
	by_cbsa: Record<string, unknown>;
}

let jobDetailsCache: Record<string, JobDetails> | null = null;
let agencyOptionsCache: AgencyOption[] | null = null;
let seriesOptionsCache: SeriesOption[] | null = null;
let countryOptionsCache: CountryOption[] | null = null;
let payTablesCache: PayTables | null = null;
let jobDetailsIndexCache: Record<string, JobDetails> | null = null;
let zipCentroidsCache: ZipCentroid[] | null = null;
let costOfLivingCache: CostOfLiving | null = null;

const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] };

// manifest.json is tiny and carries `generated_at`, which doubles as a
// cache-busting token. It is always fetched fresh (no-store). Every other
// bundle file is then fetched as `<file>?v=<generated_at>`: the same bundle
// resolves to the same URL (cache hit), and a nightly refresh changes
// generated_at, so the URL changes and the browser is guaranteed to pull
// the new file. Without this, force-cache + stable filenames keep serving a
// stale bundle long after the data has been refreshed.
let bundleVersion: string | null = null;
let manifestCache: unknown;

async function loadBundleVersion(): Promise<string> {
	if (bundleVersion !== null) return bundleVersion;
	const url = `${DATA_BASE}/manifest.json`;
	try {
		const response = await fetch(url, { cache: 'no-store' });
		manifestCache = response.ok ? await response.json() : null;
	} catch (err) {
		console.warn(`[public_map] failed to fetch ${url}:`, err);
		manifestCache = null;
	}
	const generatedAt = (manifestCache as { generated_at?: unknown } | null)?.generated_at;
	bundleVersion = generatedAt ? String(generatedAt) : 'unversioned';
	return bundleVersion;
}

// Cloudflare Pages rejects any single file over 25 MiB, so the exporter
// writes oversized bundle files (e.g. jobs.geojson) as numbered parts and
// records the part count in manifest.json's `split` map. Files absent from
// that map are single-file.
async function loadSplitMap(): Promise<Record<string, number>> {
	await loadBundleVersion();
	const split = (manifestCache as { split?: unknown } | null)?.split;
	return split && typeof split === 'object' ? (split as Record<string, number>) : {};
}

// `jobs.geojson` split into 3 parts -> ['jobs.geojson','jobs.2.geojson','jobs.3.geojson'].
// The part number is inserted before the final extension; part 1 keeps the
// original name.
export function partFilename(name: string, index: number): string {
	if (index <= 1) return name;
	const dot = name.lastIndexOf('.');
	if (dot === -1) return `${name}.${index}`;
	return `${name.slice(0, dot)}.${index}${name.slice(dot)}`;
}

/** Concatenate the `features` of several FeatureCollections into one. */
export function mergeFeatureCollections(parts: FeatureCollection[]): FeatureCollection {
	return {
		type: 'FeatureCollection',
		features: parts.flatMap((part) => part?.features ?? [])
	};
}

/** Shallow-merge several plain dicts into one (later parts override earlier). */
export function mergeDicts<T>(parts: Record<string, T>[]): Record<string, T> {
	return Object.assign({}, ...parts);
}

/**
 * Fetch a bundle file that may have been split into numbered parts. Reads the
 * part count from the manifest's `split` map (default 1), fetches every part
 * in parallel, and merges them with `merge`.
 */
async function fetchSplitJson<P, T>(
	filename: string,
	merge: (parts: P[]) => T,
	emptyPart: P
): Promise<T> {
	const splitMap = await loadSplitMap();
	const partCount = Math.max(1, splitMap[filename] ?? 1);
	const names = Array.from({ length: partCount }, (_, i) => partFilename(filename, i + 1));
	const parts = await Promise.all(names.map((name) => fetchJson<P>(name, emptyPart)));
	return merge(parts);
}

async function fetchJson<T>(filename: string, fallback: T): Promise<T> {
	const version = await loadBundleVersion();
	const url = `${DATA_BASE}/${filename}?v=${encodeURIComponent(version)}`;
	try {
		const response = await fetch(url, { cache: import.meta.env.DEV ? 'no-store' : 'force-cache' });
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
export const loadJobs = () =>
	fetchSplitJson<FeatureCollection, FeatureCollection>(
		'jobs.geojson',
		mergeFeatureCollections,
		EMPTY_COLLECTION
	);
export const loadClosedJobs = () =>
	fetchJson<FeatureCollection>('closed_jobs.geojson', EMPTY_COLLECTION);
export const loadFederalProperties = () =>
	fetchJson<FeatureCollection>('federal_properties.geojson', EMPTY_COLLECTION);
export async function loadManifest(): Promise<unknown> {
	// loadBundleVersion already fetched and cached manifest.json fresh.
	await loadBundleVersion();
	return manifestCache ?? null;
}
export async function loadAgencyOptions(): Promise<AgencyOption[]> {
	agencyOptionsCache ??= (await fetchJson<AgencyOption[]>('agencies.json', [])).map((option) => ({
		...option,
		name: option.name ?? option.label ?? option.code ?? 'Unknown',
		aliases: option.aliases ?? []
	}));
	return agencyOptionsCache;
}

// Occupational series catalog (code + OPM title + global posting count),
// emitted by scripts/export_public_map.py as series.json. Used purely to label
// the series multi-select; which series are actually *offered* in the dropdown
// is derived live from the loaded jobs, narrowed by the other active filters.
export async function loadSeriesOptions(): Promise<SeriesOption[]> {
	seriesOptionsCache ??= (await fetchJson<SeriesOption[]>('series.json', [])).map((option) => ({
		code: String(option.code ?? ''),
		label: option.label ?? String(option.code ?? ''),
		postings: Number(option.postings ?? 0)
	}));
	return seriesOptionsCache;
}

// Country catalog for the country scope multi-select, emitted as countries.json.
// Like series, which countries are *offered* in the dropdown is derived live
// from the loaded jobs; this list supplies display names + global counts.
export async function loadCountryOptions(): Promise<CountryOption[]> {
	countryOptionsCache ??= (await fetchJson<CountryOption[]>('countries.json', [])).map((option) => ({
		code: String(option.code ?? '').toUpperCase(),
		name: option.name ?? String(option.code ?? ''),
		postings: Number(option.postings ?? 0)
	}));
	return countryOptionsCache;
}

export async function loadJobDetailsIndex(): Promise<Record<string, JobDetails>> {
	jobDetailsIndexCache ??= await fetchSplitJson<Record<string, JobDetails>, Record<string, JobDetails>>(
		'jobs_detail.json',
		mergeDicts,
		{}
	);
	return jobDetailsIndexCache;
}

export async function loadJobDetails(id: string | number): Promise<JobDetails | null> {
	jobDetailsCache ??= await loadJobDetailsIndex();
	return jobDetailsCache[String(id)] ?? null;
}

export async function loadPayTables(): Promise<PayTables> {
	payTablesCache ??= await fetchJson<PayTables>('pay_tables.json', {});
	return payTablesCache;
}

export async function loadZipCentroids(): Promise<ZipCentroid[]> {
	zipCentroidsCache ??= await fetchJson<ZipCentroid[]>('zip_centroids.json', []);
	return zipCentroidsCache;
}

export async function loadCostOfLiving(): Promise<CostOfLiving> {
	costOfLivingCache ??= await fetchJson<CostOfLiving>('cost_of_living.json', {
		by_state: {},
		by_cbsa: {}
	});
	return costOfLivingCache;
}
