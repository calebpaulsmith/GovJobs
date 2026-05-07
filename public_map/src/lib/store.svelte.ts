import { DEFAULT_METRIC, type MetricKey } from './metrics';
import { DEFAULT_FILTERS, type JobFilters } from './filters';

class MapState {
	metric = $state<MetricKey>(DEFAULT_METRIC);
	manifest = $state<Manifest | null>(null);
	dataError = $state<string | null>(null);
	selectedFeature = $state<SelectedFeature | null>(null);
	filters = $state<JobFilters>({ ...DEFAULT_FILTERS });
	filteredJobCount = $state(0);
	totalJobCount = $state(0);
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
}

export interface SelectedFeature {
	source: string;
	label: string;
	properties: Record<string, unknown>;
}

export const mapState = new MapState();
