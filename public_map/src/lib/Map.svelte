<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { GeoJSONSource, Map as MaplibreMap, MapboxGeoJSONFeature, StyleSpecification } from 'mapbox-gl';
	import { configureMapboxRuntime, pickStyle, HAS_MAPBOX_TOKEN } from './basemap';
	import {
		loadClosedJobs,
		loadCounties,
		loadJobs,
		loadLocalities,
		loadManifest,
		loadMetros,
		loadJobDetailsIndex,
		loadStates,
		type FeatureCollection,
		type JobDetails
	} from './data';
	import { filterJobs } from './filters';
	import {
		LAYER_IDS,
		SOURCE_IDS,
		addAllLayers,
		addOrUpdateSource,
		setClosedJobsVisible,
		setChoroplethVisible,
		setPostingHeatVisible,
		setStateFillMetric
	} from './layers';
	import { mapState, type Manifest } from './store.svelte';
	import { METRICS, METRIC_ORDER, type MetricKey } from './metrics';

	let container: HTMLDivElement;
	let map: MaplibreMap | null = null;
	let mounted = false;
	let allStates: FeatureCollection | null = null;
	let allJobs: FeatureCollection | null = null;
	let allClosedJobs: FeatureCollection | null = null;
	let jobDetails: Record<string, JobDetails> = {};
	let addressPinTimer: ReturnType<typeof setTimeout> | null = null;

	const MAXZOOM = 9;
	const MINZOOM = 3;

	onMount(async () => {
		mounted = true;
		const mapboxgl = (await import('mapbox-gl')).default;
		await import('mapbox-gl/dist/mapbox-gl.css');

		configureMapboxRuntime(mapboxgl);

		const style = pickStyle();
		map = new mapboxgl.Map({
			container,
			style: style as string | StyleSpecification,
			center: [-97, 38.5],
			zoom: 4,
			minZoom: MINZOOM,
			maxZoom: MAXZOOM,
			attributionControl: true,
			projection: 'mercator'
		});

		map.addControl(new mapboxgl.NavigationControl({ visualizePitch: false }), 'top-right');
		map.addControl(new mapboxgl.ScaleControl({ unit: 'imperial' }), 'bottom-left');
		map.on('moveend', () => updateViewport());

		map.on('load', async () => {
			if (!map) return;
			try {
				const [states, counties, metros, localities, jobs, closedJobs, details, manifest] = await Promise.all([
					loadStates(),
					loadCounties(),
					loadMetros(),
					loadLocalities(),
					loadJobs(),
					loadClosedJobs(),
					loadJobDetailsIndex(),
					loadManifest()
				]);

				mapState.manifest = manifest as Manifest | null;
				allStates = cloneCollection(states);
				allJobs = jobs;
				allClosedJobs = closedJobs;
				jobDetails = details;
				mapState.totalJobCount = jobs.features.length;

				const filteredJobs = excludeHidden(filterJobs(jobs, mapState.filters, jobDetails));
				const filteredClosedJobs = filterJobs(closedJobs, mapState.filters, jobDetails);
				const displayStates = cloneCollection(allStates);

				// Stamp client-derived `remote_share` onto each state feature so the
				// metric switcher's "remote share" option has data to color.
				deriveRemoteShare(displayStates, filteredJobs);
				// D.5.6: demote any metric whose property is null for ≥50% of states.
				computeMetricDemotion(displayStates);
				mapState.filteredJobCount = filteredJobs.features.length;

				addOrUpdateSource(map, SOURCE_IDS.states, displayStates);
				addOrUpdateSource(map, SOURCE_IDS.counties, counties);
				addOrUpdateSource(map, SOURCE_IDS.metros, metros);
				addOrUpdateSource(map, SOURCE_IDS.localities, localities);
				addOrUpdateSource(map, SOURCE_IDS.jobsHeat, filteredJobs);
				addOrUpdateSource(map, SOURCE_IDS.closedJobs, filteredClosedJobs);
				addOrUpdateSource(map, SOURCE_IDS.addressPin, emptyCollection());
				addOrUpdateSource(map, SOURCE_IDS.jobs, filteredJobs, /* cluster */ true);

				addAllLayers(map, mapState.metric);
				attachClickHandling(map);
				updateViewport();
			} catch (err) {
				console.error('[public_map] data load failed', err);
				mapState.dataError = (err as Error).message;
			}
		});
	});

	$effect(() => {
		// React to metric changes and the on/off shading toggle.
		const m = mapState.metric;
		const shadingOn = mapState.choroplethEnabled;
		const heatOn = mapState.postingHeatEnabled;
		const closedOn = mapState.closedJobsEnabled;
		if (mounted && map && map.isStyleLoaded()) {
			setStateFillMetric(map, m);
			setChoroplethVisible(map, shadingOn);
			setPostingHeatVisible(map, heatOn);
			setClosedJobsVisible(map, closedOn);
		}
	});

	$effect(() => {
		// React to filter changes AND hidden-job set changes.
		const filters = mapState.filters;
		void mapState.hiddenJobIds;
		if (!mounted || !map || !allJobs || !allClosedJobs || !allStates || !map.isStyleLoaded()) return;
		const filteredJobs = excludeHidden(filterJobs(allJobs, filters, jobDetails));
		const filteredClosedJobs = filterJobs(allClosedJobs, filters, jobDetails);
		const displayStates = cloneCollection(allStates);
		deriveRemoteShare(displayStates, filteredJobs);
		mapState.filteredJobCount = filteredJobs.features.length;
		addOrUpdateSource(map, SOURCE_IDS.jobsHeat, filteredJobs);
		addOrUpdateSource(map, SOURCE_IDS.closedJobs, filteredClosedJobs);
		addOrUpdateSource(map, SOURCE_IDS.jobs, filteredJobs, /* cluster */ true);
		addOrUpdateSource(map, SOURCE_IDS.states, displayStates);
		setStateFillMetric(map, mapState.metric);
		if (mapState.selectedFeature?.source === LAYER_IDS.markers) {
			const selectedId = String(mapState.selectedFeature.properties.id ?? '');
			const stillVisible = filteredJobs.features.some(
				(feature) => String(feature.properties?.id ?? '') === selectedId
			);
			if (!stillVisible) {
				mapState.selectedFeature = null;
				mapState.jobStack = null;
			}
		}
	});

	$effect(() => {
		const viewport = mapState.pendingViewport;
		if (!mounted || !map || !viewport) return;
		map.easeTo({ center: viewport.center, zoom: Math.min(viewport.zoom, MAXZOOM), duration: 600 });
		mapState.pendingViewport = null;
	});

	$effect(() => {
		const target = mapState.addressTarget;
		if (!mounted || !map || !target || !map.isStyleLoaded()) return;
		setAddressPin(target);
		map.flyTo({ center: target.center, zoom: Math.min(target.zoom, MAXZOOM), duration: 700, essential: true });
	});

	onDestroy(() => {
		if (addressPinTimer) clearTimeout(addressPinTimer);
		map?.remove();
		map = null;
	});

	function cloneCollection(collection: FeatureCollection): FeatureCollection {
		return {
			type: 'FeatureCollection',
			features: collection.features.map((feature) => ({
				...feature,
				properties: { ...(feature.properties ?? {}) }
			}))
		};
	}

	function excludeHidden(collection: FeatureCollection): FeatureCollection {
		const hiddenIds = mapState.hiddenJobIds;
		if (hiddenIds.size === 0) return collection;
		return {
			...collection,
			features: collection.features.filter(
				(f) => !hiddenIds.has(String((f.properties ?? {}).id ?? ''))
			)
		};
	}

	function computeMetricDemotion(states: FeatureCollection): void {
		const features = states.features;
		if (features.length === 0) return;
		const demoted = new Set<MetricKey>();
		for (const key of METRIC_ORDER) {
			const prop = METRICS[key].property;
			const nullCount = features.filter((f) => (f.properties ?? {})[prop] == null).length;
			if (nullCount / features.length >= 0.5) {
				demoted.add(key);
			}
		}
		mapState.demotedMetrics = demoted;
		// If the active metric just became demoted, turn off choropleth shading.
		if (demoted.has(mapState.metric)) {
			mapState.choroplethEnabled = false;
		}
	}

	function deriveRemoteShare(states: FeatureCollection, jobs: FeatureCollection): void {
		// Aggregate jobs by state: total + remote count.
		const totals = new Map<string, { total: number; remote: number }>();
		for (const f of jobs.features) {
			const props = f.properties ?? {};
			const state = String(props.state ?? '').toUpperCase();
			if (!state) continue;
			const remoteStatus = String(props.remote_status ?? '').toLowerCase();
			const isRemote = remoteStatus.includes('remote');
			const bucket = totals.get(state) ?? { total: 0, remote: 0 };
			bucket.total += 1;
			if (isRemote) bucket.remote += 1;
			totals.set(state, bucket);
		}
		for (const feature of states.features) {
			const props = (feature.properties ??= {});
			const state = String(props.state ?? '').toUpperCase();
			const bucket = totals.get(state);
			props.remote_share = bucket && bucket.total > 0 ? bucket.remote / bucket.total : null;
		}
	}

	function emptyCollection(): FeatureCollection {
		return { type: 'FeatureCollection', features: [] };
	}

	function setAddressPin(target: { center: [number, number]; label: string; provider: string }): void {
		if (!map) return;
		addOrUpdateSource(map, SOURCE_IDS.addressPin, {
			type: 'FeatureCollection',
			features: [
				{
					type: 'Feature',
					geometry: { type: 'Point', coordinates: target.center },
					properties: { label: target.label, provider: target.provider }
				}
			]
		});
		if (addressPinTimer) clearTimeout(addressPinTimer);
		addressPinTimer = setTimeout(() => {
			if (map) addOrUpdateSource(map, SOURCE_IDS.addressPin, emptyCollection());
			mapState.addressTarget = null;
		}, 8000);
	}

	function updateViewport(): void {
		if (!map) return;
		const center = map.getCenter();
		mapState.viewport = {
			center: [Number(center.lng.toFixed(5)), Number(center.lat.toFixed(5))],
			zoom: Number(map.getZoom().toFixed(2))
		};
	}

	function attachClickHandling(m: MaplibreMap): void {
		const layerOrder = [
			LAYER_IDS.clusters,
			LAYER_IDS.markers,
			LAYER_IDS.closedMarkers,
			LAYER_IDS.localitiesFill,
			LAYER_IDS.countiesOutline,
			LAYER_IDS.metrosOutline,
			LAYER_IDS.statesFill
		];

		m.on('click', (e) => {
			for (const layerId of layerOrder) {
				if (!m.getLayer(layerId)) continue;
				if (layerId === LAYER_IDS.closedMarkers && !mapState.closedJobsEnabled) continue;
				const feats = m.queryRenderedFeatures(e.point, { layers: [layerId] });
				if (feats.length === 0) continue;

				const feature = feats[0];
				const props = feature.properties ?? {};
				if (layerId === LAYER_IDS.clusters) {
					zoomIntoCluster(m, feature);
					return;
				}
				if (layerId === LAYER_IDS.markers) {
					openMarkerStack(feature);
					return;
				}
				if (layerId === LAYER_IDS.localitiesFill) {
					openLocalityStack(props);
					fitFocusedFeature(m, layerId, feature);
					return;
				}
				mapState.jobStack = null;
				mapState.selectedFeature = {
					source: layerId,
					label: labelFor(layerId),
					properties: props
				};
				fitFocusedFeature(m, layerId, feature);
				return;
			}
			mapState.selectedFeature = null;
			mapState.jobStack = null;
		});

		for (const id of layerOrder) {
			m.on('mouseenter', id, () => {
				m.getCanvas().style.cursor = 'pointer';
			});
			m.on('mouseleave', id, () => {
				m.getCanvas().style.cursor = '';
			});
		}
	}

	function labelFor(layerId: string): string {
		switch (layerId) {
			case LAYER_IDS.markers:
				return 'Job card';
			case LAYER_IDS.closedMarkers:
				return 'Closed posting';
			case LAYER_IDS.statesFill:
				return 'State';
			case LAYER_IDS.localitiesFill:
				return 'Locality detail';
			case LAYER_IDS.countiesOutline:
				return 'County detail';
			case LAYER_IDS.metrosOutline:
				return 'Metro detail';
			default:
				return layerId;
		}
	}

	function openMarkerStack(feature: MapboxGeoJSONFeature): void {
		const features = markerFeaturesAtSamePoint(feature);
		if (features.length <= 1) {
			mapState.jobStack = null;
			mapState.listView = null;
			mapState.selectedFeature = {
				source: LAYER_IDS.markers,
				label: labelFor(LAYER_IDS.markers),
				properties: feature.properties ?? {}
			};
			return;
		}
		const label = pointStackLabel(features[0].properties);
		mapState.selectedFeature = null;
		mapState.listView = null;
		mapState.jobStack = {
			label,
			selectedIndex: 0,
			items: features
				.map((candidate) => ({ properties: candidate.properties ?? {} }))
				.sort((a, b) => stackSortKey(a.properties).localeCompare(stackSortKey(b.properties)))
		};
	}

	function openLocalityStack(props: Record<string, unknown>): void {
		const code = String(props.code ?? '').trim();
		if (!code) return;
		const name = String(props.name ?? code).trim();
		mapState.selectedFeature = null;
		mapState.jobStack = null;
		mapState.listView = {
			scope: 'locality',
			code,
			label: `${name} (${code})`
		};
	}

	function markerFeaturesAtSamePoint(feature: MapboxGeoJSONFeature): FeatureCollection['features'] {
		const coords = feature.geometry.type === 'Point' ? feature.geometry.coordinates : null;
		if (!coords || !allJobs) return [{ type: 'Feature', geometry: null, properties: feature.properties ?? {} }];
		const filtered = filterJobs(allJobs, mapState.filters, jobDetails);
		const matches = filtered.features.filter((candidate) => {
			if (candidate.geometry?.type !== 'Point') return false;
			const candidateCoords = candidate.geometry.coordinates;
			return sameCoordinate(coords, candidateCoords);
		});
		return matches.length > 0 ? matches : [{ type: 'Feature', geometry: null, properties: feature.properties ?? {} }];
	}

	function sameCoordinate(a: number[], b: number[]): boolean {
		return Math.abs(Number(a[0]) - Number(b[0])) < 0.00001 && Math.abs(Number(a[1]) - Number(b[1])) < 0.00001;
	}

	function pointStackLabel(props: Record<string, unknown> | null): string {
		const city = String(props?.city ?? '').trim();
		const state = String(props?.state ?? '').trim();
		return [city, state].filter(Boolean).join(', ') || 'Selected map point';
	}

	function stackSortKey(props: Record<string, unknown>): string {
		return [
			String(props.close_date ?? '9999-12-31'),
			String(props.agency_code ?? ''),
			String(props.series ?? ''),
			String(props.title ?? '')
		].join('|');
	}

	function openFeatureStack(features: FeatureCollection['features'], label: string): void {
		const items = features
			.map((candidate) => ({ properties: candidate.properties ?? {} }))
			.sort((a, b) => stackSortKey(a.properties).localeCompare(stackSortKey(b.properties)));
		if (items.length <= 1) {
			const item = items[0];
			if (!item) return;
			mapState.jobStack = null;
			mapState.listView = null;
			mapState.selectedFeature = {
				source: LAYER_IDS.markers,
				label: labelFor(LAYER_IDS.markers),
				properties: item.properties
			};
			return;
		}
		mapState.selectedFeature = null;
		mapState.listView = null;
		mapState.jobStack = {
			label,
			selectedIndex: 0,
			items
		};
	}

	function fitFocusedFeature(m: MaplibreMap, layerId: string, feature: MapboxGeoJSONFeature): void {
		const zoomByLayer: Record<string, number> = {
			[LAYER_IDS.statesFill]: 6,
			[LAYER_IDS.localitiesFill]: 7,
			[LAYER_IDS.countiesOutline]: 8,
			[LAYER_IDS.metrosOutline]: 8
		};
		const maxZoom = zoomByLayer[layerId];
		if (!maxZoom) return;
		const bounds = boundsForGeometry(feature.geometry);
		if (!bounds) return;
		const props = feature.properties ?? {};
		mapState.focusedArea = {
			source: layerId,
			label: String(props.name ?? props.state ?? props.code ?? props.fips ?? props.cbsa_code ?? labelFor(layerId))
		};
		m.fitBounds(bounds, { padding: 60, maxZoom, duration: 700 });
	}

	function boundsForGeometry(geometry: GeoJSON.Geometry | null): [[number, number], [number, number]] | null {
		if (!geometry || !('coordinates' in geometry)) return null;
		const points: [number, number][] = [];
		collectCoordinates(geometry.coordinates, points);
		if (points.length === 0) return null;
		let minLng = Infinity;
		let minLat = Infinity;
		let maxLng = -Infinity;
		let maxLat = -Infinity;
		for (const [lng, lat] of points) {
			minLng = Math.min(minLng, lng);
			minLat = Math.min(minLat, lat);
			maxLng = Math.max(maxLng, lng);
			maxLat = Math.max(maxLat, lat);
		}
		return [[minLng, minLat], [maxLng, maxLat]];
	}

	function collectCoordinates(value: unknown, points: [number, number][]): void {
		if (!Array.isArray(value)) return;
		if (typeof value[0] === 'number' && typeof value[1] === 'number') {
			points.push([Number(value[0]), Number(value[1])]);
			return;
		}
		for (const item of value) collectCoordinates(item, points);
	}

	function backToNational(): void {
		if (!map) return;
		mapState.focusedArea = null;
		map.flyTo({ center: [-97, 38.5], zoom: 4, duration: 700, essential: true });
	}

	function zoomIntoCluster(m: MaplibreMap, feature: MapboxGeoJSONFeature): void {
		const source = m.getSource(SOURCE_IDS.jobs);
		const clusterId = feature.properties?.cluster_id;
		if (!source || !('getClusterExpansionZoom' in source) || clusterId === undefined) return;
		const coords = feature.geometry.type === 'Point' ? feature.geometry.coordinates : null;
		if (!coords) return;
		(source as GeoJSONSource).getClusterExpansionZoom(Number(clusterId), (err, zoom) => {
			if (err || zoom === undefined || zoom === null) return;
			openClusterStack(source as GeoJSONSource, Number(clusterId), feature);
			const targetZoom = Math.min(zoom, MAXZOOM);
			const shouldZoom = targetZoom > m.getZoom() + 0.1;
			if (shouldZoom) {
				m.easeTo({ center: coords as [number, number], zoom: targetZoom });
			}
		});
	}

	function openClusterStack(source: GeoJSONSource, clusterId: number, feature: MapboxGeoJSONFeature): void {
		const pointCount = Number(feature.properties?.point_count ?? 100);
		const sourceWithLeaves = source as GeoJSONSource & {
			getClusterLeaves?: (
				clusterId: number,
				limit: number,
				offset: number,
				callback: (err: Error | null, features?: GeoJSON.Feature[]) => void
			) => void;
		};
		if (!sourceWithLeaves.getClusterLeaves) return;
		sourceWithLeaves.getClusterLeaves(clusterId, Math.max(pointCount, 100), 0, (err, leaves) => {
			if (err || !leaves) return;
			const label = clusterStackLabel(leaves, pointCount);
			openFeatureStack(leaves.map((leaf) => ({
				type: 'Feature',
				geometry: leaf.geometry ?? null,
				properties: leaf.properties ?? {}
			})), label);
		});
	}

	function clusterStackLabel(leaves: GeoJSON.Feature[], pointCount: number): string {
		const first = leaves[0]?.properties as Record<string, unknown> | null | undefined;
		const place = pointStackLabel(first ?? null);
		if (place !== 'Selected map point') return place;
		return `${pointCount.toLocaleString()} postings`;
	}
</script>

<div
	class="map-container"
	bind:this={container}
	role="application"
	aria-label="Interactive map of federal job postings across the United States"
></div>

{#if !HAS_MAPBOX_TOKEN}
	<div class="token-banner" role="status">
		Using OpenStreetMap basemap fallback. Set <code>VITE_MAPBOX_TOKEN</code> in
		<code>public_map/.env</code> for the Mapbox dark style.
	</div>
{/if}

{#if mapState.dataError}
	<div class="error-banner" role="alert">
		Couldn't load the data bundle: {mapState.dataError}
	</div>
{/if}

{#if mapState.focusedArea}
	<button type="button" class="back-national" onclick={backToNational}>
		<span>Back to national</span>
		<strong>{mapState.focusedArea.label}</strong>
	</button>
{/if}

<style>
	.map-container {
		position: absolute;
		inset: 0;
	}

	.token-banner,
	.error-banner {
		position: absolute;
		left: 1rem;
		bottom: 2.25rem;
		max-width: 28rem;
		padding: 0.5rem 0.75rem;
		font-size: 12px;
		line-height: 1.4;
		border-radius: 4px;
		background: rgba(14, 23, 38, 0.85);
		color: #cfd9e6;
		border: 1px solid #2a3a52;
		backdrop-filter: blur(4px);
	}
	.error-banner {
		border-color: #8a3a3a;
		color: #f1bcbc;
	}
	code {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		background: rgba(255, 255, 255, 0.05);
		padding: 0 4px;
		border-radius: 2px;
	}
	.back-national {
		position: absolute;
		left: 50%;
		bottom: 6.35rem;
		transform: translateX(-50%);
		z-index: 8;
		appearance: none;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		max-width: min(28rem, calc(100vw - 2rem));
		border: 1px solid #4979b3;
		border-radius: 999px;
		background: rgba(14, 23, 38, 0.94);
		color: #d8e6f3;
		box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
		backdrop-filter: blur(8px);
		cursor: pointer;
		font-size: 12px;
		padding: 0.55rem 0.8rem;
	}
	.back-national strong {
		color: #7bd0f2;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.back-national:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
	}
	@media (max-width: 640px) {
		.back-national {
			bottom: 11rem;
		}
	}
</style>
