// In-list facet predicates + the row-text matcher used by the rich-mode
// (Browse → List) `JobList` toolbar. Extracted so the predicates can be
// unit-tested without mounting the Svelte component.
//
// Scope reminder: these helpers never touch `mapState.filters`. They are
// purely local narrowing applied after `filterJobDetails(_, mapState.filters)`
// already ran. See PR C of the D.5.28 Browse plan.
//
// TODO(D.5.29): when `mapState.list = { search, sort, facets[] }` lands for
// URL round-trip + saved-searches v2, this module stays — only the call
// sites move from local `$state` into shared store reads.

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
