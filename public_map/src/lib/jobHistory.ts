// D.5.24 — On-demand Posting Intelligence (per ADR-0029).
//
// Pure helpers shared by `functions/api/job-history.ts` (Cloudflare Pages
// Function that proxies USAJOBS HistoricJoa) and the JobCard "Posting
// Intelligence" tab. Keeping query construction, response trimming, and
// monthly bucketing in one module guarantees the worker and the client agree
// on the contract documented in ADR-0029.
//
// The HistoricJoa endpoint is public (no API key required per CLAUDE.md), so
// the Function may call it directly from the edge. We never bulk-import
// HistoricJoa; this module exists precisely so per-job and per-filter
// "show me the history of similar postings" requests can run lazily and be
// edge-cached for 24h.

export type WindowKey = '1mo' | '3mo' | '6mo' | '1yr' | '3yr' | '5yr' | '10yr';

export const WINDOW_KEYS: readonly WindowKey[] = [
	'1mo',
	'3mo',
	'6mo',
	'1yr',
	'3yr',
	'5yr',
	'10yr'
] as const;

export const WINDOW_LABELS: Record<WindowKey, string> = {
	'1mo': '1 mo',
	'3mo': '3 mo',
	'6mo': '6 mo',
	'1yr': '1 yr',
	'3yr': '3 yr',
	'5yr': '5 yr',
	'10yr': '10 yr'
};

export const DEFAULT_WINDOW: WindowKey = '1yr';

// Approximate days per window. The upstream HistoricJoa filter is a date
// range, so we anchor on whole-day granularity. Months are 30 days, years are
// 365 — exact enough for "trailing window of postings" UX.
const WINDOW_DAYS: Record<WindowKey, number> = {
	'1mo': 30,
	'3mo': 90,
	'6mo': 180,
	'1yr': 365,
	'3yr': 365 * 3,
	'5yr': 365 * 5,
	'10yr': 365 * 10
};

export interface PostingHistoryQuery {
	// All fields are optional — they map to the matching HistoricJoa filter.
	// `agencyCode` → `HiringAgencyCodes`
	// `series`     → `PositionSeries`
	// `controlNumber` → `USAJOBSControlNumbers`
	agencyCode?: string;
	series?: string;
	grade?: string;
	state?: string;
	controlNumber?: string;
}

export interface TrimmedRecord {
	control_number: number | null;
	announcement_number: string | null;
	title: string | null;
	agency_code: string | null;
	agency_name: string | null;
	department_code: string | null;
	series: string | null;
	pay_plan: string | null;
	grade_low: string | null;
	grade_high: string | null;
	salary_min: number | null;
	salary_max: number | null;
	open_date: string | null;
	close_date: string | null;
	city: string | null;
	state: string | null;
	hiring_path: string | null;
}

export interface MonthlyBucket {
	month: string; // YYYY-MM
	count: number;
}

export type HistoryStatus = 'ok' | 'unavailable';

export interface HistoryPayload {
	status: HistoryStatus;
	window: WindowKey;
	as_of: string; // ISO date the function used as the upper bound
	start_date: string; // YYYY-MM-DD lower bound passed to HistoricJoa
	end_date: string; // YYYY-MM-DD upper bound passed to HistoricJoa
	total: number;
	truncated: boolean;
	page_cap: number;
	monthly: MonthlyBucket[];
	records: TrimmedRecord[];
	source: 'usajobs:historicjoa';
	retry_after?: number;
	error?: string;
}

export function isWindowKey(value: unknown): value is WindowKey {
	return typeof value === 'string' && (WINDOW_KEYS as readonly string[]).includes(value);
}

export function normalizeWindow(value: unknown): WindowKey {
	return isWindowKey(value) ? value : DEFAULT_WINDOW;
}

// Convert a window key + an "as of" timestamp into the (start, end) date
// strings HistoricJoa expects.
export function windowToDateRange(
	window: WindowKey,
	asOf: Date
): { start: string; end: string } {
	const end = new Date(Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth(), asOf.getUTCDate()));
	const days = WINDOW_DAYS[window];
	const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
	return {
		start: toIsoDate(start),
		end: toIsoDate(end)
	};
}

function toIsoDate(d: Date): string {
	const year = d.getUTCFullYear().toString().padStart(4, '0');
	const month = (d.getUTCMonth() + 1).toString().padStart(2, '0');
	const day = d.getUTCDate().toString().padStart(2, '0');
	return `${year}-${month}-${day}`;
}

// Build the upstream HistoricJoa query string. Per CLAUDE.md the canonical
// HistoricJoa filter names are HiringAgencyCodes / PositionSeries /
// USAJOBSControlNumbers / StartPositionOpenDate / EndPositionOpenDate. We
// always include the date range; everything else is filtered client-side
// from the trimmed response (HistoricJoa has no grade or state filter that
// matches our public-map vocabulary, so we narrow on the way back instead).
export function buildHistoricJoaParams(
	query: PostingHistoryQuery,
	window: WindowKey,
	asOf: Date
): URLSearchParams {
	const params = new URLSearchParams();
	const range = windowToDateRange(window, asOf);
	params.set('StartPositionOpenDate', range.start);
	params.set('EndPositionOpenDate', range.end);
	const agency = clean(query.agencyCode);
	if (agency) params.set('HiringAgencyCodes', agency.toUpperCase());
	const series = clean(query.series);
	if (series) params.set('PositionSeries', series);
	const control = clean(query.controlNumber);
	if (control) params.set('USAJOBSControlNumbers', control);
	return params;
}

// Strip the long-text and unused-by-public-map fields from a raw HistoricJoa
// record. Returns the trimmed shape used both for the timeline buckets and
// the drill-in list.
export function trimRecord(raw: unknown): TrimmedRecord {
	const r = (raw ?? {}) as Record<string, unknown>;
	const locations = Array.isArray(r['positionlocations'])
		? (r['positionlocations'] as Array<Record<string, unknown>>)
		: [];
	const firstLoc = locations[0] ?? {};
	const hiringPaths = Array.isArray(r['hiringpaths'])
		? (r['hiringpaths'] as Array<Record<string, unknown>>)
		: [];
	const firstHiringPath = hiringPaths[0] ?? {};
	const categories = Array.isArray(r['jobcategories'])
		? (r['jobcategories'] as Array<Record<string, unknown>>)
		: [];
	const firstCategory = categories[0] ?? {};
	return {
		control_number: numberOrNull(r['usajobsControlNumber']),
		announcement_number: stringOrNull(r['announcementNumber']),
		title: stringOrNull(r['positionTitle']),
		agency_code: stringOrNull(r['hiringAgencyCode']),
		agency_name: stringOrNull(r['hiringAgencyName']),
		department_code: stringOrNull(r['hiringDepartmentCode']),
		series: stringOrNull(firstCategory['series']),
		pay_plan: stringOrNull(r['payScale']),
		grade_low: stringOrNull(r['minimumGrade']),
		grade_high: stringOrNull(r['maximumGrade']),
		salary_min: numberOrNull(r['minimumSalary']),
		salary_max: numberOrNull(r['maximumSalary']),
		open_date: stringOrNull(r['positionOpenDate']),
		close_date: stringOrNull(r['positionCloseDate']),
		city: stringOrNull(firstLoc['positionLocationCity']),
		state: stringOrNull(firstLoc['positionLocationState']),
		hiring_path: stringOrNull(firstHiringPath['hiringPath'])
	};
}

// Apply public-map-side filters that HistoricJoa cannot apply server-side:
// grade and state. Both are best-effort string equality (case-insensitive).
export function postFilter(records: TrimmedRecord[], query: PostingHistoryQuery): TrimmedRecord[] {
	const grade = clean(query.grade);
	const state = clean(query.state).toUpperCase();
	if (!grade && !state) return records;
	return records.filter((r) => {
		if (grade) {
			const low = clean(r.grade_low);
			const high = clean(r.grade_high);
			if (low !== grade && high !== grade) return false;
		}
		if (state) {
			const recState = clean(r.state).toUpperCase();
			// Match either the postal code (IL) or the full name (Illinois)
			// because HistoricJoa returns the full name in positionLocationState.
			if (recState !== state && stateNameToCode(recState) !== state) return false;
		}
		return true;
	});
}

// Group trimmed records by YYYY-MM of their open date. Records with no open
// date are skipped silently — they cannot be placed on a timeline.
export function bucketByMonth(records: TrimmedRecord[]): MonthlyBucket[] {
	const counts = new Map<string, number>();
	for (const r of records) {
		const open = clean(r.open_date);
		if (open.length < 7) continue;
		const month = open.slice(0, 7);
		counts.set(month, (counts.get(month) ?? 0) + 1);
	}
	return [...counts.entries()]
		.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
		.map(([month, count]) => ({ month, count }));
}

// Stable cache key for `caches.default` / IndexedDB. Includes the window
// because monthly buckets and date ranges differ per window.
export function cacheKey(query: PostingHistoryQuery, window: WindowKey): string {
	const parts: string[] = [`window=${window}`];
	if (query.agencyCode) parts.push(`agency=${query.agencyCode.toUpperCase()}`);
	if (query.series) parts.push(`series=${query.series}`);
	if (query.grade) parts.push(`grade=${query.grade}`);
	if (query.state) parts.push(`state=${query.state.toUpperCase()}`);
	if (query.controlNumber) parts.push(`control=${query.controlNumber}`);
	return parts.join('&');
}

function clean(value: unknown): string {
	return String(value ?? '').trim();
}

function stringOrNull(value: unknown): string | null {
	const s = clean(value);
	return s ? s : null;
}

function numberOrNull(value: unknown): number | null {
	if (value === null || value === undefined || value === '') return null;
	const n = Number(value);
	return Number.isFinite(n) ? n : null;
}

// Minimal full-name → postal-code map for the filter pass. HistoricJoa
// `positionLocationState` is the human name (e.g. "New Mexico"); the public
// map filters carry postal codes ("NM"). We don't need every territory —
// missing ones simply fail the equality check and the row is excluded.
const STATE_NAME_TO_CODE: Record<string, string> = {
	ALABAMA: 'AL',
	ALASKA: 'AK',
	ARIZONA: 'AZ',
	ARKANSAS: 'AR',
	CALIFORNIA: 'CA',
	COLORADO: 'CO',
	CONNECTICUT: 'CT',
	DELAWARE: 'DE',
	'DISTRICT OF COLUMBIA': 'DC',
	FLORIDA: 'FL',
	GEORGIA: 'GA',
	HAWAII: 'HI',
	IDAHO: 'ID',
	ILLINOIS: 'IL',
	INDIANA: 'IN',
	IOWA: 'IA',
	KANSAS: 'KS',
	KENTUCKY: 'KY',
	LOUISIANA: 'LA',
	MAINE: 'ME',
	MARYLAND: 'MD',
	MASSACHUSETTS: 'MA',
	MICHIGAN: 'MI',
	MINNESOTA: 'MN',
	MISSISSIPPI: 'MS',
	MISSOURI: 'MO',
	MONTANA: 'MT',
	NEBRASKA: 'NE',
	NEVADA: 'NV',
	'NEW HAMPSHIRE': 'NH',
	'NEW JERSEY': 'NJ',
	'NEW MEXICO': 'NM',
	'NEW YORK': 'NY',
	'NORTH CAROLINA': 'NC',
	'NORTH DAKOTA': 'ND',
	OHIO: 'OH',
	OKLAHOMA: 'OK',
	OREGON: 'OR',
	PENNSYLVANIA: 'PA',
	'RHODE ISLAND': 'RI',
	'SOUTH CAROLINA': 'SC',
	'SOUTH DAKOTA': 'SD',
	TENNESSEE: 'TN',
	TEXAS: 'TX',
	UTAH: 'UT',
	VERMONT: 'VT',
	VIRGINIA: 'VA',
	WASHINGTON: 'WA',
	'WEST VIRGINIA': 'WV',
	WISCONSIN: 'WI',
	WYOMING: 'WY',
	'PUERTO RICO': 'PR',
	GUAM: 'GU',
	'AMERICAN SAMOA': 'AS',
	'NORTHERN MARIANA ISLANDS': 'MP',
	'VIRGIN ISLANDS': 'VI'
};

function stateNameToCode(name: string): string {
	return STATE_NAME_TO_CODE[name.toUpperCase()] ?? '';
}
