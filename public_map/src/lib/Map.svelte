<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import type {
		GeoJSONSource,
		Map as MaplibreMap,
		MapboxGeoJSONFeature,
		Popup as MapboxPopup,
		StyleSpecification
	} from 'mapbox-gl';
	import {
		assertBasemapInvariants,
		configureMapboxRuntime,
		pickStyleForTheme,
		HAS_MAPBOX_TOKEN
	} from './basemap';
	import {
		loadClosedJobs,
		loadCounties,
		loadFederalProperties,
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
		setFederalPropertiesVisible,
		setStateFillMetric
	} from './layers';
	import { mapState, type Manifest } from './store.svelte';
	import { METRICS, METRIC_ORDER, type MetricKey } from './metrics';

	// `browseMode` is set only when this map is embedded in the /browse map-home
	// view. In that mode every polygon tap (state / locality / county / metro)
	// resolves to a `selectedFeature` so the bottom sheet can show that area's
	// card — including localities, which on /map open a scoped job list instead.
	// Taps do NOT mutate filters here: adding an area to the working list is an
	// explicit "Add this area to my list" button in the sheet (per the operator
	// review — no auto-chips on every tap). On /map (browseMode === false)
	// nothing in this file changes.
	let { browseMode = false }: { browseMode?: boolean } = $props();

	let container: HTMLDivElement;
	let map: MaplibreMap | null = null;
	let mounted = false;
	let allStates: FeatureCollection | null = null;
	let allJobs: FeatureCollection | null = null;
	let allClosedJobs: FeatureCollection | null = null;
	let jobDetails: Record<string, JobDetails> = {};
	let addressPinTimer: ReturnType<typeof setTimeout> | null = null;
	// Single reusable hover tooltip for marker / markersStack / closed / FRPP.
	// Created once per map mount; positioned and shown on mouseenter, hidden
	// on mouseleave, re-positioned on mousemove for stacks that span pixels.
	let hoverPopup: MapboxPopup | null = null;

	// Street-level zoom (~19) per 2026-05-10 operator request. The original
	// hard cap of 9 came from ADR-0017 ("layered, zoom-driven map; no
	// street-level views") but the operator now wants individual marker
	// inspection at street level. The polygon overlays (states / counties /
	// metros / localities) keep their per-layer maxzoom at 9 so they fade out
	// before the basemap goes street-level.
	const MAXZOOM = 19;
	const MINZOOM = 3;

	onMount(async () => {
		mounted = true;
		const mapboxgl = (await import('mapbox-gl')).default;
		await import('mapbox-gl/dist/mapbox-gl.css');

		configureMapboxRuntime(mapboxgl);

		const style = pickStyleForTheme(mapState.theme);
		if (import.meta.env.DEV) {
			// Catches accidental reintroduction of `glyphs:` / symbol layers
			// during local development. In production we trust the unit test.
			assertBasemapInvariants(style);
		}
		map = new mapboxgl.Map({
			container,
			style: style as string | StyleSpecification,
			center: [-97, 38.5],
			zoom: 4,
			minZoom: MINZOOM,
			maxZoom: MAXZOOM,
			// Default attribution control adds "Improve this map" pointing at
			// the Mapbox feedback tool — operator review on 2026-05-10 asked
			// to drop it. We replace the default with our own custom-only
			// attribution so we keep Mapbox + OSM credit (required by both
			// providers' terms) without the feedback link.
			attributionControl: false,
			projection: 'mercator'
		});

		map.addControl(new mapboxgl.NavigationControl({ visualizePitch: false }), 'top-right');
		map.addControl(new mapboxgl.ScaleControl({ unit: 'imperial' }), 'bottom-left');
		map.addControl(
			new mapboxgl.AttributionControl({
				compact: true,
				customAttribution: HAS_MAPBOX_TOKEN
					? '© <a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noopener">Mapbox</a> · © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
					: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
			}),
			'bottom-right'
		);
		map.on('moveend', () => updateViewport());

		// Dev-only: expose the live map instance so the local Playwright
		// touch-event harness in tests/browse-touch.spec.mjs can drive
		// queryRenderedFeatures / project without re-implementing them.
		// Stripped from production by Vite's import.meta.env.DEV gate.
		if (import.meta.env.DEV) {
			(window as unknown as { __ffMap?: typeof map }).__ffMap = map;
		}

		hoverPopup = new mapboxgl.Popup({
			closeButton: false,
			closeOnClick: false,
			offset: 14,
			className: 'ff-hover-popup',
			maxWidth: '260px'
		});

		map.on('load', async () => {
			if (!map) return;
			try {
				const [states, counties, metros, localities, jobs, closedJobs, federalProperties, details, manifest] = await Promise.all([
					loadStates(),
					loadCounties(),
					loadMetros(),
					loadLocalities(),
					loadJobs(),
					loadClosedJobs(),
					loadFederalProperties(),
					loadJobDetailsIndex(),
					loadManifest()
				]);

				mapState.manifest = manifest as Manifest | null;
				allStates = cloneCollection(states);
				allJobs = jobs;
				allClosedJobs = closedJobs;
				jobDetails = details;
				mapState.totalJobCount = jobs.features.length;

				const filteredJobs = stampStackCounts(
					excludeHidden(filterJobs(jobs, mapState.filters, jobDetails))
				);
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
				addOrUpdateSource(map, SOURCE_IDS.closedJobs, filteredClosedJobs);
				addOrUpdateSource(map, SOURCE_IDS.federalProperties, federalProperties);
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
		const closedOn = mapState.closedJobsEnabled;
		const frppOn = mapState.federalPropertiesEnabled;
		if (mounted && map && map.isStyleLoaded()) {
			setStateFillMetric(map, m);
			setChoroplethVisible(map, shadingOn);
			setClosedJobsVisible(map, closedOn);
			setFederalPropertiesVisible(map, frppOn);
		}
	});

	$effect(() => {
		// React to filter changes AND hidden-job set changes.
		const filters = mapState.filters;
		void mapState.hiddenJobIds;
		if (!mounted || !map || !allJobs || !allClosedJobs || !allStates || !map.isStyleLoaded()) return;
		const filteredJobs = stampStackCounts(
			excludeHidden(filterJobs(allJobs, filters, jobDetails))
		);
		const filteredClosedJobs = filterJobs(allClosedJobs, filters, jobDetails);
		const displayStates = cloneCollection(allStates);
		deriveRemoteShare(displayStates, filteredJobs);
		// Pull selectedFeature once via untrack so this effect doesn't also
		// subscribe to it (the body conditionally writes back to the same
		// property; WebKit's Svelte 5 scheduler treats that read-then-write
		// of the same proxy as a `state_unsafe_mutation` and bails the
		// effect graph out, freezing further mapState mutations — that's
		// the operator-reported "after I tap a locality, the sheet won't
		// update and the Filters FAB won't open" symptom).
		const currentSelection = untrack(() => mapState.selectedFeature);
		untrack(() => {
			mapState.filteredJobCount = filteredJobs.features.length;
		});
		addOrUpdateSource(map, SOURCE_IDS.closedJobs, filteredClosedJobs);
		addOrUpdateSource(map, SOURCE_IDS.jobs, filteredJobs, /* cluster */ true);
		addOrUpdateSource(map, SOURCE_IDS.states, displayStates);
		setStateFillMetric(map, mapState.metric);
		if (currentSelection?.source === LAYER_IDS.markers) {
			const selectedId = String(currentSelection.properties.id ?? '');
			const stillVisible = filteredJobs.features.some(
				(feature) => String(feature.properties?.id ?? '') === selectedId
			);
			if (!stillVisible) {
				untrack(() => {
					mapState.selectedFeature = null;
					mapState.jobStack = null;
				});
			}
		}
	});

	$effect(() => {
		const viewport = mapState.pendingViewport;
		if (!mounted || !map || !viewport) return;
		map.easeTo({ center: viewport.center, zoom: Math.min(viewport.zoom, MAXZOOM), duration: 600 });
		// Same state_unsafe_mutation bailout class as above — this effect
		// reads pendingViewport and immediately writes it back to null.
		untrack(() => {
			mapState.pendingViewport = null;
		});
	});

	$effect(() => {
		const target = mapState.addressTarget;
		if (!mounted || !map || !target || !map.isStyleLoaded()) return;
		setAddressPin(target);
		map.flyTo({ center: target.center, zoom: Math.min(target.zoom, MAXZOOM), duration: 700, essential: true });
	});

	onDestroy(() => {
		if (addressPinTimer) clearTimeout(addressPinTimer);
		hoverPopup?.remove();
		hoverPopup = null;
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

	/**
	 * Stamp `stack_count` on each feature: the number of features sharing
	 * its exact (lon, lat). Used by the marker layer split so a coordinate
	 * with N >= 2 stacked jobs renders as a numbered bubble (matching the
	 * cluster aesthetic) instead of a single dot that visually hides the
	 * other N-1 postings. The `openMarkerStack` click handler already
	 * detects same-coord stacks via `markerFeaturesAtSamePoint`; this stamp
	 * is purely a visual hint so the operator can SEE the stack.
	 *
	 * Tolerance: 5 decimal places (~1.1m) — tighter than any of our
	 * geocoders. Matches `sameCoordinate()` which the click router uses.
	 */
	function stampStackCounts(collection: FeatureCollection): FeatureCollection {
		const counts = new Map<string, number>();
		const keyFor = (feature: FeatureCollection['features'][number]): string => {
			const geom = feature.geometry;
			if (!geom || geom.type !== 'Point') return '';
			const [lon, lat] = geom.coordinates;
			if (typeof lon !== 'number' || typeof lat !== 'number') return '';
			return `${lon.toFixed(5)},${lat.toFixed(5)}`;
		};
		for (const feature of collection.features) {
			const key = keyFor(feature);
			if (!key) continue;
			counts.set(key, (counts.get(key) ?? 0) + 1);
		}
		return {
			...collection,
			features: collection.features.map((feature) => {
				const key = keyFor(feature);
				const stack_count = key ? counts.get(key) ?? 1 : 1;
				return {
					...feature,
					properties: { ...(feature.properties ?? {}), stack_count }
				};
			})
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
		const b = map.getBounds();
		mapState.viewport = {
			center: [Number(center.lng.toFixed(5)), Number(center.lat.toFixed(5))],
			zoom: Number(map.getZoom().toFixed(2)),
			bounds: b
				? {
					west: Number(b.getWest().toFixed(5)),
					south: Number(b.getSouth().toFixed(5)),
					east: Number(b.getEast().toFixed(5)),
					north: Number(b.getNorth().toFixed(5))
				}
				: undefined
		};
	}

	function attachClickHandling(m: MaplibreMap): void {
		const layerOrder = [
			LAYER_IDS.clusters,
			// markersStack must come before markers so a click on a stacked
			// bubble routes to openMarkerStack regardless of which layer is
			// "topmost" at the rendering pixel.
			LAYER_IDS.markersStack,
			LAYER_IDS.markers,
			LAYER_IDS.closedMarkers,
			LAYER_IDS.federalProperties,
			LAYER_IDS.localitiesFill,
			LAYER_IDS.countiesOutline,
			LAYER_IDS.metrosOutline,
			LAYER_IDS.statesFill
		];

		m.on('click', (e) => {
			// The hover popup is a DOM overlay positioned at the previously-
			// hovered feature. On touch devices its mouseleave never fires,
			// so it sticks to the last marker and absorbs the NEXT tap before
			// Mapbox can dispatch click to the map. Dismissing it on every
			// click makes the popup transient and keeps it from intercepting
			// subsequent feature selections.
			hoverPopup?.remove();
			for (const layerId of layerOrder) {
				if (!m.getLayer(layerId)) continue;
				if (layerId === LAYER_IDS.closedMarkers && !mapState.closedJobsEnabled) continue;
				if (layerId === LAYER_IDS.federalProperties && !mapState.federalPropertiesEnabled) continue;
				const feats = m.queryRenderedFeatures(e.point, { layers: [layerId] });
				if (feats.length === 0) continue;

				const feature = feats[0];
				const props = feature.properties ?? {};
				if (layerId === LAYER_IDS.clusters) {
					// Cluster tap: zoom in until the cluster's points spread
					// out, and route the BrowseSheet's Postings tab to show
					// jobs in the resulting viewport. Previously the cluster
					// path tried to populate `mapState.jobStack` from inside
					// `getClusterLeaves`' callback so PointJobList could show
					// those exact leaves; writes from inside mapbox-gl's
					// worker actor message handler don't reliably propagate
					// to Svelte 5 template subscribers (verified by
					// `tests/cluster-tap.spec.mjs`), so we sidestep the
					// problem entirely — every job visible after the zoom is
					// inside the viewport, and the viewport-scoped JobList
					// renders them reactively from `mapState.viewport.bounds`.
					if (browseMode) {
						mapState.selectedFeature = null;
						mapState.jobStack = null;
						mapState.listView = {
							scope: 'viewport',
							code: '',
							label: 'this area'
						};
						autoOpenBrowseSheet();
						mapState.browseSheetPage = 'list';
					}
					zoomIntoCluster(m, feature);
					return;
				}
				if (layerId === LAYER_IDS.markers || layerId === LAYER_IDS.markersStack) {
					openMarkerStack(feature);
					autoOpenBrowseSheet();
					return;
				}
				if (layerId === LAYER_IDS.localitiesFill) {
					if (browseMode) {
						// Browse: select the locality (Here tab shows its card)
						// AND scope the Postings tab to jobs in that locality
						// by setting `listView`. Sheet auto-opens so the user
						// can see either tab; we stay on whichever page they
						// were on so they're not yanked off the list mid-flow.
						mapState.jobStack = null;
						mapState.selectedFeature = {
							source: layerId,
							label: labelFor(layerId),
							properties: props
						};
						mapState.listView = listViewForPolygon(layerId, props);
						autoOpenBrowseSheet();
						fitFocusedFeature(m, layerId, feature);
						return;
					}
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
				if (browseMode) {
					mapState.listView = listViewForPolygon(layerId, props);
				}
				autoOpenBrowseSheet();
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

		// Hover tooltips on the marker-bearing layers. Shows "<title> — <city>,
		// <state>" for a single posting and "N jobs at <city>, <state>" for a
		// stacked-coord bubble. The dominant location label wins for stacks
		// where the geocoder collapsed minor variants (~1% of stacks per the
		// 2026-05-10 audit; e.g. "Oklahoma City, OK" vs "Oklahoma County, OK"
		// at the same coord).
		const tooltipLayers = [
			LAYER_IDS.markersStack,
			LAYER_IDS.markers,
			LAYER_IDS.closedMarkers,
			LAYER_IDS.federalProperties
		];
		// Touch devices have no "hover" — mousemove is synthesized from taps
		// but mouseleave never fires when the finger lifts. The popup then
		// sticks to the last-tapped marker and blocks subsequent taps. Skip
		// the hover wiring entirely when the device can't really hover.
		const hasHover =
			typeof window !== 'undefined' &&
			typeof window.matchMedia === 'function' &&
			window.matchMedia('(hover: hover)').matches;
		for (const id of hasHover ? tooltipLayers : []) {
			m.on('mousemove', id, (e) => {
				if (!hoverPopup) return;
				if (id === LAYER_IDS.closedMarkers && !mapState.closedJobsEnabled) return;
				if (id === LAYER_IDS.federalProperties && !mapState.federalPropertiesEnabled) return;
				const feature = e.features?.[0];
				if (!feature) return;
				const coords = feature.geometry?.type === 'Point' ? feature.geometry.coordinates : null;
				if (!coords) return;
				const html = renderTooltipHtml(id, feature);
				if (!html) {
					hoverPopup.remove();
					return;
				}
				hoverPopup.setLngLat(coords as [number, number]).setHTML(html).addTo(m);
			});
			m.on('mouseleave', id, () => {
				hoverPopup?.remove();
			});
		}
	}

	function renderTooltipHtml(layerId: string, feature: MapboxGeoJSONFeature): string {
		const props = feature.properties ?? {};
		if (layerId === LAYER_IDS.closedMarkers) {
			const title = String(props.title ?? '').trim() || 'Closed posting';
			const closeDate = String(props.close_date ?? '').trim();
			return `<div class="ff-tip-title">${escapeHtml(title)}</div>` +
				(closeDate ? `<div class="ff-tip-meta">closed ${escapeHtml(closeDate)}</div>` : '');
		}
		if (layerId === LAYER_IDS.federalProperties) {
			const name = String(props.name ?? '').trim() || 'Federal property';
			const agency = String(props.agency ?? '').trim();
			return `<div class="ff-tip-title">${escapeHtml(name)}</div>` +
				(agency ? `<div class="ff-tip-meta">${escapeHtml(agency)}</div>` : '');
		}
		// markers / markersStack: build label from same-coord siblings so
		// "12 jobs at Chicago, IL" reflects the dominant location text.
		const siblings = markerFeaturesAtSamePoint(feature);
		const stackCount = siblings.length;
		const label = dominantLocationLabel(siblings.length > 0 ? siblings : [{ properties: props }]);
		if (stackCount > 1) {
			return `<div class="ff-tip-title">${stackCount.toLocaleString()} jobs at ${escapeHtml(label || 'this location')}</div>` +
				`<div class="ff-tip-meta">click to list all postings</div>`;
		}
		const title = String(props.title ?? '').trim() || 'Posting';
		return `<div class="ff-tip-title">${escapeHtml(title)}</div>` +
			(label ? `<div class="ff-tip-meta">${escapeHtml(label)}</div>` : '');
	}

	function dominantLocationLabel(items: { properties: Record<string, unknown> | null }[]): string {
		if (items.length === 0) return '';
		const tally = new Map<string, number>();
		for (const item of items) {
			const props = item.properties ?? {};
			const city = String(props.city ?? '').trim();
			const state = String(props.state ?? '').trim();
			const label = [city, state].filter(Boolean).join(', ');
			if (!label) continue;
			tally.set(label, (tally.get(label) ?? 0) + 1);
		}
		let best = '';
		let bestCount = 0;
		for (const [label, count] of tally) {
			if (count > bestCount) {
				best = label;
				bestCount = count;
			}
		}
		return best;
	}

	function escapeHtml(value: string): string {
		return value
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	function labelFor(layerId: string): string {
		switch (layerId) {
			case LAYER_IDS.markers:
			case LAYER_IDS.markersStack:
				return 'Job card';
			case LAYER_IDS.closedMarkers:
				return 'Closed posting';
			case LAYER_IDS.federalProperties:
				return 'Federal property';
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

	// Force the BrowseSheet open and on the Here page imperatively from the
	// click handler. Belt-and-suspenders alongside `BrowseSheet.svelte`'s
	// auto-open $effect: on real iOS Safari we've seen the effect-driven
	// re-open fail when the sheet was MANUALLY MINIMIZED before tapping a
	// different feature (auto-open works on first selection, but a later
	// tap from the collapsed state does not re-expand). Setting the state
	// here makes the open happen in the same synchronous tick as the
	// selection mutation, with no $effect graph between the click and the
	// visible result. No-op when the component is mounted outside browse
	// mode (the desktop /map page).
	// Compute the `mapState.listView` shape that scopes the BrowseSheet's
	// Postings tab to the polygon the user just tapped. Returns null when
	// the polygon doesn't have a usable scoping code (the JobList will
	// fall back to its viewport scope in that case).
	function listViewForPolygon(layerId: string, props: Record<string, unknown>): import('./store.svelte').ListView | null {
		const propStr = (k: string) => String(props[k] ?? '').trim();
		switch (layerId) {
			case LAYER_IDS.statesFill: {
				const code = propStr('state').toUpperCase();
				const name = propStr('name') || code;
				return code ? { scope: 'state', code, label: name } : null;
			}
			case LAYER_IDS.localitiesFill: {
				const code = propStr('code').toUpperCase();
				const name = propStr('name') || code;
				return code ? { scope: 'locality', code, label: name } : null;
			}
			case LAYER_IDS.countiesOutline: {
				const code = propStr('fips') || propStr('state');
				const name = propStr('name') || code;
				return code ? { scope: 'county', code, label: name } : null;
			}
			case LAYER_IDS.metrosOutline: {
				const code = propStr('cbsa_code') || propStr('code');
				const name = propStr('name') || code;
				return code ? { scope: 'cbsa', code, label: name } : null;
			}
			default:
				return null;
		}
	}

	function autoOpenBrowseSheet(): void {
		if (!browseMode) return;
		mapState.browseSheetPage = 'here';
		mapState.browseSheetExpanded = true;
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
			autoOpenBrowseSheet();
			return;
		}
		mapState.selectedFeature = null;
		mapState.listView = null;
		// If a placeholder jobStack was seeded by the cluster click handler
		// (so the template could switch to PointJobList synchronously while
		// the leaves were fetched), mutate its items array in place rather
		// than replacing the whole jobStack object — Svelte 5's deep $state
		// proxy notifies array-mutation subscribers via `.splice`, whereas
		// replacing the outer jobStack object from inside a mapbox-gl actor
		// message-port callback does not reliably propagate to the bound
		// PointJobList component's `stack` prop.
		if (mapState.jobStack && Array.isArray(mapState.jobStack.items)) {
			mapState.jobStack.label = label;
			mapState.jobStack.selectedIndex = 0;
			mapState.jobStack.items.splice(0, mapState.jobStack.items.length, ...items);
		} else {
			mapState.jobStack = {
				label,
				selectedIndex: 0,
				items
			};
		}
		autoOpenBrowseSheet();
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
		// Previously also called `openClusterStack` to populate
		// `mapState.jobStack` with the cluster's leaves. That path was
		// broken by a Svelte 5 / mapbox-gl worker actor interaction
		// (see `tests/cluster-tap.spec.mjs`). The cluster's contents are
		// now surfaced via the viewport-scoped JobList after the zoom —
		// every leaf is, by definition, inside the cluster's expansion
		// bounds, and `mapState.viewport.bounds` updates on `moveend`
		// so the list reactively renders the leaves once the camera
		// lands. The Map.svelte cluster click handler sets
		// `mapState.listView = { scope: 'viewport', … }` before calling
		// this function so the user sees the list as soon as the sheet
		// opens.
		(source as GeoJSONSource).getClusterExpansionZoom(Number(clusterId), (err, zoom) => {
			if (err || zoom === undefined || zoom === null) return;
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

	/* Hover tooltip for marker / markersStack / closed / FRPP. Mapbox renders
	   the popup container outside our component tree, so the rules must be
	   :global to land. Match the dark / light surface tokens used elsewhere
	   so the tooltip reads in either theme. */
	:global(.ff-hover-popup .mapboxgl-popup-content) {
		background: var(--c-panel, rgba(14, 23, 38, 0.96));
		color: var(--c-text-2, #cfd9e6);
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 8px;
		padding: 0.45rem 0.6rem;
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
		font-size: 12px;
		line-height: 1.35;
		pointer-events: none;
	}
	:global(.ff-hover-popup .mapboxgl-popup-tip) {
		display: none;
	}
	:global(.ff-hover-popup .ff-tip-title) {
		color: var(--c-text, #e5edf5);
		font-weight: 600;
	}
	:global(.ff-hover-popup .ff-tip-meta) {
		color: var(--c-muted, #94a3b8);
		margin-top: 0.15rem;
		font-size: 11px;
	}
</style>
