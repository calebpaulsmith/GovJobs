import { DEFAULT_METRIC, type MetricKey } from './metrics';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import type { FeatureCollection, JobDetails } from './data';

class MapState {
	metric = $state<MetricKey>(DEFAULT_METRIC);
	// When false, the choropleth state-fill renders at zero opacity. The user
	// toggles this by clicking the currently-active metric pill in the
	// MetricSwitcher (clicking another metric re-enables it).
	choroplethEnabled = $state<boolean>(true);
	// `postingHeatEnabled` removed 2026-05-10; the heat layer was archived to
	// public_map/src/lib/_archived/heatmap/. See that folder's README for revival.
	closedJobsEnabled = $state<boolean>(false);
	// D.5.9: GSA Federal Real Property layer (neutral diamonds at zoom >= 6).
	// Off by default so it doesn't crowd job markers; toggled from the
	// MetricSwitcher.
	federalPropertiesEnabled = $state<boolean>(false);
	manifest = $state<Manifest | null>(null);
	dataError = $state<string | null>(null);
	addressSearchOpen = $state<boolean>(false);
	addressTarget = $state<AddressTarget | null>(null);
	lastAddressTarget = $state<AddressTarget | null>(null);
	savedSearchesOpen = $state<boolean>(false);
	selectedFeature = $state<SelectedFeature | null>(null);
	focusedArea = $state<FocusedArea | null>(null);
	jobStack = $state<JobStackView | null>(null);
	// Shared cache of the full jobs.geojson + jobs_detail index loaded once
	// by `Map.svelte` and reused by every consumer (JobList, BrowseSheet,
	// FeaturePanel). Previously each component fetched and parsed its own
	// copy in its own onMount; the Promise.then write back into the local
	// $state then sometimes failed to propagate to template subscribers
	// (Svelte 5 reactivity glitch with onMount Promise resolution). Storing
	// the loaded data here means consumers read it via `mapState.allJobs`
	// — a regular `$state` read which Svelte does refresh — instead of
	// owning their own load pipeline. `$state.raw` skips the deep proxy so
	// we don't pay the cost of wrapping ~74k feature objects.
	allJobs = $state.raw<FeatureCollection | null>(null);
	allJobDetails = $state.raw<Record<string, JobDetails>>({});
	// When set, the FeaturePanel renders a JobList for the matching scope
	// (e.g. {scope: 'state', state: 'IL'}) instead of the current
	// selectedFeature detail view. Set by clicking "View N postings" inside a
	// roundup popup. Cleared when the user closes the panel or picks a marker.
	listView = $state<ListView | null>(null);
	filters = $state<JobFilters>({ ...DEFAULT_FILTERS, agencies: [] });
	viewport = $state<MapViewport>({ center: [-97, 38.5], zoom: 4 });
	pendingViewport = $state<MapViewport | null>(null);
	filteredJobCount = $state(0);
	totalJobCount = $state(0);
	// D.5.6: metrics auto-demoted to 'wip' because ≥50% of state features are null.
	demotedMetrics = $state<Set<MetricKey>>(new Set());
	// D.5.6: reveal under-construction metrics in the switcher.
	showExperimentalMetrics = $state<boolean>(false);
	// 2026-05-10 operator request: collapse the bottom metric switcher
	// behind a small expand button when not actively recoloring states.
	metricSwitcherOpen = $state<boolean>(false);
	// D.5.19: job IDs hidden by the user; excluded from map/list/heat by default.
	hiddenJobIds = $state<Set<string>>(new Set());
	// D.5.19: job IDs saved by the user.
	savedJobIds = $state<Set<string>>(new Set());
	// D.5.19: profile drawer open.
	profileOpen = $state<boolean>(false);
	// D.5.16: light/dark theme. Initialized from localStorage in +page.svelte.
	theme = $state<'light' | 'dark'>('dark');
	// D.5.17: compensation/COL comparator drawer.
	compareOpen = $state<boolean>(false);
	// Browse map: left-edge filter sheet (shares FilterFields with /map).
	filterSheetOpen = $state<boolean>(false);
	// Browse map: bottom sheet (Here area card ↔ Postings list).
	browseSheetExpanded = $state<boolean>(false);
	browseSheetPage = $state<'here' | 'list'>('list');
	// Browse map: Saved drawer (job lists + saved/hidden/viewed jobs).
	savedDrawerOpen = $state<boolean>(false);
}

export interface MapViewport {
	center: [number, number];
	zoom: number;
	// Visible map bounds at the current camera position. Updated on every
	// moveend by `Map.svelte::updateViewport`. Lets `JobList` filter rows
	// by what's currently visible without each consumer reaching for the
	// mapbox-gl instance directly.
	bounds?: { west: number; south: number; east: number; north: number };
}

export interface AddressTarget extends MapViewport {
	label: string;
	resultType: 'address' | 'postcode' | 'place' | 'region';
	provider: 'mapbox' | 'nominatim' | 'zip_centroid';
}

export interface ListView {
	// `'viewport'` is the browse-mode default — list rows are filtered by
	// `mapState.viewport.bounds`. The other scopes are polygon-membership
	// based and use the `code` field (state postal, OPM locality code, etc.).
	scope: 'state' | 'locality' | 'county' | 'cbsa' | 'viewport';
	// 2-letter state postal, OPM locality code, 5-digit county FIPS, etc.
	// Unused for `viewport` scope (use the empty string).
	code: string;
	// Display label for the panel header.
	label: string;
}

export interface FocusedArea {
	source: string;
	label: string;
}

export interface JobStackItem {
	properties: Record<string, unknown>;
}

export interface JobStackView {
	label: string;
	items: JobStackItem[];
	selectedIndex: number;
}

export interface Manifest {
	schema_version: number;
	generated_at: string;
	reference_year: number;
	feature_count: number;
	job_count: number;
	opm_state_count: number;
	opm_label: string;
	geocoding: { city_matches: number; state_matches: number; unmatched: number; source_matches?: number };
	layers: Record<string, number>;
	data_sources: Record<string, { last_success_at: string | null; row_count: number | null }>;
	posting_coverage?: {
		scope: string;
		live_usajobs_total: number | null;
		job_count: number;
		feature_count: number;
		total_usajobs_jobs_in_db: number;
		total_current_search_jobs_in_db: number;
		total_historic_jobs_in_db: number;
		open_usajobs_jobs_in_db: number;
		open_current_search_jobs_in_db: number;
		open_historic_jobs_in_db: number;
		last_current_import_completed_at: string | null;
		last_current_import_records: number | null;
		last_current_import_pages: number | null;
		last_current_import_filters: Record<string, unknown> | string | null;
	};
}

export interface SelectedFeature {
	source: string;
	label: string;
	properties: Record<string, unknown>;
}

export const mapState = new MapState();
