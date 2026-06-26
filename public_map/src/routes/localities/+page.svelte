<!--
	/localities — the D.5.27 Localities screen (ADR-0032). A dedicated
	browse-and-drill screen (NOT a map mode): the LocalityRollup table is the
	centerpiece. Filters are editable here via the shared FilterSheet (same
	FilterFields as /map and /browse), and the rollup re-tallies live. The
	screen owns no map; it loads the bundle into the shared store if a prior
	screen hasn't already, so it works on direct navigation too.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from '$lib/store.svelte';
	import { loadJobs, loadJobDetailsIndex } from '$lib/data';
	import LocalityRollup from '$lib/LocalityRollup.svelte';
	import ActiveFilterStrip from '$lib/ActiveFilterStrip.svelte';
	import FilterSheet from '$lib/FilterSheet.svelte';

	const THEME_KEY = 'fedfinder.public_map.theme.v1';
	let loading = $state(true);

	onMount(async () => {
		if (!browser) return;
		const stored = localStorage.getItem(THEME_KEY);
		if (stored === 'light' || stored === 'dark') mapState.theme = stored;
		// Mirror Map.svelte's bundle load so the rollup has a corpus even on
		// direct navigation to /localities (no map screen visited first).
		if (Object.keys(mapState.allJobDetails).length === 0) {
			const [jobs, details] = await Promise.all([loadJobs(), loadJobDetailsIndex()]);
			mapState.allJobs = jobs;
			mapState.allJobDetails = details;
		}
		loading = false;
	});

	$effect(() => {
		if (!browser) return;
		document.documentElement.dataset.theme = mapState.theme;
		localStorage.setItem(THEME_KEY, mapState.theme);
	});
	function toggleTheme() {
		mapState.theme = mapState.theme === 'dark' ? 'light' : 'dark';
	}
</script>

<svelte:head><title>Localities · FedFinder</title></svelte:head>

<div class="localities" data-theme={mapState.theme}>
	<header class="masthead">
		<span class="brand">FedFinder</span>
		<nav class="modes" aria-label="View mode">
			<a class="mode" href="/browse">Browse</a>
			<a class="mode" href="/map">Map only</a>
			<span class="mode active" aria-current="page">Localities</span>
		</nav>
		<button type="button" class="theme-btn" onclick={toggleTheme} aria-label="Toggle light or dark mode">
			{mapState.theme === 'dark' ? '☀' : '☾'}
		</button>
		<a class="about-link" href="/about">About</a>
	</header>

	<main class="content">
		<div class="intro">
			<h1>Localities</h1>
			<p>
				Compare federal pay areas by how many postings they hold under your filters, then drill into
				the ones worth a move. Counts and pay reflect every filter except geography.
			</p>
		</div>

		<div class="filters-row">
			<div class="strip-wrap"><ActiveFilterStrip docked /></div>
			<button type="button" class="edit-btn" onclick={() => (mapState.filterSheetOpen = true)}>Edit filters</button>
		</div>

		{#if loading}
			<p class="loading" role="status">Loading postings…</p>
		{:else}
			<LocalityRollup />
		{/if}
	</main>

	<FilterSheet />
</div>

<style>
	.localities {
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
	/* The rollup fills remaining height and scrolls internally. */
	.content :global(.rollup) {
		flex: 1;
		min-height: 0;
	}
</style>
