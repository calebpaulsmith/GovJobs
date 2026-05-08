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

	let expanded = $state(false);
	let hydratedFromUrl = false;
	let replaceTimer: ReturnType<typeof setTimeout> | null = null;
	// Remember whether the user manually opened the panel so we can restore it
	// after a feature panel closes — without overriding their intent.
	let userManuallyExpanded = $state(false);

	onMount(() => {
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

	// Auto-collapse when a feature panel opens so the two don't fight for
	// horizontal real estate on narrower viewports. The user can re-expand
	// from the toggle at any time; doing so flips userManuallyExpanded so
	// closing the feature panel later doesn't reopen the filters again.
	$effect(() => {
		const featureOpen = mapState.selectedFeature !== null || mapState.listView !== null;
		if (featureOpen && expanded) {
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

	function resetFilters() {
		mapState.filters = { ...DEFAULT_FILTERS };
	}
</script>

<section
	class="filters"
	class:expanded
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

			<div class="row">
				<label>
					<span>Agency</span>
					<input
						type="text"
						placeholder="FEMA or HSCB"
						value={mapState.filters.agency}
						oninput={(e) => setFilter('agency', e.currentTarget.value)}
					/>
				</label>
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
		top: 10.9rem;
		z-index: 6;
		width: min(24rem, calc(100vw - 2rem));
		color: #cfd9e6;
		font-size: 12px;
	}
	.toggle,
	.body {
		background: rgba(14, 23, 38, 0.94);
		border: 1px solid #2a3a52;
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
		color: #e5edf5;
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
		background: #4979b3;
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
		color: #94a3b8;
		font-size: 11px;
	}
	input,
	select {
		width: 100%;
		box-sizing: border-box;
		border: 1px solid #2c4870;
		border-radius: 6px;
		background: rgba(8, 13, 22, 0.85);
		color: #e5edf5;
		padding: 0.45rem 0.55rem;
		font: inherit;
	}
	input:focus,
	select:focus,
	.toggle:focus-visible,
	.summary button:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
	}
	.summary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding-top: 0.45rem;
		border-top: 1px solid #22344c;
	}
	.summary button {
		appearance: none;
		border: 1px solid #2c4870;
		border-radius: 999px;
		background: rgba(28, 42, 64, 0.75);
		color: #cfd9e6;
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
		.row,
		.row.three {
			grid-template-columns: 1fr;
		}
	}
</style>
