<script lang="ts">
	import { slide } from 'svelte/transition';
	import { onDestroy, onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { METRIC_ORDER, type MetricKey } from './metrics';
	import { mapState } from './store.svelte';
	import {
		activeFilterCount,
		filtersFromSearchParams,
		writeFiltersToSearchParams
	} from './filters';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import FilterFields from './FilterFields.svelte';

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

	// (2026-05-09) Removed: auto-collapse on featureOpen. With the always-visible
	// ActiveFilterStrip across the top, the user never loses sight of active
	// filters, so collapse-on-feature-open is no longer needed for visibility.

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
			<FilterFields />
		</div>
	{/if}
</section>

<style>
	/* Position vars come from public_map/src/lib/layout.ts via +layout.svelte.
	   Local state-driven shifts (.address-open / .saved-open) are deltas off
	   the base --slot-filters-top so layout.ts stays the single source of
	   truth for the resting position. */
	.filters {
		position: absolute;
		left: var(--slot-filters-left);
		top: var(--slot-filters-top);
		right: var(--slot-filters-right);
		bottom: var(--slot-filters-bottom);
		width: var(--slot-filters-width);
		z-index: 6;
		color: #cfd9e6;
		font-size: 12px;
		transition: top 160ms ease;
		display: var(--slot-filters-display, block);
	}
	@media (min-width: 720px) {
		.filters.address-open {
			top: calc(var(--slot-filters-top) + 5rem);
		}
		.filters.saved-open {
			top: calc(var(--slot-filters-top) + 11rem);
		}
		.filters.saved-open.address-open {
			top: calc(var(--slot-filters-top) + 23rem);
		}
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
	.toggle span {
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
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
	.toggle:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.body {
		margin-top: 0.45rem;
		padding: 0.85rem;
		border-radius: 10px;
	}
</style>
