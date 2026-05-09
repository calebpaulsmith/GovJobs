import { DEFAULT_METRIC, type MetricKey } from './metrics';
import { DEFAULT_FILTERS, normalizeFilters, type JobFilters } from './filters';
import type { MapViewport } from './store.svelte';

export const SAVED_SEARCHES_KEY = 'tgp.public_map.saved_searches.v1';
export const SAVED_SEARCHES_SCHEMA_VERSION = 1;

export interface SavedSearch {
	id: string;
	name: string;
	createdAt: string;
	updatedAt: string;
	filters: JobFilters;
	metric: MetricKey;
	viewport?: MapViewport;
}

interface SavedSearchStore {
	schemaVersion: number;
	items: SavedSearch[];
}

export function loadSavedSearches(): SavedSearch[] {
	if (!storageAvailable()) return [];
	const raw = localStorage.getItem(SAVED_SEARCHES_KEY);
	if (!raw) return [];
	try {
		const parsed = JSON.parse(raw) as Partial<SavedSearchStore>;
		if (parsed.schemaVersion !== SAVED_SEARCHES_SCHEMA_VERSION || !Array.isArray(parsed.items)) {
			console.warn('[public_map] dropping incompatible saved-search storage');
			localStorage.removeItem(SAVED_SEARCHES_KEY);
			return [];
		}
		return parsed.items.map(normalizeSavedSearch).filter((item): item is SavedSearch => item !== null);
	} catch (err) {
		console.warn('[public_map] failed to read saved searches:', err);
		return [];
	}
}

export function saveSavedSearches(items: SavedSearch[]): void {
	if (!storageAvailable()) return;
	const payload: SavedSearchStore = {
		schemaVersion: SAVED_SEARCHES_SCHEMA_VERSION,
		items: items.map(normalizeSavedSearch).filter((item): item is SavedSearch => item !== null)
	};
	localStorage.setItem(SAVED_SEARCHES_KEY, JSON.stringify(payload));
}

export function createSavedSearch(input: {
	name: string;
	filters: JobFilters;
	metric: MetricKey;
	viewport?: MapViewport;
}): SavedSearch {
	const now = new Date().toISOString();
	return {
		id: crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`,
		name: cleanName(input.name),
		createdAt: now,
		updatedAt: now,
		filters: cloneFilters(input.filters),
		metric: input.metric,
		viewport: input.viewport ? cloneViewport(input.viewport) : undefined
	};
}

export function renameSavedSearch(item: SavedSearch, name: string): SavedSearch {
	return {
		...item,
		name: cleanName(name),
		updatedAt: new Date().toISOString()
	};
}

export function cloneFilters(filters: JobFilters): JobFilters {
	return {
		...normalizeFilters(filters),
		agencies: [...filters.agencies]
	};
}

function normalizeSavedSearch(item: Partial<SavedSearch>): SavedSearch | null {
	if (!item || !item.id || !item.name) return null;
	const metric = isMetricKey(item.metric) ? item.metric : DEFAULT_METRIC;
	return {
		id: String(item.id),
		name: cleanName(item.name),
		createdAt: String(item.createdAt || item.updatedAt || new Date().toISOString()),
		updatedAt: String(item.updatedAt || item.createdAt || new Date().toISOString()),
		filters: cloneFilters(item.filters ?? DEFAULT_FILTERS),
		metric,
		viewport: item.viewport ? cloneViewport(item.viewport) : undefined
	};
}

function cloneViewport(viewport: MapViewport): MapViewport {
	return {
		center: [Number(viewport.center[0]), Number(viewport.center[1])],
		zoom: Number(viewport.zoom)
	};
}

function cleanName(name: string): string {
	return name.trim().slice(0, 80) || 'Saved search';
}

function isMetricKey(value: unknown): value is MetricKey {
	return typeof value === 'string' && Object.keys(DEFAULT_METRIC_LOOKUP).includes(value);
}

const DEFAULT_METRIC_LOOKUP: Record<MetricKey, true> = {
	postings: true,
	workforce: true,
	accessions: true,
	separations: true,
	remote_share: true,
	pay_vs_col: true
};

function storageAvailable(): boolean {
	return typeof localStorage !== 'undefined';
}
