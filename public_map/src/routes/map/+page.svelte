<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import Map from '$lib/Map.svelte';
	import MetricSwitcher from '$lib/MetricSwitcher.svelte';
	import FeaturePanel from '$lib/FeaturePanel.svelte';
	import FilterPanel from '$lib/FilterPanel.svelte';
	import ActiveFilterStrip from '$lib/ActiveFilterStrip.svelte';
	import SavedSearchMenu from '$lib/SavedSearchMenu.svelte';
	import AddressSearch from '$lib/AddressSearch.svelte';
	import ProfileDrawer from '$lib/ProfileDrawer.svelte';
	import CompensationComparator from '$lib/CompensationComparator.svelte';
	import { LAYOUT_SLOTS, slotAttr } from '$lib/layout';
	import { mapState } from '$lib/store.svelte';
	import { jobProfile } from '$lib/jobProfile.svelte';

	const THEME_KEY = 'fedfinder.public_map.theme.v1';

	const savedCount = $derived(jobProfile.savedJobs.length);

	// Seed mapState hidden/saved sets from persisted profile on startup.
	$effect(() => {
		mapState.hiddenJobIds = jobProfile.hiddenIds;
		mapState.savedJobIds = jobProfile.savedJobs.reduce((s, j) => { s.add(j.id); return s; }, new Set<string>());
	});

	// Initialize theme from localStorage, persist on change.
	onMount(() => {
		if (!browser) return;
		const stored = localStorage.getItem(THEME_KEY);
		if (stored === 'light' || stored === 'dark') {
			mapState.theme = stored;
		}
	});

	$effect(() => {
		if (!browser) return;
		const t = mapState.theme;
		localStorage.setItem(THEME_KEY, t);
		document.documentElement.dataset.theme = t;
	});

	function toggleTheme() {
		mapState.theme = mapState.theme === 'dark' ? 'light' : 'dark';
	}
</script>

<svelte:head>
	<title>FedFinder — Federal Job Map</title>
</svelte:head>

<div class="root" data-theme={mapState.theme}>
	<header class="masthead" data-layout-slot={slotAttr(LAYOUT_SLOTS.masthead)}>
		<div class="brand">
			<span class="logo" aria-hidden="true"></span>
			<div>
				<h1>FedFinder</h1>
				<p class="tagline">Federal jobs, by paycheck and place</p>
			</div>
		</div>
		{#if mapState.manifest}
			<div class="manifest">
				<span>Reference year {mapState.manifest.reference_year}</span>
				<span>{mapState.manifest.job_count.toLocaleString()} local snapshot postings</span>
				<span>Updated {new Date(mapState.manifest.generated_at).toLocaleDateString()}</span>
			</div>
		{/if}
		<button
			type="button"
			class="profile-btn"
			onclick={() => (mapState.compareOpen = true)}
			aria-label="Open pay and cost-of-living comparator"
			title="Compare pay across localities and states"
		>
			Pay Compare
		</button>
		<button
			type="button"
			class="profile-btn"
			onclick={() => (mapState.profileOpen = true)}
			aria-label="Open my jobs profile"
			title="My saved and hidden jobs"
		>
			My Jobs{#if savedCount > 0}<span class="profile-count">{savedCount}</span>{/if}
		</button>
		<button
			type="button"
			class="theme-btn"
			onclick={toggleTheme}
			aria-label="Toggle light/dark mode"
			title={mapState.theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
			data-layout-slot={slotAttr(LAYOUT_SLOTS['theme-toggle'])}
		>
			{mapState.theme === 'dark' ? '☀' : '☾'}
		</button>
	</header>

	<ProfileDrawer />
	<CompensationComparator />

	{#key mapState.theme}
		<Map />
	{/key}
	<MetricSwitcher />
	<AddressSearch />
	<SavedSearchMenu />
	<FilterPanel />
	<ActiveFilterStrip />
	<FeaturePanel />

	<footer class="attrib" data-layout-slot={slotAttr(LAYOUT_SLOTS.freshness)}>
		<span>Data: USAJOBS · OPM · U.S. Census · BEA</span>
		<span>Not affiliated with the U.S. government</span>
	</footer>
</div>

<style>
	.root {
		position: fixed;
		inset: 0;
		overflow: hidden;
	}
	.masthead {
		/* Position from public_map/src/lib/layout.ts (slot 'masthead'). The
		   max-width cap is what stops the brand + manifest + buttons from
		   bleeding into the top-left address-search column at desktop +
		   tablet widths. Content wraps inside the pill when it exceeds the
		   cap, which is preferable to overlapping the side panels. */
		position: absolute;
		top: var(--slot-masthead-top);
		left: var(--slot-masthead-left);
		right: var(--slot-masthead-right);
		transform: var(--slot-masthead-transform);
		max-width: var(--slot-masthead-max-width);
		z-index: 4;
		display: flex;
		gap: 1.25rem;
		align-items: center;
		flex-wrap: wrap;
		padding: 0.55rem 0.95rem;
		background: var(--c-panel-blur, rgba(14, 23, 38, 0.85));
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 999px;
		backdrop-filter: blur(8px);
		pointer-events: none;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.logo {
		display: inline-block;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: radial-gradient(circle at 30% 30%, #7bd0f2, #2c5b8a 70%);
		box-shadow: 0 0 12px rgba(123, 208, 242, 0.5);
	}
	h1 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		letter-spacing: 0.01em;
		color: var(--c-text, #e5edf5);
	}
	.tagline {
		margin: 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.manifest {
		display: flex;
		gap: 0.9rem;
		font-size: 11px;
		color: var(--c-text-2, #cfd9e6);
		border-left: 1px solid var(--c-border, #2a3a52);
		padding-left: 1rem;
	}
	.manifest span {
		white-space: nowrap;
	}
	.profile-btn {
		appearance: none;
		pointer-events: all;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(28, 42, 64, 0.6));
		color: var(--c-text-2, #cfd9e6);
		font-size: 11px;
		padding: 0.25rem 0.65rem;
		border-radius: 999px;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.3rem;
		white-space: nowrap;
		transition: border-color 120ms ease, color 120ms ease;
		border-left: none;
		margin-left: 0.5rem;
	}
	.profile-btn:hover { border-color: var(--c-accent, #7bd0f2); color: var(--c-accent, #7bd0f2); }
	.profile-count {
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 10px;
		font-weight: 700;
		padding: 0.05rem 0.4rem;
		border-radius: 999px;
	}
	.theme-btn {
		pointer-events: all;
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(28, 42, 64, 0.6));
		color: var(--c-text-2, #cfd9e6);
		font-size: 14px;
		width: 2rem;
		height: 2rem;
		border-radius: 999px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		transition: border-color 120ms ease, color 120ms ease;
		flex-shrink: 0;
	}
	.theme-btn:hover { border-color: var(--c-accent, #7bd0f2); color: var(--c-accent, #7bd0f2); }
	.attrib {
		/* Position from public_map/src/lib/layout.ts (slot 'freshness'). */
		position: absolute;
		bottom: var(--slot-freshness-bottom);
		right: var(--slot-freshness-right);
		left: var(--slot-freshness-left);
		display: flex;
		gap: 0.9rem;
		font-size: 10px;
		color: var(--c-faint, #64748b);
		pointer-events: none;
		z-index: 4;
	}

	/* Position at every breakpoint comes from --slot-* in layout.ts. Only
	   the per-breakpoint visual changes (column wrap, border radius) belong
	   here. */
	@media (max-width: 719px) {
		.masthead {
			flex-direction: column;
			gap: 0.4rem;
			align-items: flex-start;
			border-radius: 8px;
		}
		.manifest {
			border-left: none;
			padding-left: 0;
			flex-wrap: wrap;
		}
	}
</style>
