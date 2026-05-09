<script lang="ts">
	import { slide } from 'svelte/transition';
	import { onDestroy, onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { METRIC_ORDER, type MetricKey } from './metrics';
	import { mapState } from './store.svelte';
	import {
		DEFAULT_FILTERS,
		activeFilterCount,
		filtersFromSearchParams,
		writeFiltersToSearchParams,
		type JobFilters
	} from './filters';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import { loadAgencyOptions, type AgencyOption } from './data';

	let expanded = $state(false);
	let hydratedFromUrl = false;
	let replaceTimer: ReturnType<typeof setTimeout> | null = null;
	// Remember whether the user manually opened the panel so we can restore it
	// after a feature panel closes — without overriding their intent.
	let userManuallyExpanded = $state(false);
	let agencyOptions = $state<AgencyOption[]>([]);
	let agencySearch = $state('');
	let agencyValidation = $state('');

	onMount(() => {
		void loadAgencyOptions().then((options) => {
			agencyOptions = options.filter((option) => option.code);
		});
		if (!browser) return;
		const params = new URLSearchParams(window.location.search);
		mapState.filters = filtersFromSearchParams(params);
		const metric = params.get('metric');
		if (metric && METRIC_ORDER.includes(metric as MetricKey)) {
			mapState.metric = metric as MetricKey;
		}
		hydratedFromUrl = true;
		if (activeFilterCount(mapState.filters) > 0) expanded = true;
	});

	// (2026-05-09) Removed: auto-collapse on featureOpen.
	// The previous effect closed the FilterPanel any time
	// `mapState.selectedFeature` or `mapState.listView` became non-null. In
	// practice this fired during normal pan/zoom because Mapbox treats the
	// pinch-to-zoom or scroll-then-click sequence as a polygon click,
	// silently selecting a state polygon and snapping the filter drawer
	// shut. With the always-visible ActiveFilterStrip across the top, the
	// user never loses sight of active filters, so collapse-on-feature-open
	// is no longer needed for visibility. Users close the panel manually.

	$effect(() => {
		if (mapState.savedSearchesOpen && expanded) {
			expanded = false;
			userManuallyExpanded = false;
		}
	});

	function toggleExpanded() {
		expanded = !expanded;
		userManuallyExpanded = expanded;
	}

	$effect(() => {
		const filters = mapState.filters;
		const metric = mapState.metric;
		if (!browser || !hydratedFromUrl) return;
		if (replaceTimer) clearTimeout(replaceTimer);
		replaceTimer = setTimeout(() => {
			const url = new URL(window.location.href);
			writeFiltersToSearchParams(url.searchParams, filters);
			if (metric === 'postings') url.searchParams.delete('metric');
			else url.searchParams.set('metric', metric);
			const next = `${url.pathname}${url.search}${url.hash}`;
			window.history.replaceState({}, '', next);
		}, 250);
	});

	onDestroy(() => {
		if (replaceTimer) clearTimeout(replaceTimer);
	});

	function setFilter<K extends keyof JobFilters>(key: K, value: JobFilters[K]) {
		mapState.filters = { ...mapState.filters, [key]: value };
	}

	function selectedAgencyOptions(): AgencyOption[] {
		const selected = new Set(mapState.filters.agencies);
		return agencyOptions.filter((option) => option.code && selected.has(option.code));
	}

	function filteredAgencyOptions(): AgencyOption[] {
		const selected = new Set(mapState.filters.agencies);
		const query = agencySearch.trim().toLowerCase();
		return agencyOptions
			.filter((option) => option.code && !selected.has(option.code))
			.filter((option) => !query || agencySearchText(option).includes(query))
			.slice(0, 8);
	}

	function agencySearchText(option: AgencyOption): string {
		return [option.code, option.name, option.label, option.department_name, ...(option.aliases ?? [])]
			.map((value) => String(value ?? '').toLowerCase())
			.join(' ');
	}

	function addAgency(option: AgencyOption) {
		if (!option.code || mapState.filters.agencies.includes(option.code)) return;
		setFilter('agencies', [...mapState.filters.agencies, option.code]);
		agencySearch = '';
		agencyValidation = '';
	}

	function removeAgency(code: string) {
		setFilter('agencies', mapState.filters.agencies.filter((agency) => agency !== code));
	}

	function selectAgencyFromSearch() {
		const query = agencySearch.trim();
		if (!query) return;
		const normalized = query.toLowerCase();
		const match = agencyOptions.find((option) => {
			const aliases = option.aliases ?? [];
			return (
				String(option.code ?? '').toLowerCase() === normalized ||
				option.name.toLowerCase() === normalized ||
				aliases.some((alias) => alias.toLowerCase() === normalized)
			);
		}) ?? filteredAgencyOptions()[0];
		if (match) addAgency(match);
		else agencyValidation = 'Choose a listed agency or known alias; free-text agencies do not change results.';
	}

	function resetFilters() {
		mapState.filters = { ...DEFAULT_FILTERS, agencies: [], geographies: [] };
	}

	function removeGeo(geo: string) {
		setFilter('geographies', mapState.filters.geographies.filter((g) => g !== geo));
	}

	function geoLabel(geo: string): string {
		const sep = geo.indexOf(':');
		if (sep === -1) return geo;
		const type = geo.slice(0, sep);
		const code = geo.slice(sep + 1);
		return type === 'state' ? `State: ${code}` : type === 'locality' ? `Locality: ${code}` : geo;
	}
</script>

<section
	class="filters"
	class:expanded
	class:saved-open={mapState.savedSearchesOpen}
	class:address-open={mapState.addressSearchOpen}
	aria-label="Map filters"
	data-layout-slot={slotAttr(LAYOUT_SLOTS.filters)}
>
	<button
		type="button"
		class="toggle"
		aria-expanded={expanded}
		onclick={toggleExpanded}
	>
		<span>Filters</span>
		{#if activeFilterCount(mapState.filters) > 0}
			<strong>{activeFilterCount(mapState.filters)}</strong>
		{/if}
	</button>

	{#if expanded}
		<div class="body" transition:slide={{ duration: 180 }}>
			<label>
				<span>Keyword</span>
				<input
					type="search"
					placeholder="title, agency, city…"
					value={mapState.filters.keyword}
					oninput={(e) => setFilter('keyword', e.currentTarget.value)}
				/>
			</label>

			<div class="agency-picker">
				<span>Agencies</span>
				<div class="chips" aria-label="Selected agencies">
					{#each selectedAgencyOptions() as option (option.code)}
						<button type="button" class="chip" onclick={() => removeAgency(option.code ?? '')}>
							{option.code} · {option.name}
							<strong aria-hidden="true">×</strong>
						</button>
					{/each}
				</div>
				<div class="agency-search">
					<input
						type="search"
						placeholder="Search FEMA, HSCB, DHS…"
						value={agencySearch}
						oninput={(e) => { agencySearch = e.currentTarget.value; agencyValidation = ''; }}
						onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); selectAgencyFromSearch(); } }}
					/>
					<button type="button" onclick={selectAgencyFromSearch}>Add</button>
				</div>
				{#if agencySearch.trim()}
					<div class="agency-results">
						{#each filteredAgencyOptions() as option (option.code)}
							<button type="button" onclick={() => addAgency(option)}>
								<strong>{option.code}</strong>
								<span>{option.name}</span>
								<small>{option.postings.toLocaleString()} postings{option.aliases?.length ? ` · aliases: ${option.aliases.join(', ')}` : ''}</small>
							</button>
						{/each}
					</div>
				{/if}
				{#if agencyValidation}<p class="validation">{agencyValidation}</p>{/if}
			</div>

			{#if mapState.filters.geographies.length > 0}
				<div class="geo-chips">
					<span>Geography scope</span>
					<div class="chips" aria-label="Active geography filters">
						{#each mapState.filters.geographies as geo (geo)}
							<button type="button" class="chip chip-geo" onclick={() => removeGeo(geo)}>
								{geoLabel(geo)}
								<strong aria-hidden="true">×</strong>
							</button>
						{/each}
					</div>
					<p class="geo-hint">Jobs outside these areas are hidden. Add more via the + button on any state or locality.</p>
				</div>
			{/if}

			<div class="row">
				<label>
					<span>Series</span>
					<input
						type="text"
						inputmode="numeric"
						placeholder="0301"
						value={mapState.filters.series}
						oninput={(e) => setFilter('series', e.currentTarget.value)}
					/>
				</label>
			</div>

			<div class="row three">
				<label>
					<span>Grade min</span>
					<input
						type="number"
						min="1"
						max="15"
						value={mapState.filters.gradeMin}
						oninput={(e) => setFilter('gradeMin', e.currentTarget.value)}
					/>
				</label>
				<label>
					<span>Grade max</span>
					<input
						type="number"
						min="1"
						max="15"
						value={mapState.filters.gradeMax}
						oninput={(e) => setFilter('gradeMax', e.currentTarget.value)}
					/>
				</label>
				<label>
					<span>Pay plan</span>
					<input
						type="text"
						placeholder="GS"
						value={mapState.filters.payPlan}
						oninput={(e) => setFilter('payPlan', e.currentTarget.value.toUpperCase())}
					/>
				</label>
			</div>

			<div class="row">
				<label>
					<span>Salary minimum</span>
					<input
						type="number"
						min="0"
						placeholder="90000"
						value={mapState.filters.salaryMin}
						oninput={(e) => setFilter('salaryMin', e.currentTarget.value)}
					/>
				</label>
				<label>
					<span>Remote</span>
					<select
						value={mapState.filters.remote}
						onchange={(e) => setFilter('remote', e.currentTarget.value as JobFilters['remote'])}
					>
						<option value="any">Any</option>
						<option value="remote">Remote</option>
						<option value="hybrid">Hybrid</option>
						<option value="onsite">Onsite</option>
					</select>
				</label>
			</div>

			<label>
				<span>Hiring path</span>
				<input
					type="text"
					placeholder="public, vet, fed-competitive…"
					value={mapState.filters.hiringPath}
					oninput={(e) => setFilter('hiringPath', e.currentTarget.value)}
				/>
			</label>

			<div class="summary" aria-live="polite">
				<span>{mapState.filteredJobCount.toLocaleString()} of {mapState.totalJobCount.toLocaleString()} mapped posting locations shown</span>
				<button type="button" onclick={resetFilters} disabled={activeFilterCount(mapState.filters) === 0}>
					Reset
				</button>
			</div>
		</div>
	{/if}
</section>

<style>
	.filters {
		position: absolute;
		left: 1rem;
		top: 12.45rem;
		z-index: 6;
		width: min(24rem, calc(100vw - 2rem));
		color: #cfd9e6;
		font-size: 12px;
		transition: top 160ms ease;
	}
	.filters.address-open {
		top: 24.5rem;
	}
	.filters.saved-open {
		top: 27rem;
	}
	.filters.saved-open.address-open {
		top: 37rem;
	}
	.toggle,
	.body {
		background: var(--c-panel-blur, rgba(14, 23, 38, 0.94));
		border: 1px solid var(--c-border, #2a3a52);
		backdrop-filter: blur(8px);
		box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
	}
	.toggle {
		appearance: none;
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.65rem 0.8rem;
		border-radius: 8px;
		color: var(--c-text, #e5edf5);
		cursor: pointer;
		font-weight: 600;
	}
	.toggle strong {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.35rem;
		height: 1.35rem;
		border-radius: 999px;
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 11px;
	}
	.body {
		margin-top: 0.45rem;
		padding: 0.85rem;
		border-radius: 10px;
	}
	label,
	.row {
		display: grid;
		gap: 0.35rem;
	}
	.body > label,
	.agency-picker,
	.geo-chips,
	.row {
		margin-bottom: 0.7rem;
	}
	.row {
		grid-template-columns: 1fr 0.7fr;
		gap: 0.65rem;
	}
	.row.three {
		grid-template-columns: repeat(3, 1fr);
	}
	span {
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
	}
	input,
	select {
		width: 100%;
		box-sizing: border-box;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 6px;
		background: var(--c-row-bg, rgba(8, 13, 22, 0.85));
		color: var(--c-text, #e5edf5);
		padding: 0.45rem 0.55rem;
		font: inherit;
	}
	input:focus,
	select:focus,
	.agency-search button:focus-visible,
	.agency-results button:focus-visible,
	.chip:focus-visible,
	.toggle:focus-visible,
	.summary button:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.agency-picker {
		display: grid;
		gap: 0.45rem;
	}
	.geo-chips {
		display: grid;
		gap: 0.45rem;
	}
	.geo-hint {
		margin: 0;
		font-size: 10px;
		color: var(--c-faint, #64748b);
		line-height: 1.4;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
	}
	.chip {
		appearance: none;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 999px;
		background: var(--c-accent-bg-strong, rgba(73, 121, 179, 0.2));
		color: var(--c-text, #e5edf5);
		padding: 0.28rem 0.5rem;
		cursor: pointer;
		font: inherit;
		font-size: 11px;
	}
	.chip-geo {
		border-color: #5e9a4a;
		background: rgba(94, 154, 74, 0.15);
		color: var(--c-text, #e5edf5);
	}
	.chip strong {
		margin-left: 0.35rem;
		color: var(--c-text, #fff);
	}
	.agency-search {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.35rem;
	}
	.agency-search button,
	.agency-results button {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 6px;
		background: var(--c-row-hover, rgba(28, 42, 64, 0.85));
		color: var(--c-text-2, #d8e6f3);
		cursor: pointer;
		font: inherit;
	}
	.agency-search button {
		padding: 0 0.7rem;
	}
	.agency-results {
		display: grid;
		gap: 0.25rem;
		max-height: 10rem;
		overflow: auto;
	}
	.agency-results button {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.1rem 0.45rem;
		text-align: left;
		padding: 0.45rem 0.55rem;
	}
	.agency-results button strong {
		color: var(--c-text, #fff);
	}
	.agency-results button span {
		color: var(--c-text-2, #d8e6f3);
	}
	.agency-results button small {
		grid-column: 2;
		color: var(--c-muted, #94a3b8);
	}
	.validation {
		margin: 0;
		color: #fbbf24;
	}
	.summary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding-top: 0.45rem;
		border-top: 1px solid var(--c-border-subtle, #22344c);
	}
	.summary button {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 999px;
		background: var(--c-row-hover, rgba(28, 42, 64, 0.75));
		color: var(--c-text-2, #cfd9e6);
		padding: 0.35rem 0.7rem;
		cursor: pointer;
	}
	.summary button:disabled {
		cursor: not-allowed;
		opacity: 0.45;
	}
	@media (max-width: 640px) {
		.filters {
			left: 0.5rem;
			top: auto;
			bottom: 6.5rem;
		}
		.filters.saved-open {
			top: auto;
		}
		.filters.address-open,
		.filters.saved-open.address-open {
			top: auto;
		}
		.row,
		.row.three {
			grid-template-columns: 1fr;
		}
	}
</style>
