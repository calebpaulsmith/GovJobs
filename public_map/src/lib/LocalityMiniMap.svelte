<!--
	LocalityMiniMap — the smaller paired map for the D.5.27 Localities screen
	(ADR-0032 §5). It is a SUPPORTING visual, not the centerpiece: it shows the
	locality polygons and reflects the rollup's selection (selected polygons are
	highlighted), and clicking a polygon toggles that locality's selection — so
	row ↔ polygon highlighting is two-way. No choropleth; color is reserved for
	selection state. Reuses the shared basemap config (token / OSM fallback /
	telemetry-off) so it works with or without a Mapbox token. Wrap in
	`{#key theme}` from the parent to re-theme (setStyle would drop custom layers).
-->
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { mapState } from './store.svelte';
	import { loadLocalities } from './data';
	import { pickStyleForTheme, configureMapboxRuntime, HAS_MAPBOX_TOKEN } from './basemap';
	import type { StyleSpecification } from 'mapbox-gl';

	let { selected, onToggle }: { selected: Set<string>; onToggle: (code: string) => void } = $props();

	const SRC = 'localities-mini';
	const FILL = 'localities-mini-fill';
	const SEL = 'localities-mini-selected';
	const LINE = 'localities-mini-line';

	let container: HTMLDivElement | null = null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let map: any = null;
	let ready = $state(false);

	// Highlight filter: only the currently selected localities. `__none__` at
	// rest matches nothing (an empty `in` list errors on some style specs).
	function selectionFilter(codes: Set<string>): unknown {
		const list = codes.size > 0 ? [...codes] : ['__none__'];
		return ['in', ['upcase', ['to-string', ['get', 'code']]], ['literal', list]];
	}

	onMount(() => {
		let destroyed = false;
		(async () => {
			const mapboxgl = (await import('mapbox-gl')).default;
			await import('mapbox-gl/dist/mapbox-gl.css');
			configureMapboxRuntime(mapboxgl);
			if (destroyed || !container) return;
			const fc = await loadLocalities();
			if (destroyed || !container) return;

			map = new mapboxgl.Map({
				container,
				style: pickStyleForTheme(mapState.theme) as string | StyleSpecification,
				center: [-97, 38.5],
				zoom: 2.6,
				attributionControl: false,
				projection: 'mercator'
			});
			map.addControl(
				new mapboxgl.AttributionControl({
					compact: true,
					customAttribution: HAS_MAPBOX_TOKEN
						? '© Mapbox · © OpenStreetMap'
						: '© OpenStreetMap contributors'
				}),
				'bottom-right'
			);

			map.on('load', () => {
				if (destroyed) return;
				map.addSource(SRC, { type: 'geojson', data: fc });
				map.addLayer({
					id: FILL,
					type: 'fill',
					source: SRC,
					paint: { 'fill-color': '#7bd0f2', 'fill-opacity': 0.08 }
				});
				map.addLayer({
					id: SEL,
					type: 'fill',
					source: SRC,
					filter: selectionFilter(selected),
					paint: { 'fill-color': '#7bd0f2', 'fill-opacity': 0.45 }
				});
				map.addLayer({
					id: LINE,
					type: 'line',
					source: SRC,
					paint: { 'line-color': '#4979b3', 'line-width': 0.5, 'line-opacity': 0.6 }
				});
				map.on('click', FILL, (e: { features?: Array<{ properties?: Record<string, unknown> }> }) => {
					const code = String(e.features?.[0]?.properties?.code ?? '').toUpperCase();
					if (code) onToggle(code);
				});
				map.on('mouseenter', FILL, () => (map.getCanvas().style.cursor = 'pointer'));
				map.on('mouseleave', FILL, () => (map.getCanvas().style.cursor = ''));
				ready = true;
			});
		})();
		return () => {
			destroyed = true;
		};
	});

	onDestroy(() => {
		if (map) {
			map.remove();
			map = null;
		}
	});

	// Two-way highlight: when the rollup's selection changes, update the
	// highlight layer's filter. Reads `selected` + `ready`; writes only to the
	// mapbox layer (not to any $state proxy), so the WebKit state_unsafe_mutation
	// rule does not apply.
	$effect(() => {
		const codes = selected;
		if (!ready || !map || !map.getLayer(SEL)) return;
		map.setFilter(SEL, selectionFilter(codes));
	});
</script>

<div class="mini">
	<div class="canvas" bind:this={container}></div>
	<p class="cap">
		Selected localities are highlighted. Click a polygon to add or remove it from your selection.
	</p>
</div>

<style>
	.mini {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.canvas {
		width: 100%;
		height: 220px;
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		overflow: hidden;
	}
	.cap {
		margin: 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
</style>
