import { DEFAULT_METRIC, type MetricKey } from './metrics';
import { DEFAULT_FILTERS, type JobFilters } from './filters';

class MapState {
	metric = $state<MetricKey>(DEFAULT_METRIC);
	// When false, the choropleth state-fill renders at zero opacity. The user
	// toggles this by clicking the currently-active metric pill in the
	// MetricSwitcher (clicking another metric re-enables it).
	choroplethEnabled = $state<boolean>(true);
	postingHeatEnabled = $state<boolean>(true);
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
}

export interface MapViewport {
	center: [number, number];
	zoom: number;
}

export interface AddressTarget extends MapViewport {
	label: string;
	resultType: 'address' | 'postcode' | 'place' | 'region';
	provider: 'mapbox' | 'nominatim' | 'zip_centroid';
}

export interface ListView {
	scope: 'state' | 'locality' | 'county' | 'cbsa';
	// 2-letter state postal, OPM locality code, 5-digit county FIPS, etc.
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
