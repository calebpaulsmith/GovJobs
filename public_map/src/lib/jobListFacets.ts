// In-list facet predicates + the row-text matcher used by the rich-mode
// (Browse → List) `JobList` toolbar. Extracted so the predicates can be
// unit-tested without mounting the Svelte component.
//
// Scope reminder: these helpers never touch `mapState.filters`. They are
// purely local narrowing applied after `filterJobDetails(_, mapState.filters)`
// already ran. See PR C of the D.5.28 Browse plan.
//
// D.5.28: `mapState.list = { search, sort, facets[] }` landed — the toolbar
// state lives in the store and round-trips through share URLs (viewState.ts)
// and saved searches (v3). This module owns the pure model: sort keys, the
// toolbar-state shape + defaults, and the normalizer every entry point
// (URL decode, saved-search load, store writes) funnels through.

import type { JobDetails } from './data';
import { urgencyBadge } from './format';

export type FacetKey = 'gs_family' | 'remote_eligible' | 'closing_7d' | 'hide_viewed';

export interface FacetCtx {
	isViewed: (id: string) => boolean;
}

export interface FacetDef {
	key: FacetKey;
	label: string;
	match: (job: JobDetails, ctx?: FacetCtx) => boolean;
}

// GS-family pay plans: GS, GL, GM, GP, GR, GG, GW — every plan whose code
// starts with "G". Matches the JobCard pill scheme + ADR-0034 GS-family
// rule (only these get the locality-adjusted pay table).
function isGsFamily(job: JobDetails): boolean {
	return String(job.pay_plan ?? '').toUpperCase().startsWith('G');
}

function isRemoteEligible(job: JobDetails): boolean {
	const status = String(job.remote_status ?? '').toLowerCase();
	return status === 'remote' || status === 'hybrid';
}

function closesWithinSevenDays(job: JobDetails): boolean {
	const badge = urgencyBadge(job.close_date ?? null);
	return badge.level === 'critical' || badge.level === 'soon';
}

function notViewed(job: JobDetails, ctx?: FacetCtx): boolean {
	if (!ctx) return true;
	return !ctx.isViewed(String(job.id));
}

// Stable, mock-aligned order. Keep this exported as a frozen array so callers
// can rely on the rendered chip sequence.
export const FACETS: readonly FacetDef[] = Object.freeze<FacetDef[]>([
	{ key: 'gs_family', label: 'GS family', match: isGsFamily },
	{ key: 'remote_eligible', label: 'Remote-eligible', match: isRemoteEligible },
	{ key: 'closing_7d', label: 'Closing ≤ 7d', match: closesWithinSevenDays },
	{ key: 'hide_viewed', label: 'Hide viewed', match: notViewed }
]);

// Case-insensitive substring search across the in-list-visible fields. The
// row may already have its `detail` populated (rich mode always does) and
// can also carry GeoJSON-style `props` (scoped mode), so both shapes are
// merged into a single haystack. Empty / whitespace-only query is always a
// match — callers can therefore short-circuit at the call site or not, the
// behaviour is identical.
export function rowMatchesSearch(
	detail: JobDetails | undefined,
	props: Record<string, unknown>,
	query: string
): boolean {
	const needle = query.trim().toLowerCase();
	if (!needle) return true;

	const parts: string[] = [];
	if (detail) {
		parts.push(
			String(detail.title ?? ''),
			String(detail.agency ?? ''),
			String(detail.agency_code ?? ''),
			String(detail.locality_code ?? '')
		);
		for (const loc of detail.locations ?? []) {
			parts.push(String(loc.city ?? ''));
			parts.push(String(loc.state ?? ''));
			parts.push(String(loc.location_text ?? ''));
		}
	}
	// Scoped-mode rows also carry GeoJSON properties.
	if (props) {
		parts.push(
			String(props.title ?? ''),
			String(props.agency ?? ''),
			String(props.agency_code ?? ''),
			String(props.locality_code ?? ''),
			String(props.city ?? ''),
			String(props.state ?? '')
		);
	}

	const haystack = parts.join(' ').toLowerCase();
	return haystack.includes(needle);
}

// ── In-list toolbar state (D.5.28) ──────────────────────────────────────────

export const LIST_SORT_KEYS = [
	'closing_soon',
	'closing_late',
	'salary_high',
	'salary_low',
	'title',
	'agency',
	'newest',
	'distance'
] as const;

export type ListSortKey = (typeof LIST_SORT_KEYS)[number];

export interface ListToolbarState {
	// Free-text in-list search. Narrows visible rows only — never becomes a
	// global filter chip.
	search: string;
	sort: ListSortKey;
	facets: FacetKey[];
}

export const DEFAULT_LIST_TOOLBAR: ListToolbarState = Object.freeze({
	search: '',
	sort: 'closing_soon',
	facets: []
});

const FACET_KEY_SET = new Set<string>(FACETS.map((f) => f.key));

export function isListSortKey(value: unknown): value is ListSortKey {
	return typeof value === 'string' && (LIST_SORT_KEYS as readonly string[]).includes(value);
}

/**
 * Coerce any untrusted shape (URL params, old saved-search JSON) into a valid
 * ListToolbarState. Unknown sort keys fall back to the default; unknown facet
 * keys are dropped; facets are deduped preserving FACETS order so the chips
 * render deterministically.
 */
export function normalizeListToolbar(input: unknown): ListToolbarState {
	const raw = (input ?? {}) as Partial<Record<keyof ListToolbarState, unknown>>;
	const search = typeof raw.search === 'string' ? raw.search.slice(0, 200) : '';
	const sort = isListSortKey(raw.sort) ? raw.sort : DEFAULT_LIST_TOOLBAR.sort;
	const requested = new Set(
		(Array.isArray(raw.facets) ? raw.facets : []).filter(
			(k): k is FacetKey => typeof k === 'string' && FACET_KEY_SET.has(k)
		)
	);
	const facets = FACETS.map((f) => f.key).filter((k) => requested.has(k));
	return { search, sort, facets };
}

/** True when the toolbar is at its resting state (nothing to encode/save). */
export function isDefaultListToolbar(list: ListToolbarState): boolean {
	return list.search === '' && list.sort === DEFAULT_LIST_TOOLBAR.sort && list.facets.length === 0;
}
