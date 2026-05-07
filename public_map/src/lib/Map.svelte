<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { Map as MaplibreMap, StyleSpecification } from 'mapbox-gl';
	import { mapboxToken, pickStyle, HAS_MAPBOX_TOKEN } from './basemap';
	import {
		loadCounties,
		loadJobs,
		loadLocalities,
		loadManifest,
		loadMetros,
		loadStates,
		type FeatureCollection
	} from './data';
	import {
		LAYER_IDS,
		SOURCE_IDS,
		addAllLayers,
		addOrUpdateSource,
		setStateFillMetric
	} from './layers';
	import { mapState, type Manifest } from './store.svelte';

	let container: HTMLDivElement;
	let map: MaplibreMap | null = null;
	let mounted = false;

	const MAXZOOM = 9;
	const MINZOOM = 3;

	onMount(async () => {
		mounted = true;
		const mapboxgl = (await import('mapbox-gl')).default;
		await import('mapbox-gl/dist/mapbox-gl.css');

		if (HAS_MAPBOX_TOKEN) {
			mapboxgl.accessToken = mapboxToken();
		}

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

		map.on('load', async () => {
			if (!map) return;
			try {
				const [states, counties, metros, localities, jobs, manifest] = await Promise.all([
					loadStates(),
					loadCounties(),
					loadMetros(),
					loadLocalities(),
					loadJobs(),
					loadManifest()
				]);

				mapState.manifest = manifest as Manifest | null;

				// Stamp client-derived `remote_share` onto each state feature so the
				// metric switcher's "remote share" option has data to color.
				deriveRemoteShare(states, jobs);

				addOrUpdateSource(map, SOURCE_IDS.states, states);
				addOrUpdateSource(map, SOURCE_IDS.counties, counties);
				addOrUpdateSource(map, SOURCE_IDS.metros, metros);
				addOrUpdateSource(map, SOURCE_IDS.localities, localities);
				addOrUpdateSource(map, SOURCE_IDS.jobs, jobs, /* cluster */ true);

				addAllLayers(map, mapState.metric);
				attachDebugClick(map);
			} catch (err) {
				console.error('[public_map] data load failed', err);
				mapState.dataError = (err as Error).message;
			}
		});
	});

	$effect(() => {
		// React to metric changes.
		const m = mapState.metric;
		if (mounted && map && map.isStyleLoaded()) {
			setStateFillMetric(map, m);
		}
	});

	onDestroy(() => {
		map?.remove();
		map = null;
	});

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

	function attachDebugClick(m: MaplibreMap): void {
		// Phase B: a single bubble-aware click handler that surfaces whichever
		// feature was on top. Phase C replaces this with proper popups.
		const layerOrder = [
			LAYER_IDS.markers,
			LAYER_IDS.clusters,
			LAYER_IDS.localitiesFill,
			LAYER_IDS.countiesOutline,
			LAYER_IDS.metrosOutline,
			LAYER_IDS.statesFill
		];
		m.on('click', (e) => {
			for (const layerId of layerOrder) {
				if (!m.getLayer(layerId)) continue;
				const feats = m.queryRenderedFeatures(e.point, { layers: [layerId] });
				if (feats.length > 0) {
					mapState.debugFeature = {
						source: layerId,
						properties: feats[0].properties ?? {}
					};
					return;
				}
			}
			mapState.debugFeature = null;
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
</script>

<div class="map-container" bind:this={container}></div>

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
</style>
