import type { Feature, FeatureCollection, JobDetails } from './data';

export interface JobFilters {
	keyword: string;
	agency: string;
	series: string;
	gradeMin: string;
	gradeMax: string;
	salaryMin: string;
	remote: 'any' | 'remote' | 'hybrid' | 'onsite';
	hiringPath: string;
	payPlan: string;
}

export const DEFAULT_FILTERS: JobFilters = {
	keyword: '',
	agency: '',
	series: '',
	gradeMin: '',
	gradeMax: '',
	salaryMin: '',
	remote: 'any',
	hiringPath: '',
	payPlan: ''
};

export const FILTER_PARAM_KEYS = [
	'q',
	'agency',
	'series',
	'gradeMin',
	'gradeMax',
	'salaryMin',
	'remote',
	'hiringPath',
	'payPlan'
] as const;

type JobDetailsIndex = Record<string, JobDetails>;

type FilterableProps = Record<string, unknown>;

export function hasActiveFilters(filters: JobFilters): boolean {
	return Object.entries(filters).some(([key, value]) => {
		if (key === 'remote') return value !== 'any';
		return String(value ?? '').trim().length > 0;
	});
}

export function activeFilterCount(filters: JobFilters): number {
	return Object.entries(filters).filter(([key, value]) => {
		if (key === 'remote') return value !== 'any';
		return String(value ?? '').trim().length > 0;
	}).length;
}

export function normalizeFilters(input: Partial<JobFilters>): JobFilters {
	const remote = input.remote && ['any', 'remote', 'hybrid', 'onsite'].includes(input.remote)
		? input.remote
		: DEFAULT_FILTERS.remote;
	return {
		keyword: clean(input.keyword),
		agency: clean(input.agency),
		series: clean(input.series),
		gradeMin: clean(input.gradeMin),
		gradeMax: clean(input.gradeMax),
		salaryMin: clean(input.salaryMin),
		remote,
		hiringPath: clean(input.hiringPath),
		payPlan: clean(input.payPlan)
	};
}

export function filtersFromSearchParams(params: URLSearchParams): JobFilters {
	return normalizeFilters({
		keyword: params.get('q') ?? '',
		agency: params.get('agency') ?? '',
		series: params.get('series') ?? '',
		gradeMin: params.get('gradeMin') ?? '',
		gradeMax: params.get('gradeMax') ?? '',
		salaryMin: params.get('salaryMin') ?? '',
		remote: (params.get('remote') as JobFilters['remote'] | null) ?? 'any',
		hiringPath: params.get('hiringPath') ?? '',
		payPlan: params.get('payPlan') ?? ''
	});
}

export function writeFiltersToSearchParams(params: URLSearchParams, filters: JobFilters): void {
	params.delete('q');
	params.delete('agency');
	params.delete('series');
	params.delete('gradeMin');
	params.delete('gradeMax');
	params.delete('salaryMin');
	params.delete('remote');
	params.delete('hiringPath');
	params.delete('payPlan');

	if (filters.keyword) params.set('q', filters.keyword);
	if (filters.agency) params.set('agency', filters.agency);
	if (filters.series) params.set('series', filters.series);
	if (filters.gradeMin) params.set('gradeMin', filters.gradeMin);
	if (filters.gradeMax) params.set('gradeMax', filters.gradeMax);
	if (filters.salaryMin) params.set('salaryMin', filters.salaryMin);
	if (filters.remote !== 'any') params.set('remote', filters.remote);
	if (filters.hiringPath) params.set('hiringPath', filters.hiringPath);
	if (filters.payPlan) params.set('payPlan', filters.payPlan.toUpperCase());
}

export function filterJobs(
	jobs: FeatureCollection,
	filters: JobFilters,
	details: JobDetailsIndex = {}
): FeatureCollection {
	if (!hasActiveFilters(filters)) return jobs;
	return {
		type: 'FeatureCollection',
		features: jobs.features.filter((feature) => matchesJobFeature(feature, filters, details))
	};
}

export function matchesJobFeature(
	feature: Feature,
	filters: JobFilters,
	details: JobDetailsIndex = {}
): boolean {
	const props = feature.properties ?? {};
	const detail = details[String(props.id ?? '')];
	const combined = combineProps(props, detail);

	if (filters.keyword && !containsAnyText(combined, filters.keyword)) return false;
	if (filters.agency && !agencyMatches(combined, filters.agency)) return false;
	if (filters.series && !equalsNormalized(combined.series, filters.series)) return false;
	if (filters.payPlan && !equalsNormalized(combined.pay_plan, filters.payPlan)) return false;
	if (filters.remote !== 'any' && !remoteMatches(combined.remote_status, filters.remote)) return false;
	if (filters.hiringPath && !containsText(combined.hiring_paths, filters.hiringPath)) return false;
	if (filters.salaryMin && !meetsSalaryMinimum(combined.salary_min, filters.salaryMin)) return false;
	if (!gradeRangeOverlaps(combined.grade_low, combined.grade_high, filters.gradeMin, filters.gradeMax)) return false;

	return true;
}

function combineProps(props: FilterableProps, detail: JobDetails | undefined): FilterableProps {
	return {
		...props,
		...(detail ?? {}),
		// Keep marker city/state when detail locations only contains nested rows.
		city: props.city ?? detail?.locations?.[0]?.city,
		state: props.state ?? detail?.locations?.[0]?.state
	};
}

function containsAnyText(props: FilterableProps, needle: string): boolean {
	const haystack = [
		props.title,
		props.agency,
		props.department,
		props.agency_code,
		props.series,
		props.pay_plan,
		props.city,
		props.state,
		props.remote_status,
		props.hiring_paths
	]
		.map((v) => String(v ?? '').toLowerCase())
		.join(' ');
	return haystack.includes(needle.toLowerCase().trim());
}

function agencyMatches(props: FilterableProps, agency: string): boolean {
	const needle = agency.toLowerCase().trim();
	return [props.agency, props.department, props.agency_code]
		.map((v) => String(v ?? '').toLowerCase())
		.some((value) => value.includes(needle));
}

function containsText(value: unknown, needle: string): boolean {
	return String(value ?? '').toLowerCase().includes(needle.toLowerCase().trim());
}

function equalsNormalized(value: unknown, expected: string): boolean {
	return String(value ?? '').trim().toLowerCase() === expected.trim().toLowerCase();
}

function remoteMatches(value: unknown, expected: JobFilters['remote']): boolean {
	const status = String(value ?? '').toLowerCase();
	if (expected === 'remote') return status.includes('remote');
	if (expected === 'hybrid') return status.includes('hybrid');
	if (expected === 'onsite') return status.includes('onsite') || status.includes('no remote');
	return true;
}

function meetsSalaryMinimum(value: unknown, minimum: string): boolean {
	const salary = Number(value);
	const threshold = Number(minimum);
	if (!Number.isFinite(threshold)) return true;
	if (!Number.isFinite(salary)) return false;
	return salary >= threshold;
}

function gradeRangeOverlaps(
	lowValue: unknown,
	highValue: unknown,
	minValue: string,
	maxValue: string
): boolean {
	const filterMin = Number(minValue);
	const filterMax = Number(maxValue);
	if (!Number.isFinite(filterMin) && !Number.isFinite(filterMax)) return true;

	const low = Number(lowValue);
	const high = Number(highValue);
	if (!Number.isFinite(low) && !Number.isFinite(high)) return false;
	const jobLow = Number.isFinite(low) ? low : high;
	const jobHigh = Number.isFinite(high) ? high : low;

	if (Number.isFinite(filterMin) && jobHigh < filterMin) return false;
	if (Number.isFinite(filterMax) && jobLow > filterMax) return false;
	return true;
}

function clean(value: unknown): string {
	return String(value ?? '').trim();
}
