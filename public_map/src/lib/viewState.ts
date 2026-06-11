// D.5.29 / ADR-0033 — full-view URL codec for shareable links.
//
// One canonical encode/decode for the *entire* Browse view: the filter set
// (delegated to filters.ts), plus the metric, map viewport, theme, the
// selected job, and the rich-list scroll fraction. Both pages hydrate from and
// write to the URL through here, and the "Copy share link" button builds its
// long URL from `viewToParamString`. Keeping it pure (no Svelte, no DOM) makes
// the round-trip unit-testable and identical to what the share Function stores.

import { DEFAULT_METRIC, METRIC_ORDER, type MetricKey } from './metrics';
import {
	filtersFromSearchParams,
	writeFiltersToSearchParams,
	type JobFilters
} from './filters';
import {
	DEFAULT_LIST_TOOLBAR,
	isDefaultListToolbar,
	normalizeListToolbar,
	type ListToolbarState
} from './jobListFacets';

export interface ShareViewport {
	center: [number, number];
	zoom: number;
}

export interface ShareableView {
	filters: JobFilters;
	metric: MetricKey;
	viewport: ShareViewport | null;
	theme: 'light' | 'dark' | null;
	selectedJobId: string | null;
	/** Rich-list scroll position as a 0..1 fraction of scrollable height. */
	scroll: number | null;
	/** In-list toolbar (D.5.28): search / sort / facets. Always present;
	 *  defaults are omitted from the encoded URL. */
	list: ListToolbarState;
}

// View-only param keys (filters own their own keys in filters.ts). Listed so
// `writeViewToParams` can clear them before rewriting, keeping the codec
// idempotent when called against a URL that already carries view state.
export const VIEW_PARAM_KEYS = [
	'metric',
	'center',
	'zoom',
	'theme',
	'selected',
	'scroll',
	// In-list toolbar (D.5.28): lq = in-list search, lsort = sort key,
	// lf = repeated facet keys. Prefixed to keep clear of the global filter
	// keys (q/keyword etc. belong to filters.ts).
	'lq',
	'lsort',
	'lf'
] as const;

function isMetricKey(value: unknown): value is MetricKey {
	return typeof value === 'string' && METRIC_ORDER.includes(value as MetricKey);
}

function parseCenter(raw: string | null): [number, number] | null {
	if (!raw) return null;
	const parts = raw.split(',');
	if (parts.length !== 2) return null;
	const lng = Number(parts[0]);
	const lat = Number(parts[1]);
	if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;
	if (lng < -180 || lng > 180 || lat < -90 || lat > 90) return null;
	return [lng, lat];
}

function clampScroll(value: number): number {
	if (!Number.isFinite(value)) return 0;
	return Math.min(1, Math.max(0, value));
}

/**
 * Write a full view onto `params`, additively over the filter keys. Existing
 * view/filter keys are cleared first so repeated calls are idempotent.
 */
export function writeViewToParams(params: URLSearchParams, view: ShareableView): void {
	writeFiltersToSearchParams(params, view.filters);
	for (const key of VIEW_PARAM_KEYS) params.delete(key);

	// Metric: omit the default so a plain view stays a clean URL.
	if (view.metric && view.metric !== DEFAULT_METRIC) params.set('metric', view.metric);

	if (view.viewport) {
		const [lng, lat] = view.viewport.center;
		if (Number.isFinite(lng) && Number.isFinite(lat)) {
			params.set('center', `${round5(lng)},${round5(lat)}`);
		}
		if (Number.isFinite(view.viewport.zoom)) {
			params.set('zoom', String(round2(view.viewport.zoom)));
		}
	}

	// Theme: dark is the default, so only a light share needs to carry it.
	if (view.theme === 'light') params.set('theme', 'light');

	if (view.selectedJobId) params.set('selected', String(view.selectedJobId));

	if (view.scroll != null && Number.isFinite(view.scroll) && view.scroll > 0) {
		params.set('scroll', String(round3(clampScroll(view.scroll))));
	}

	// In-list toolbar: encode only what differs from the resting state so a
	// plain view stays a clean URL.
	const list = normalizeListToolbar(view.list);
	if (!isDefaultListToolbar(list)) {
		if (list.search) params.set('lq', list.search);
		if (list.sort !== DEFAULT_LIST_TOOLBAR.sort) params.set('lsort', list.sort);
		for (const facet of list.facets) params.append('lf', facet);
	}
}

/** Decode a full view from `params`. Missing keys fall back to sane defaults. */
export function readViewFromParams(params: URLSearchParams): ShareableView {
	const metricRaw = params.get('metric');
	const themeRaw = params.get('theme');
	const center = parseCenter(params.get('center'));
	const zoomRaw = params.get('zoom');
	const zoom = zoomRaw != null && Number.isFinite(Number(zoomRaw)) ? Number(zoomRaw) : null;
	const scrollRaw = params.get('scroll');
	const scroll =
		scrollRaw != null && Number.isFinite(Number(scrollRaw)) ? clampScroll(Number(scrollRaw)) : null;

	return {
		filters: filtersFromSearchParams(params),
		metric: isMetricKey(metricRaw) ? metricRaw : DEFAULT_METRIC,
		viewport: center && zoom != null ? { center, zoom } : null,
		theme: themeRaw === 'light' || themeRaw === 'dark' ? themeRaw : null,
		selectedJobId: params.get('selected') || null,
		scroll,
		list: normalizeListToolbar({
			search: params.get('lq') ?? '',
			sort: params.get('lsort') ?? undefined,
			facets: params.getAll('lf')
		})
	};
}

/** Serialize a view to a query string (no leading `?`). */
export function viewToParamString(view: ShareableView): string {
	const params = new URLSearchParams();
	writeViewToParams(params, view);
	return params.toString();
}

/** Build a full shareable URL string for a view. */
export function shareUrlFromView(
	view: ShareableView,
	opts: { origin: string; path?: string }
): string {
	const path = opts.path ?? '/browse';
	const qs = viewToParamString(view);
	return qs ? `${opts.origin}${path}?${qs}` : `${opts.origin}${path}`;
}

function round5(n: number): number {
	return Number(n.toFixed(5));
}
function round3(n: number): number {
	return Number(n.toFixed(3));
}
function round2(n: number): number {
	return Number(n.toFixed(2));
}
