// Layer + source registration helpers.
//
// All sources point at static GeoJSON in static/data/. We avoid Mapbox vector
// tiles for the polygon layers because the bundle is small (~9 MB gzipped per
// the plan) and serving from Cloudflare's CDN is fine. Marker clustering uses
// Mapbox's built-in cluster machinery on the jobs source.

import type { Map as MaplibreMap, ExpressionSpecification } from 'mapbox-gl';
import type { FeatureCollection } from './data';
import { fillColorExpression, METRICS, type MetricKey } from './metrics';

// `jobsHeat` source + `postingHeat` layer were archived 2026-05-10 to
// public_map/src/lib/_archived/heatmap/. See that folder's README for revival.
export const SOURCE_IDS = {
	states: 'states',
	counties: 'counties',
	metros: 'metros',
	localities: 'localities',
	closedJobs: 'closed-jobs',
	federalProperties: 'federal-properties',
	addressPin: 'address-pin',
	jobs: 'jobs'
} as const;

export const LAYER_IDS = {
	statesFill: 'states-fill',
	statesOutline: 'states-outline',
	countiesOutline: 'counties-outline',
	metrosOutline: 'metros-outline',
	localitiesFill: 'localities-fill',
	localitiesOutline: 'localities-outline',
	closedMarkers: 'closed-job-markers',
	federalProperties: 'federal-properties-markers',
	addressPinHalo: 'address-pin-halo',
	addressPin: 'address-pin',
	clusters: 'job-clusters',
	clusterCount: 'job-cluster-count',
	markers: 'job-markers'
} as const;

const FADE = (zoomIn: number, zoomOut: number, peak = 1, off = 0): ExpressionSpecification =>
	[
		'interpolate',
		['linear'],
		['zoom'],
		zoomIn - 0.5,
		off,
		zoomIn,
		peak,
		zoomOut,
		peak,
		zoomOut + 0.5,
		off
	] as unknown as ExpressionSpecification;

/**
 * Add all sources for the public map. Idempotent: if a source already exists
 * (HMR re-runs in dev), we set its data instead of re-adding.
 */
export function addOrUpdateSource(
	map: MaplibreMap,
	id: string,
	data: FeatureCollection,
	cluster = false
): void {
	const existing = map.getSource(id);
	if (existing && 'setData' in existing && typeof existing.setData === 'function') {
		(existing as { setData: (d: FeatureCollection) => void }).setData(data);
		return;
	}
	map.addSource(id, {
		type: 'geojson',
		data: data as unknown as GeoJSON.FeatureCollection,
		cluster,
		clusterMaxZoom: 8,
		clusterRadius: 40
	});
}

/**
 * Add layers in the order specified by ADR-0017. Mapbox renders layers in
 * insertion order, so this function MUST be called bottom-to-top.
 */
export function addAllLayers(map: MaplibreMap, metricKey: MetricKey): void {
	const metric = METRICS[metricKey];

	// 1. State fill (choropleth) — visible 0-7, fades out 5-7.
	map.addLayer({
		id: LAYER_IDS.statesFill,
		type: 'fill',
		source: SOURCE_IDS.states,
		minzoom: 0,
		maxzoom: 7.5,
		paint: {
			'fill-color': fillColorExpression(metric) as unknown as ExpressionSpecification,
			'fill-opacity': FADE(0, 5, 0.85)
		}
	});
	map.addLayer({
		id: LAYER_IDS.statesOutline,
		type: 'line',
		source: SOURCE_IDS.states,
		minzoom: 0,
		maxzoom: 9,
		paint: {
			'line-color': '#0a0f1a',
			'line-width': 0.6,
			'line-opacity': 0.7
		}
	});

	// (Posting heat surface removed 2026-05-10; see _archived/heatmap/.)

	// 3. Counties outline — visible 7-9.
	map.addLayer({
		id: LAYER_IDS.countiesOutline,
		type: 'line',
		source: SOURCE_IDS.counties,
		minzoom: 7,
		maxzoom: 9,
		paint: {
			'line-color': '#5a6a82',
			'line-width': 0.4,
			'line-opacity': FADE(7, 9, 0.55)
		}
	});

	// 3. Metros (CBSA) outline — visible 7-9.
	map.addLayer({
		id: LAYER_IDS.metrosOutline,
		type: 'line',
		source: SOURCE_IDS.metros,
		minzoom: 7,
		maxzoom: 9,
		paint: {
			'line-color': '#ffb86b',
			'line-width': 1.0,
			'line-opacity': FADE(7, 9, 0.6),
			'line-dasharray': [2, 2]
		}
	});

	// 4. Localities — fill (low alpha) + outline. Visible 5-9.
	map.addLayer({
		id: LAYER_IDS.localitiesFill,
		type: 'fill',
		source: SOURCE_IDS.localities,
		minzoom: 5,
		maxzoom: 9,
		paint: {
			'fill-color': '#7bd0f2',
			'fill-opacity': FADE(5, 9, 0.08)
		}
	});
	map.addLayer({
		id: LAYER_IDS.localitiesOutline,
		type: 'line',
		source: SOURCE_IDS.localities,
		minzoom: 5,
		maxzoom: 9,
		paint: {
			'line-color': '#7bd0f2',
			'line-width': 1.2,
			'line-opacity': FADE(5, 9, 0.7)
		}
	});

	// 5. Marker clusters — visible past zoom 7 per Phase B exit criteria.
	map.addLayer({
		id: LAYER_IDS.closedMarkers,
		type: 'circle',
		source: SOURCE_IDS.closedJobs,
		minzoom: 7,
		filter: ['!', ['has', 'point_count']],
		paint: {
			'circle-color': '#8792a3',
			'circle-radius': ['interpolate', ['linear'], ['zoom'], 7, 2.5, 9, 4],
			'circle-stroke-color': '#1f2937',
			'circle-stroke-width': 0.8,
			'circle-opacity': 0
		}
	});

	// 5b. Federal Real Property Profile (FRPP) buildings — neutral diamonds
	//     visible at zoom >= 6 per ADR-0025. Drawn beneath job markers so
	//     active postings always read on top. Off by default; toggled via
	//     setFederalPropertiesVisible(). Maxzoom lifted to 19 on 2026-05-10
	//     so federal properties remain visible at street level.
	map.addLayer({
		id: LAYER_IDS.federalProperties,
		type: 'circle',
		source: SOURCE_IDS.federalProperties,
		minzoom: 6,
		paint: {
			'circle-color': '#cbd5e1',
			'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 3, 9, 6, 14, 7, 19, 8],
			'circle-stroke-color': '#1f2937',
			'circle-stroke-width': 1,
			'circle-opacity': 0,
			'circle-stroke-opacity': 0
		}
	});

	map.addLayer({
		id: LAYER_IDS.clusters,
		type: 'circle',
		source: SOURCE_IDS.jobs,
		// Clusters disengage at clusterMaxZoom (=8 in addOrUpdateSource); past
		// that the cluster aggregation breaks apart into individual points so
		// no explicit upper bound is needed here.
		minzoom: 3,
		filter: ['has', 'point_count'],
		paint: {
			'circle-color': [
				'step',
				['get', 'point_count'],
				'#3677b3',
				25,
				'#4ea3d6',
				100,
				'#7bd0f2'
			],
			'circle-radius': ['step', ['get', 'point_count'], 12, 2, 14, 5, 16, 10, 18, 25, 22, 100, 26],
			'circle-stroke-color': '#0a0f1a',
			'circle-stroke-width': 1.5,
			'circle-opacity': 0.92
		}
	});
	map.addLayer({
		id: LAYER_IDS.clusterCount,
		type: 'symbol',
		source: SOURCE_IDS.jobs,
		minzoom: 3,
		filter: ['has', 'point_count'],
		layout: {
			'text-field': ['get', 'point_count_abbreviated'],
			'text-size': 12,
			'text-allow-overlap': true
		},
		paint: {
			'text-color': '#0a0f1a',
			'text-halo-color': '#e5edf5',
			'text-halo-width': 0.6
		}
	});

	// 6. Individual (non-clustered) markers. Visible at every zoom so a
	//    narrowly filtered set (e.g. one agency with 24 postings spread
	//    across 50 states) doesn't disappear at low zoom: those points
	//    are too sparse to cluster within 40 px and would otherwise have
	//    nothing to render. Size interpolates so low-zoom dots stay tiny;
	//    explicit stops at 14 / 19 keep them readable at street-level zoom
	//    (cap raised from 9 → 19 on 2026-05-10).
	map.addLayer({
		id: LAYER_IDS.markers,
		type: 'circle',
		source: SOURCE_IDS.jobs,
		minzoom: 3,
		filter: ['!', ['has', 'point_count']],
		paint: {
			'circle-color': '#7bd0f2',
			'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 5, 3, 7, 4, 9, 6, 14, 8, 19, 10],
			'circle-stroke-color': '#0a0f1a',
			'circle-stroke-width': 1,
			'circle-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.85, 9, 0.95]
		}
	});

	map.addLayer({
		id: LAYER_IDS.addressPinHalo,
		type: 'circle',
		source: SOURCE_IDS.addressPin,
		filter: ['!', ['has', 'point_count']],
		paint: {
			'circle-color': '#fbbf24',
			'circle-radius': 15,
			'circle-opacity': 0.18,
			'circle-stroke-color': '#fef3c7',
			'circle-stroke-width': 1.2,
			'circle-stroke-opacity': 0.7
		}
	});
	map.addLayer({
		id: LAYER_IDS.addressPin,
		type: 'circle',
		source: SOURCE_IDS.addressPin,
		filter: ['!', ['has', 'point_count']],
		paint: {
			'circle-color': '#f59e0b',
			'circle-radius': 5,
			'circle-stroke-color': '#111827',
			'circle-stroke-width': 1.5,
			'circle-opacity': 0.95
		}
	});
}

export function setStateFillMetric(map: MaplibreMap, metricKey: MetricKey): void {
	if (!map.getLayer(LAYER_IDS.statesFill)) return;
	const metric = METRICS[metricKey];
	map.setPaintProperty(
		LAYER_IDS.statesFill,
		'fill-color',
		fillColorExpression(metric) as unknown as ExpressionSpecification
	);
}

export function setClosedJobsVisible(map: MaplibreMap, visible: boolean): void {
	if (!map.getLayer(LAYER_IDS.closedMarkers)) return;
	map.setPaintProperty(LAYER_IDS.closedMarkers, 'circle-opacity', visible ? 0.5 : 0);
}

export function setFederalPropertiesVisible(map: MaplibreMap, visible: boolean): void {
	if (!map.getLayer(LAYER_IDS.federalProperties)) return;
	map.setPaintProperty(LAYER_IDS.federalProperties, 'circle-opacity', visible ? 0.85 : 0);
	map.setPaintProperty(
		LAYER_IDS.federalProperties,
		'circle-stroke-opacity',
		visible ? 0.9 : 0
	);
}

/**
 * Toggle the choropleth shading on/off without removing the source. When off
 * we keep state outlines visible (so polygon hit-testing for clicks still
 * works) but drop the fill opacity to zero. The fade-in expression remains
 * intact for when the user re-enables shading.
 */
export function setChoroplethVisible(map: MaplibreMap, visible: boolean): void {
	if (!map.getLayer(LAYER_IDS.statesFill)) return;
	const opacity: ExpressionSpecification | number = visible
		? (FADE(0, 5, 0.85) as ExpressionSpecification)
		: 0;
	map.setPaintProperty(LAYER_IDS.statesFill, 'fill-opacity', opacity as unknown as ExpressionSpecification);
}
