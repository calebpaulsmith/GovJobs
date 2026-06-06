// Live, drill-down facet options for the Browse / Map filter dropdowns.
//
// The operator requirement (2026-06-06): the pay-plan, hiring-path, and series
// dropdowns must offer ONLY the values that exist in the currently *filtered*
// results — e.g. with FEMA selected, only the pay plans FEMA actually posts
// should appear. That can only be computed in the browser, because it depends
// on the live combination of active filters; a nightly export is a single
// global list. The job corpus (`jobs_detail`) is already loaded client-side,
// so the tally is cheap.
//
// Drill-down rule: a facet's own selection is ignored when computing that
// facet's options, so picking "GS" does not remove "WG" from the pay-plan list
// (otherwise you could never add a second plan). Every other active filter IS
// applied, so the list narrows as you build up the rest of the query.
//
// Scope: this module never mutates `mapState`; it only reads jobs + filters and
// returns option lists. Matching uses the same `matchesJobDetail` the list and
// map already run, so the offered options and the resulting rows stay in sync.

import type { JobDetails } from './data';
import { matchesJobDetail, parseHiringPaths, type JobFilters } from './filters';

export interface FacetOption {
	value: string;
	label: string;
	// Secondary line under the label (code, department, etc.).
	sub?: string;
	// Postings carrying this value within the current narrowed result set.
	count: number;
	// Extra text folded into the dropdown search (aliases, codes).
	keywords?: string;
}

// Friendly names for the common federal pay plans. Presence in a dropdown is
// driven by the data; this map only makes the codes readable. Unknown codes
// fall back to the raw code so a newly-seen plan is never hidden.
export const PAY_PLAN_LABELS: Record<string, string> = {
	GS: 'General Schedule',
	GM: 'GS — Supervisory/Managerial (GM)',
	GL: 'GS — Law Enforcement (GL)',
	GP: 'GS — Physician/Dentist (GP)',
	GR: 'GS — Other (GR)',
	GG: 'Grades Similar to GS (GG)',
	GW: 'GS — Other (GW)',
	WG: 'Wage Grade — Worker (WG)',
	WL: 'Wage Grade — Leader (WL)',
	WS: 'Wage Grade — Supervisor (WS)',
	WD: 'Wage Grade — Production (WD)',
	WN: 'Wage Grade (WN)',
	NF: 'Nonappropriated Fund — Pay Band (NF)',
	NA: 'Nonappropriated Fund — Wage (NA)',
	NL: 'Nonappropriated Fund — Leader (NL)',
	NS: 'Nonappropriated Fund — Supervisor (NS)',
	CY: 'Child & Youth (CY)',
	VN: 'VA — Nurse (VN)',
	VM: 'VA — Physician/Dentist (VM)',
	VP: 'VA — Podiatrist/Optometrist (VP)',
	VH: 'VA — Hybrid Title 38 (VH)',
	AD: 'Administratively Determined (AD)',
	ES: 'Senior Executive Service (ES)',
	SL: 'Senior Level (SL)',
	ST: 'Scientific & Professional (ST)',
	EX: 'Executive Schedule (EX)',
	NH: 'AcqDemo — Business/Technical (NH)',
	NJ: 'AcqDemo — Technical Support (NJ)',
	NK: 'AcqDemo — Administrative Support (NK)',
	SV: 'TSA — Core Compensation (SV)',
	AT: 'FAA — Air Traffic (AT)',
	FV: 'FAA — Core Compensation (FV)',
	FG: 'FBI — General Schedule (FG)',
	FP: 'Foreign Service — Specialist (FP)',
	FO: 'Foreign Service — Officer (FO)',
	IA: 'Defense Intelligence (IA)'
};

// USAJOBS hiring-path authority codes -> human labels.
export const HIRING_PATH_LABELS: Record<string, string> = {
	public: 'Open to the public',
	'fed-competitive': 'Federal employees — Competitive service',
	'fed-excepted': 'Federal employees — Excepted service',
	'fed-internal-search': 'Internal to an agency',
	'fed-transition': 'Career transition (CTAP/ICTAP)',
	vet: 'Veterans',
	nguard: 'National Guard & Reserves',
	mspouse: 'Military spouses',
	disability: 'Individuals with disabilities',
	land: 'Land & base management',
	overseas: 'Family of overseas employees',
	peace: 'Peace Corps & AmeriCorps VISTA',
	'special-authorities': 'Special authorities',
	ses: 'Senior Executives',
	student: 'Students',
	graduates: 'Recent graduates',
	native: 'Native Americans'
};

export function payPlanLabel(code: string): string {
	const upper = String(code ?? '').trim().toUpperCase();
	return PAY_PLAN_LABELS[upper] ?? upper;
}

export function hiringPathLabel(code: string): string {
	const lower = String(code ?? '').trim().toLowerCase();
	return HIRING_PATH_LABELS[lower] ?? humanizeCode(lower);
}

// Fallback presentation for an unmapped hiring-path code: "fed-internal-search"
// -> "Fed internal search". Keeps an unexpected code legible without hiding it.
function humanizeCode(code: string): string {
	if (!code) return code;
	const spaced = code.replace(/[-_]+/g, ' ').trim();
	return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

type MultiFacetKey = 'series' | 'payPlans' | 'hiringPaths';

// Clone the filters with the target facet's own selection cleared, so the
// dropdown shows every value still reachable under the OTHER active filters.
function filtersIgnoring(filters: JobFilters, facet: MultiFacetKey): JobFilters {
	return { ...filters, [facet]: [] };
}

function narrowedJobs(jobs: JobDetails[], filters: JobFilters, facet: MultiFacetKey): JobDetails[] {
	const scoped = filtersIgnoring(filters, facet);
	return jobs.filter((job) => matchesJobDetail(job, scoped));
}

// Sort by count desc, then by value asc for a stable, predictable order.
function sortOptions(options: FacetOption[]): FacetOption[] {
	return options.sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

export function payPlanFacet(jobs: JobDetails[], filters: JobFilters): FacetOption[] {
	const counts = new Map<string, number>();
	for (const job of narrowedJobs(jobs, filters, 'payPlans')) {
		const code = String(job.pay_plan ?? '').trim().toUpperCase();
		if (!code) continue;
		counts.set(code, (counts.get(code) ?? 0) + 1);
	}
	const options: FacetOption[] = [];
	for (const [code, count] of counts) {
		options.push({ value: code, label: payPlanLabel(code), sub: code, count, keywords: code });
	}
	return sortOptions(options);
}

export function hiringPathFacet(jobs: JobDetails[], filters: JobFilters): FacetOption[] {
	const counts = new Map<string, number>();
	for (const job of narrowedJobs(jobs, filters, 'hiringPaths')) {
		for (const code of new Set(parseHiringPaths(job.hiring_paths))) {
			counts.set(code, (counts.get(code) ?? 0) + 1);
		}
	}
	const options: FacetOption[] = [];
	for (const [code, count] of counts) {
		options.push({ value: code, label: hiringPathLabel(code), sub: code, count, keywords: code });
	}
	return sortOptions(options);
}

export function seriesFacet(
	jobs: JobDetails[],
	filters: JobFilters,
	labels: Record<string, string> = {}
): FacetOption[] {
	const counts = new Map<string, number>();
	for (const job of narrowedJobs(jobs, filters, 'series')) {
		const code = String(job.series ?? '').trim();
		if (!code) continue;
		counts.set(code, (counts.get(code) ?? 0) + 1);
	}
	const options: FacetOption[] = [];
	for (const [code, count] of counts) {
		const title = labels[code];
		// Many series carry only the bare code as their "title" in series.json;
		// don't repeat it as a redundant label.
		const label = title && title !== code ? `${code} — ${title}` : code;
		options.push({ value: code, label, sub: title && title !== code ? title : undefined, count, keywords: `${code} ${title ?? ''}` });
	}
	return sortOptions(options);
}
