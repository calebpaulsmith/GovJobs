<!--
	/analysis — the Analysis screen (ADR-0039; formerly /localities, ADR-0032).

	Browse is for finding jobs; Analysis is for trends and metrics about a
	place. The user picks a level (Nationwide · State · Locality · Metro ·
	County) and an area within it; AreaAnalysis shows that area's pulse, pay
	vs. cost of living, workforce, urgency, and the click-to-load trend and
	"What to watch" notes — all under the user's non-geographic filters,
	which are shared with Browse. Below, the locality comparison (rollup
	table + mini map, ADR-0032) is kept as its own section.

	Default area on arrival (analysisArea.ts::resolveDefaultArea): the polygon
	the user had tapped in Browse > their geography chip > the Browse map
	center at a level chosen from its zoom > Nationwide. An explicit
	`?area=level:code` in the URL wins (links from Browse's "Analyze this
	area", shared URLs). Switching level keeps the user in the same place via
	the area's anchor point.
-->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { mapState } from '$lib/store.svelte';
	import {
		loadJobs,
		loadJobDetailsIndex,
		loadStates,
		loadLocalities,
		loadMetros,
		loadCounties
	} from '$lib/data';
	import { filtersFromSearchParams, writeFiltersToSearchParams, hasActiveFilters } from '$lib/filters';
	import { writeViewToParams } from '$lib/viewState';
	import { readCurrentView } from '$lib/viewSync';
	import { LAYER_IDS } from '$lib/layers';
	import {
		ANALYSIS_LEVELS,
		NATIONWIDE_AREA,
		areaAtPoint,
		areaToParam,
		areasForLevel,
		findArea,
		parseAreaParam,
		resolveDefaultArea,
		type AnalysisArea,
		type AnalysisLevel,
		type AreaCollections,
		type BrowseContext
	} from '$lib/analysisArea';
	import AreaAnalysis from '$lib/AreaAnalysis.svelte';
	import LocalityRollup from '$lib/LocalityRollup.svelte';
	import LocalityMiniMap from '$lib/LocalityMiniMap.svelte';
	import ActiveFilterStrip from '$lib/ActiveFilterStrip.svelte';
	import FilterSheet from '$lib/FilterSheet.svelte';

	const THEME_KEY = 'fedfinder.public_map.theme.v1';
	let loading = $state(true);

	let cols = $state<AreaCollections>({ states: null, localities: null, metros: null, counties: null });
	let area = $state<AnalysisArea>(NATIONWIDE_AREA);
	// The level the user asked for. Usually area.level, but can differ when
	// the chosen level has nothing at the current spot (e.g. no metro there) —
	// then the picker prompts instead of silently switching levels.
	let level = $state<AnalysisLevel>('nationwide');
	// Where the user "is": carried across level switches.
	let anchor = $state<[number, number] | null>(null);

	// Selection shared by the rollup table and the paired map (row ↔ polygon
	// highlight is two-way). Reassign a fresh Set on each toggle so both
	// consumers re-derive.
	let selected = $state<Set<string>>(new Set());
	function toggleLocality(code: string) {
		const next = new Set(selected);
		if (next.has(code)) next.delete(code);
		else next.add(code);
		selected = next;
	}

	/** Map Browse's selected polygon (if any) onto an analysis level. */
	function browseSelection(): BrowseContext['selected'] {
		const sel = mapState.selectedFeature;
		const p = sel?.properties ?? {};
		switch (sel?.source) {
			case LAYER_IDS.statesFill:
				return p.state ? { level: 'state', code: String(p.state) } : null;
			case LAYER_IDS.localitiesFill:
				return p.code ? { level: 'locality', code: String(p.code) } : null;
			case LAYER_IDS.countiesOutline:
				return p.fips ? { level: 'county', code: String(p.fips) } : null;
			case LAYER_IDS.metrosOutline:
				return p.cbsa_code ? { level: 'metro', code: String(p.cbsa_code) } : null;
			default:
				return null;
		}
	}

	onMount(async () => {
		if (!browser) return;
		const stored = localStorage.getItem(THEME_KEY);
		if (stored === 'light' || stored === 'dark') mapState.theme = stored;
		const params = new URLSearchParams(window.location.search);
		// A direct/shared link carries its filters in the URL; arriving from
		// Browse, the shared store already holds them.
		if (!hasActiveFilters(mapState.filters)) {
			const fromUrl = filtersFromSearchParams(params);
			if (hasActiveFilters(fromUrl)) mapState.filters = fromUrl;
		}
		const [states, localities, metros, counties] = await Promise.all([
			loadStates(),
			loadLocalities(),
			loadMetros(),
			loadCounties()
		]);
		cols = { states, localities, metros, counties };
		const explicit = parseAreaParam(params.get('area'));
		const fromUrl = explicit ? findArea(explicit.level, explicit.code, cols) : null;
		const initial =
			fromUrl ??
			resolveDefaultArea(
				{
					selected: browseSelection(),
					filters: mapState.filters,
					viewport: mapState.viewport?.center
						? { center: mapState.viewport.center as [number, number], zoom: mapState.viewport.zoom }
						: null
				},
				cols
			);
		area = initial;
		level = initial.level;
		anchor = initial.anchor;
		// Mirror Map.svelte's bundle load so the rollup has a corpus even on
		// direct navigation (no map screen visited first).
		if (Object.keys(mapState.allJobDetails).length === 0) {
			const [jobs, details] = await Promise.all([loadJobs(), loadJobDetailsIndex()]);
			mapState.allJobs = jobs;
			mapState.allJobDetails = details;
		}
		loading = false;
	});

	// Keep the address bar shareable: ?area=… plus the filter params. Reads
	// state, writes history only (never mapState).
	$effect(() => {
		const a = area;
		const f = mapState.filters;
		if (!browser || loading) return;
		const url = new URL(window.location.href);
		const params = new URLSearchParams();
		params.set('area', areaToParam(a));
		writeFiltersToSearchParams(params, f);
		url.search = params.toString();
		window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`);
	});

	function chooseLevel(next: AnalysisLevel) {
		level = next;
		if (next === 'nationwide') {
			area = NATIONWIDE_AREA;
			return;
		}
		const hit = areaAtPoint(next, anchor, cols);
		if (hit) area = hit;
	}

	// --- area picker (typeahead) ----------------------------------------------
	const options = $derived(level === 'nationwide' ? [] : areasForLevel(level, cols));
	let query = $state('');
	let pickerOpen = $state(false);
	const matches = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const list = q ? options.filter((o) => o.label.toLowerCase().includes(q) || o.code.toLowerCase() === q) : options;
		return list.slice(0, 40);
	});
	const levelMismatch = $derived(level !== 'nationwide' && area.level !== level);
	function pickArea(code: string) {
		const hit = findArea(level, code, cols);
		if (!hit) return;
		area = hit;
		anchor = hit.anchor;
		query = '';
		pickerOpen = false;
	}
	const LEVEL_WORD: Record<AnalysisLevel, string> = {
		nationwide: 'area',
		state: 'state',
		locality: 'locality pay area',
		metro: 'metro area',
		county: 'county'
	};

	/** Browse link that keeps the user's whole view (filters, map, list). */
	function browseHref(): string {
		const params = new URLSearchParams();
		writeViewToParams(params, readCurrentView());
		const qs = params.toString();
		return qs ? `/browse?${qs}` : '/browse';
	}

	/** "See postings in Browse": scope Browse to this area and go. */
	function viewInBrowse() {
		const a = untrack(() => area);
		if (a.level === 'state' || a.level === 'locality') {
			mapState.filters = { ...mapState.filters, geographies: [`${a.level}:${a.code}`], radii: [] };
		}
		if (a.anchor && a.level !== 'nationwide') {
			const zoom = a.level === 'state' ? 5.5 : a.level === 'county' ? 9 : 7.5;
			mapState.viewport = { ...mapState.viewport, center: a.anchor, zoom };
		}
		mapState.selectedFeature = null;
		mapState.listView = null;
		void goto(browseHref());
	}

	$effect(() => {
		if (!browser) return;
		document.documentElement.dataset.theme = mapState.theme;
		localStorage.setItem(THEME_KEY, mapState.theme);
	});
	function toggleTheme() {
		mapState.theme = mapState.theme === 'dark' ? 'light' : 'dark';
	}
</script>

<svelte:head><title>Analysis · FedFinder</title></svelte:head>

<div class="analysis" data-theme={mapState.theme}>
	<header class="masthead">
		<span class="brand">FedFinder</span>
		<nav class="modes" aria-label="View mode">
			<a class="mode" href={browseHref()} onclick={(e) => { e.preventDefault(); void goto(browseHref()); }}>Browse</a>
			<a class="mode map-only" href="/map">Map only</a>
			<span class="mode active" aria-current="page">Analysis</span>
		</nav>
		<button type="button" class="theme-btn" onclick={toggleTheme} aria-label="Toggle light or dark mode">
			{mapState.theme === 'dark' ? '☀' : '☾'}
		</button>
		<a class="about-link" href="/about">About</a>
	</header>

	<main class="content">
		<div class="intro">
			<h1>Analysis</h1>
			<p>
				Trends and metrics for a place, under your filters. Pick a level and an area — to find and
				apply to jobs, use <a href={browseHref()}>Browse</a>.
			</p>
		</div>

		<div class="filters-row">
			<div class="strip-wrap"><ActiveFilterStrip docked /></div>
			<button type="button" class="edit-btn" onclick={() => (mapState.filterSheetOpen = true)}>Edit filters</button>
		</div>
		{#if mapState.filters.geographies.length > 0 || mapState.filters.radii.length > 0}
			<p class="geo-note">Location filters from Browse are set aside here — the area you pick below sets the location.</p>
		{/if}

		{#if loading}
			<p class="loading" role="status">Loading…</p>
		{:else}
			<section class="picker" aria-label="Area to analyze">
				<div class="levels" role="radiogroup" aria-label="Level">
					{#each ANALYSIS_LEVELS as l (l.key)}
						<button
							type="button"
							role="radio"
							class="level"
							class:on={level === l.key}
							aria-checked={level === l.key}
							onclick={() => chooseLevel(l.key)}
						>
							{l.label}
						</button>
					{/each}
				</div>
				{#if level !== 'nationwide'}
					<div class="area-search">
						<input
							type="search"
							placeholder={levelMismatch ? `Pick a ${LEVEL_WORD[level]}…` : `Change ${LEVEL_WORD[level]} — ${area.label}`}
							aria-label={`Choose a ${LEVEL_WORD[level]}`}
							bind:value={query}
							onfocus={() => (pickerOpen = true)}
							onblur={() => setTimeout(() => (pickerOpen = false), 150)}
						/>
						{#if pickerOpen && matches.length > 0}
							<ul class="matches" role="listbox">
								{#each matches as m (m.code)}
									<li>
										<button type="button" role="option" aria-selected={m.code === area.code} onmousedown={(e) => e.preventDefault()} onclick={() => pickArea(m.code)}>
											{m.label}
										</button>
									</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/if}
			</section>

			{#if levelMismatch}
				<p class="prompt" role="status">
					{area.level === 'nationwide' ? 'This spot' : area.label} isn't inside a {LEVEL_WORD[level]}
					{level === 'locality' ? '(it is in the "Rest of U.S." pay area)' : ''} — pick one above.
				</p>
			{:else}
				{#key areaToParam(area)}
					<AreaAnalysis {area} onViewList={viewInBrowse} />
				{/key}
			{/if}

			<section class="compare">
				<h2>Compare locality pay areas</h2>
				<p class="compare-sub">
					Every locality ranked by postings under your filters. Select rows to see their jobs in Browse.
				</p>
				{#key mapState.theme}
					<LocalityMiniMap {selected} onToggle={toggleLocality} />
				{/key}
				<LocalityRollup {selected} onToggle={toggleLocality} />
			</section>
		{/if}
	</main>

	<FilterSheet />
</div>

<style>
	.analysis {
		display: flex;
		flex-direction: column;
		height: 100dvh;
		background: var(--c-bg, #06111f);
		color: var(--c-text, #e5edf5);
	}
	.masthead {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.5rem 0.75rem;
		background: var(--c-panel, rgba(14, 23, 38, 0.96));
		border-bottom: 1px solid var(--c-border, #2a3a52);
	}
	.brand {
		font-weight: 700;
		font-size: 14px;
	}
	.modes {
		display: inline-flex;
		gap: 0.1rem;
		background: var(--c-bg, #06111f);
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 999px;
		padding: 0.15rem;
	}
	.mode {
		font-size: 11px;
		font-weight: 600;
		padding: 0.28rem 0.6rem;
		border-radius: 999px;
		color: var(--c-text-2, #cfd9e6);
		text-decoration: none;
	}
	.mode.active {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
	}
	/* No Map-only mode on mobile (operator decision 2026-09-24): below the
	   desktop-mosaic breakpoint (layout.ts BROWSE_MOSAIC.minWidth = 1024)
	   Browse is already map-first, so the pill only crowded the masthead.
	   /map itself still resolves for existing links. */
	@media (max-width: 1023.98px) {
		.mode.map-only {
			display: none;
		}
	}
	.theme-btn {
		margin-left: auto;
		appearance: none;
		width: 1.9rem;
		height: 1.9rem;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		cursor: pointer;
		font-size: 13px;
	}
	.theme-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.about-link {
		font-size: 11px;
		font-weight: 600;
		color: var(--c-muted, #94a3b8);
		text-decoration: none;
		white-space: nowrap;
	}
	.about-link:hover {
		color: var(--c-accent, #7bd0f2);
	}
	.content {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		padding: 0.85rem 1rem 1rem;
		max-width: 1100px;
		width: 100%;
		margin: 0 auto;
		box-sizing: border-box;
	}
	.intro h1 {
		margin: 0 0 0.2rem;
		font-size: 20px;
	}
	.intro p {
		margin: 0;
		max-width: 60ch;
		font-size: 13px;
		line-height: 1.5;
		color: var(--c-text-2, #cfd9e6);
	}
	.filters-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.strip-wrap {
		flex: 1;
		min-width: 0;
	}
	.edit-btn {
		appearance: none;
		flex-shrink: 0;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 11px;
		font-weight: 600;
		padding: 0.3rem 0.6rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.edit-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.loading {
		padding: 2rem;
		text-align: center;
		color: var(--c-muted, #94a3b8);
	}
	/* The page scrolls as a whole now (area analysis above the comparison);
	   the rollup keeps its own scroll box at a fixed height. */
	.content :global(.rollup) {
		height: min(70vh, 40rem);
		flex-shrink: 0;
	}
	.intro a {
		color: var(--c-accent, #7bd0f2);
	}
	.geo-note {
		margin: -0.2rem 0 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.picker {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.levels {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}
	.level {
		appearance: none;
		min-height: 2.25rem;
		border: 1px solid var(--c-border, #2a3a52);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.3rem 0.8rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.level.on {
		border-color: var(--c-accent, #7bd0f2);
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
	}
	.area-search {
		position: relative;
		flex: 1;
		min-width: 14rem;
	}
	.area-search input {
		width: 100%;
		box-sizing: border-box;
		min-height: 2.25rem;
		padding: 0.35rem 0.7rem;
		border-radius: 8px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-bg, #06111f);
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 16px; /* ≥16px so iOS Safari doesn't zoom on focus */
	}
	.matches {
		position: absolute;
		z-index: 10;
		left: 0;
		right: 0;
		top: calc(100% + 2px);
		max-height: 16rem;
		overflow-y: auto;
		margin: 0;
		padding: 0.2rem;
		list-style: none;
		background: var(--c-panel, rgba(14, 23, 38, 0.98));
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
	}
	.matches button {
		appearance: none;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 13px;
		padding: 0.45rem 0.55rem;
		border-radius: 6px;
		cursor: pointer;
	}
	.matches button:hover,
	.matches button[aria-selected='true'] {
		background: var(--c-row-hover, rgba(123, 208, 242, 0.1));
	}
	.prompt {
		margin: 0;
		padding: 1rem;
		border: 1px dashed var(--c-border-input, #2c4870);
		border-radius: 10px;
		font-size: 13px;
		color: var(--c-text-2, #cfd9e6);
	}
	.compare {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-top: 0.6rem;
		padding-top: 0.8rem;
		border-top: 1px solid var(--c-border-subtle, #22344c);
	}
	.compare h2 {
		margin: 0;
		font-size: 16px;
	}
	.compare-sub {
		margin: 0;
		font-size: 12px;
		color: var(--c-muted, #94a3b8);
	}
</style>
