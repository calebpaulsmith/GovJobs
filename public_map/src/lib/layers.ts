// Layer + source registration helpers.
//
// All sources point at static GeoJSON in static/data/. We avoid Mapbox vector
// tiles for the polygon layers because the bundle is small (~9 MB gzipped per
// the plan) and serving from Cloudflare's CDN is fine. Marker clustering uses
// Mapbox's built-in cluster machinery on the jobs source.

import type { Map as MaplibreMap, ExpressionSpecification } from 'mapbox-gl';
import type { FeatureCollection } from './data';
import { fillColorExpression, METRICS, type MetricKey } from './metrics';

export const SOURCE_IDS = {
	states: 'states',
	counties: 'counties',
	metros: 'metros',
	localities: 'localities',
	jobs: 'jobs'
} as const;

export const LAYER_IDS = {
	statesFill: 'states-fill',
	statesOutline: 'states-outline',
	countiesOutline: 'counties-outline',
	metrosOutline: 'metros-outline',
	localitiesFill: 'localities-fill',
	localitiesOutline: 'localities-outline',
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

	// 2. Counties outline — visible 7-9.
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
		id: LAYER_IDS.clusters,
		type: 'circle',
		source: SOURCE_IDS.jobs,
		minzoom: 7,
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
			'circle-radius': ['step', ['get', 'point_count'], 12, 25, 18, 100, 26],
			'circle-stroke-color': '#0a0f1a',
			'circle-stroke-width': 1.5,
			'circle-opacity': FADE(7, 9, 0.9)
		}
	});
	map.addLayer({
		id: LAYER_IDS.clusterCount,
		type: 'symbol',
		source: SOURCE_IDS.jobs,
		minzoom: 7,
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

	// 6. Individual markers — also past zoom 7. At higher zoom the cluster
	//    radius shrinks and these reveal naturally.
	map.addLayer({
		id: LAYER_IDS.markers,
		type: 'circle',
		source: SOURCE_IDS.jobs,
		minzoom: 7,
		filter: ['!', ['has', 'point_count']],
		paint: {
			'circle-color': '#7bd0f2',
			'circle-radius': ['interpolate', ['linear'], ['zoom'], 7, 3, 9, 6],
			'circle-stroke-color': '#0a0f1a',
			'circle-stroke-width': 1,
			'circle-opacity': FADE(7, 9, 0.95)
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
