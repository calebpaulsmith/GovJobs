<!--
	FedFinder — Browse view (mobile-first), map-as-home.

	The full-screen map is the home surface. A left-edge "Filters" pill opens the
	shared FilterSheet (same fields as /map, one mapState.filters store). Tapping
	a state / locality / county / marker opens the bottom sheet (BrowseSheet) to
	that area's card; swiping/segmenting to "Postings" shows the shared JobList.
	"Saved" in the masthead opens the SavedDrawer (job lists + saved postings).

	Spec: public_map/mocks/browse/ (rev 2), ADR-0033. Bottom-sheet swipe gesture
	+ remembered page is the next increment (Layer 4); Layer 3 uses a segmented
	control.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from '$lib/store.svelte';
	import { activeFilterCount } from '$lib/filters';
	import { jobProfile } from '$lib/jobProfile.svelte';
	import Map from '$lib/Map.svelte';
	import FilterSheet from '$lib/FilterSheet.svelte';
	import BrowseSheet from '$lib/BrowseSheet.svelte';
	import SavedDrawer from '$lib/SavedDrawer.svelte';
	import BuildStamp from '$lib/BuildStamp.svelte';
	import AddressSearch from '$lib/AddressSearch.svelte';
	import CompensationComparator from '$lib/CompensationComparator.svelte';
	import UngeocodedSheet from '$lib/UngeocodedSheet.svelte';

	// D.6.2: "Go to" panel visibility. Local to this page — distinct from
	// mapState.addressSearchOpen, which means "the results dropdown is open".
	let goToOpen = $state(false);

	const THEME_KEY = 'fedfinder.public_map.theme.v1';

	// Theme — read once, persist on change (so /browse themes when opened direct).
	onMount(() => {
		if (!browser) return;
		const stored = localStorage.getItem(THEME_KEY);
		if (stored === 'light' || stored === 'dark') mapState.theme = stored;
	});
	$effect(() => {
		if (!browser) return;
		document.documentElement.dataset.theme = mapState.theme;
		localStorage.setItem(THEME_KEY, mapState.theme);
	});
	function toggleTheme() {
		mapState.theme = mapState.theme === 'dark' ? 'light' : 'dark';
	}

	const savedCount = $derived(jobProfile.savedJobs.length);
</script>

<svelte:head>
	<title>FedFinder — Browse federal jobs</title>
</svelte:head>

<div class="browse" data-theme={mapState.theme}>
	<!-- Masthead -->
	<header class="masthead">
		<span class="brand">FedFinder</span>
		<nav class="modes" aria-label="View mode">
			<span class="mode active">Browse</span>
			<a class="mode" href="/map">Map only</a>
			<span class="mode disabled" aria-disabled="true" title="Coming soon">Localities</span>
		</nav>
		<button type="button" class="saved-btn" onclick={() => (mapState.savedDrawerOpen = true)} aria-label="Open saved">
			★ Saved{#if savedCount > 0}<span class="saved-pip">{savedCount}</span>{/if}
		</button>
		<button type="button" class="theme-btn" onclick={toggleTheme} aria-label="Toggle light or dark mode">
			{mapState.theme === 'dark' ? '☀' : '☾'}
		</button>
		<a class="about-link" href="/about">About</a>
	</header>

	<!-- Build/version + USAJOBS data freshness. -->
	<BuildStamp />

	<!-- Map fills the home surface; overlays sit on top of it. -->
	<main class="content">
		<div class="map-frame">
			<Map browseMode />
			<div class="fab-row">
				<button
					type="button"
					class="filters-fab"
					onclick={() => (mapState.filterSheetOpen = true)}
					aria-label="Open filters"
				>
					<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M3 5h18l-7 8v6l-4 2v-8z" /></svg>
					Filters
					{#if activeFilterCount(mapState.filters) > 0}
						<span class="fab-count">{activeFilterCount(mapState.filters)}</span>
					{/if}
				</button>
				<button
					type="button"
					class="filters-fab"
					class:open={goToOpen}
					onclick={() => (goToOpen = !goToOpen)}
					aria-expanded={goToOpen}
					aria-label="Go to an address, city, or ZIP"
				>
					<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z" /></svg>
					Go to
				</button>
			</div>
			{#if goToOpen}
				<div class="goto-panel">
					<AddressSearch docked commitRadius onChoose={() => (goToOpen = false)} />
				</div>
			{/if}
			<FilterSheet />
			<BrowseSheet />
		</div>
	</main>

	<SavedDrawer />
	<!-- D.6.3: comparator drawer (z 50/51, above the sheet) opened from a
	     JobCard's "Compare pay" action. -->
	<CompensationComparator />
	<!-- Swipe-away list of postings the map couldn't place (z 45/46), opened
	     from the "N postings not on the map" button in the filter sheet. -->
	<UngeocodedSheet />
</div>

<style>
	.browse {
		position: fixed;
		inset: 0;
		display: flex;
		flex-direction: column;
		background: var(--c-bg, #06111f);
		color: var(--c-text, #e5edf5);
		font-size: 14px;
	}

	/* Masthead */
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
	.mode.disabled {
		color: var(--c-faint, #64748b);
		cursor: not-allowed;
	}
	.saved-btn {
		margin-left: auto;
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 999px;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 11px;
		font-weight: 600;
		padding: 0.3rem 0.6rem;
		cursor: pointer;
	}
	.saved-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.saved-pip {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1rem;
		height: 1rem;
		padding: 0 0.25rem;
		border-radius: 999px;
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 9px;
		font-weight: 700;
	}
	.theme-btn {
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

	/* Content = full-screen map surface. The bottom sheet scrolls internally,
	   so .content itself does not scroll. */
	.content {
		position: relative;
		flex: 1;
		overflow: hidden;
	}
	.map-frame {
		position: absolute;
		inset: 0;
	}
	.fab-row {
		position: absolute;
		top: 0.75rem;
		left: 0.75rem;
		z-index: 6;
		display: flex;
		gap: 0.5rem;
	}
	.goto-panel {
		/* Directly below the FAB row in the same top-left column (single
		   column per invariant #12 — no overlap by construction). */
		position: absolute;
		top: 3.2rem;
		left: 0.75rem;
		width: min(22rem, calc(100% - 1.5rem));
		z-index: 7;
	}
	.filters-fab {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		appearance: none;
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 999px;
		background: var(--c-panel-blur, rgba(14, 23, 38, 0.92));
		backdrop-filter: blur(8px);
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.45rem 0.75rem;
		cursor: pointer;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
	}
	.filters-fab:hover {
		border-color: var(--c-accent, #7bd0f2);
	}
	.filters-fab.open {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.filters-fab svg {
		color: var(--c-accent, #7bd0f2);
	}
	.filters-fab:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.fab-count {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.1rem;
		height: 1.1rem;
		padding: 0 0.3rem;
		border-radius: 999px;
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 10px;
		font-weight: 700;
	}

	@media (min-width: 720px) {
		.browse {
			max-width: 30rem;
			margin: 0 auto;
			border-left: 1px solid var(--c-border, #2a3a52);
			border-right: 1px solid var(--c-border, #2a3a52);
		}
	}
</style>
