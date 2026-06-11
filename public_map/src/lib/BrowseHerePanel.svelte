<!--
	BrowseHerePanel — the "Here" content for /browse, shared by two hosts:
	  • BrowseSheet (mobile bottom sheet, < 1024 px)
	  • the desktop mosaic's top-right pane (≥ 1024 px)

	Renders the tapped area's card (State / Locality / County), a job card for
	a tapped marker, a PointJobList for a tapped cluster, or — when nothing is
	selected — the first-run welcome card plus the SmallestAreaCard fallback.

	"Add this area to my list" is the explicit, opt-in way to narrow the
	working list by geography (no auto-chips on tap, per ADR-0033 #5).

	Callbacks are optional so each host wires only what makes sense there:
	on desktop the list and map are always visible, so the welcome card's
	"See postings list" / "Explore the map" buttons are hidden when their
	handlers are absent.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from './store.svelte';
	import { LAYER_IDS } from './layers';
	import { propString, countValue } from './format';
	import AddressSearch from './AddressSearch.svelte';
	import StateRoundup from './StateRoundup.svelte';
	import LocalityDetail from './LocalityDetail.svelte';
	import CountyDetail from './CountyDetail.svelte';
	import SmallestAreaCard from './SmallestAreaCard.svelte';
	import JobCard from './JobCard.svelte';
	import PointJobList from './PointJobList.svelte';

	const WELCOME_KEY = 'fedfinder.public_map.browse_welcome.v1';

	interface Props {
		onViewList?: () => void;
		onExploreMap?: () => void;
	}

	let { onViewList, onExploreMap }: Props = $props();

	// D.6.4 (ADR-0035): first-run welcome card. Defaults to dismissed so it
	// never flashes before onMount reads the flag.
	let welcomeDismissed = $state(true);

	onMount(() => {
		if (!browser) return;
		welcomeDismissed = localStorage.getItem(WELCOME_KEY) === '1';
	});

	function dismissWelcome() {
		welcomeDismissed = true;
		if (browser) localStorage.setItem(WELCOME_KEY, '1');
	}

	// Explicit, opt-in geography add. Mirrors the chip format ScopedAreaActions
	// uses on /map so the two paths produce identical, deduped chips.
	function addAreaToList(type: 'state' | 'locality', code: string) {
		const value = String(code ?? '').trim().toUpperCase();
		if (!value) return;
		const chip = `${type}:${value}`;
		if (mapState.filters.geographies.includes(chip)) return;
		mapState.filters = {
			...mapState.filters,
			geographies: [...mapState.filters.geographies, chip]
		};
	}

	function isInList(type: 'state' | 'locality', code: string): boolean {
		return mapState.filters.geographies.includes(`${type}:${String(code ?? '').trim().toUpperCase()}`);
	}

	const sel = $derived(mapState.selectedFeature);
</script>

{#if mapState.jobStack && !sel}
	<!-- {#key} forces PointJobList to fully remount when the jobStack's items
	     count changes. The cluster path seeds an empty stack synchronously
	     from the click handler (so this branch is selected immediately) and
	     then the async leaves callback fills in the items. Without the key,
	     PointJobList's `stack` prop doesn't re-evaluate when mapState.jobStack
	     is replaced from the actor callback. Keying on items.length triggers
	     a clean remount once the leaves arrive. -->
	{#key mapState.jobStack.items.length}
		<PointJobList stack={mapState.jobStack} />
	{/key}
{:else if sel}
	{#if sel.source === LAYER_IDS.markers}
		<JobCard properties={sel.properties} />
	{:else if sel.source === LAYER_IDS.statesFill}
		<button
			type="button"
			class="add-area"
			disabled={isInList('state', String(sel.properties.state ?? ''))}
			onclick={() => addAreaToList('state', String(sel.properties.state ?? ''))}
		>
			{isInList('state', String(sel.properties.state ?? '')) ? '✓ In your list' : '+ Add this area to my list'}
		</button>
		<StateRoundup properties={sel.properties} />
	{:else if sel.source === LAYER_IDS.localitiesFill}
		<button
			type="button"
			class="add-area"
			disabled={isInList('locality', String(sel.properties.code ?? ''))}
			onclick={() => addAreaToList('locality', String(sel.properties.code ?? ''))}
		>
			{isInList('locality', String(sel.properties.code ?? '')) ? '✓ In your list' : '+ Add this area to my list'}
		</button>
		<LocalityDetail properties={sel.properties} />
	{:else if sel.source === LAYER_IDS.countiesOutline}
		<CountyDetail properties={sel.properties} />
	{:else}
		<section class="generic">
			<h2>{propString(sel.properties, 'name')}</h2>
			<dl>
				<dt>Open postings</dt><dd>{countValue(sel.properties.postings)}</dd>
				{#if sel.properties.cbsa_code}<dt>CBSA</dt><dd>{propString(sel.properties, 'cbsa_code')}</dd>{/if}
				{#if sel.properties.agency}<dt>Agency</dt><dd>{propString(sel.properties, 'agency')}</dd>{/if}
			</dl>
		</section>
	{/if}
{:else}
	{#if !welcomeDismissed}
		<div class="welcome" role="region" aria-label="Getting started">
			<div class="welcome-head">
				<h2>Find your federal job</h2>
				<button type="button" class="welcome-close" onclick={dismissWelcome} aria-label="Dismiss welcome">✕</button>
			</div>
			<p class="welcome-sub">Jump to where you'd work, or browse everything that's open.</p>
			<AddressSearch docked onChoose={dismissWelcome} />
			{#if onViewList || onExploreMap}
				<div class="welcome-actions">
					{#if onViewList}
						<button
							type="button"
							class="welcome-btn"
							onclick={() => {
								dismissWelcome();
								onViewList?.();
							}}
						>
							See postings list
						</button>
					{/if}
					{#if onExploreMap}
						<button
							type="button"
							class="welcome-btn"
							onclick={() => {
								dismissWelcome();
								onExploreMap?.();
							}}
						>
							Explore the map
						</button>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
	<SmallestAreaCard {onViewList} />
{/if}

<style>
	.add-area {
		appearance: none;
		width: 100%;
		margin-bottom: 0.6rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 8px;
		background: var(--c-accent-bg-strong, rgba(73, 121, 179, 0.2));
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.55rem;
		cursor: pointer;
	}
	.add-area:hover:not(:disabled) {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.add-area:disabled {
		cursor: default;
		opacity: 0.7;
		border-color: #5e9a4a;
		background: rgba(94, 154, 74, 0.15);
	}
	.welcome {
		margin-bottom: 0.7rem;
		padding: 0.7rem 0.75rem 0.8rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 10px;
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.1));
	}
	.welcome-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.welcome-head h2 {
		margin: 0;
		font-size: 16px;
		color: var(--c-text, #e5edf5);
	}
	.welcome-close {
		appearance: none;
		border: none;
		background: none;
		color: var(--c-muted, #94a3b8);
		font-size: 14px;
		cursor: pointer;
		padding: 0.15rem 0.35rem;
		border-radius: 4px;
	}
	.welcome-close:hover {
		color: var(--c-text, #e5edf5);
		background: rgba(255, 255, 255, 0.07);
	}
	.welcome-sub {
		margin: 0.25rem 0 0.6rem;
		font-size: 12px;
		color: var(--c-text-2, #cfd9e6);
		line-height: 1.45;
	}
	.welcome-actions {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.6rem;
	}
	.welcome-btn {
		appearance: none;
		flex: 1;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.45rem;
		border-radius: 8px;
		cursor: pointer;
	}
	.welcome-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.generic h2 {
		margin: 0 0 0.6rem;
		font-size: 18px;
		color: var(--c-text, #e5edf5);
	}
	.generic dl {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.4rem 0.8rem;
		margin: 0;
	}
	.generic dt {
		color: var(--c-muted, #94a3b8);
	}
	.generic dd {
		margin: 0;
		font-weight: 600;
		text-align: right;
		color: var(--c-text-2, #cfd9e6);
	}
</style>
