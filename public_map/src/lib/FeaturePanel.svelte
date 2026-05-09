<script lang="ts">
	import { fly } from 'svelte/transition';
	import { mapState } from './store.svelte';
	import { LAYER_IDS } from './layers';
	import StateRoundup from './StateRoundup.svelte';
	import LocalityDetail from './LocalityDetail.svelte';
	import CountyDetail from './CountyDetail.svelte';
	import JobCard from './JobCard.svelte';
	import JobList from './JobList.svelte';
	import PointJobList from './PointJobList.svelte';
	import ScopedAreaActions from './ScopedAreaActions.svelte';
	import { countValue, propString } from './format';
	import { LAYOUT_SLOTS, slotAttr } from './layout';

	function close() {
		mapState.selectedFeature = null;
		mapState.listView = null;
		mapState.jobStack = null;
	}

	function stackIndex(): number {
		return mapState.jobStack?.selectedIndex ?? 0;
	}

	function stackCount(): number {
		return mapState.jobStack?.items.length ?? 0;
	}

	function selectStackJob(index: number) {
		const stack = mapState.jobStack;
		if (!stack) return;
		const wrapped = (index + stack.items.length) % stack.items.length;
		const item = stack.items[wrapped];
		mapState.jobStack = { ...stack, selectedIndex: wrapped };
		mapState.selectedFeature = {
			source: LAYER_IDS.markers,
			label: 'Job card',
			properties: item.properties
		};
	}

	function backToPointList() {
		mapState.selectedFeature = null;
	}
</script>

{#if mapState.listView}
	<aside
		class="panel"
		aria-live="polite"
		data-layout-slot={slotAttr(LAYOUT_SLOTS.feature)}
		transition:fly={{ x: 24, duration: 200 }}
	>
		<header>
			<span class="layer">Job list</span>
			<button type="button" class="close" onclick={close} aria-label="Close">×</button>
		</header>
		<JobList listView={mapState.listView} />
	</aside>
{:else if mapState.jobStack && !mapState.selectedFeature}
	<aside
		class="panel"
		aria-live="polite"
		data-layout-slot={slotAttr(LAYOUT_SLOTS.feature)}
		transition:fly={{ x: 24, duration: 200 }}
	>
		<header>
			<span class="layer">Job point</span>
			<button type="button" class="close" onclick={close} aria-label="Close">Ã—</button>
		</header>
		<PointJobList stack={mapState.jobStack} />
	</aside>
{:else if mapState.selectedFeature}
	<aside
		class="panel"
		aria-live="polite"
		data-layout-slot={slotAttr(LAYOUT_SLOTS.feature)}
		transition:fly={{ x: 24, duration: 200 }}
	>
		<header>
			<span class="layer">{mapState.selectedFeature.label}</span>
			<button type="button" class="close" onclick={close} aria-label="Close">×</button>
		</header>
		{#if mapState.selectedFeature.source === LAYER_IDS.markers}
			{#if mapState.jobStack && stackCount() > 1}
				<nav class="stack-nav" aria-label="Jobs at this point">
					<button type="button" onclick={backToPointList}>List</button>
					<button type="button" onclick={() => selectStackJob(stackIndex() - 1)}>Prev</button>
					<span>{stackIndex() + 1} / {stackCount()}</span>
					<button type="button" onclick={() => selectStackJob(stackIndex() + 1)}>Next</button>
				</nav>
			{/if}
			<JobCard properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.statesFill}
			<ScopedAreaActions
				type="state"
				code={String(mapState.selectedFeature.properties.state ?? '')}
				label={String(mapState.selectedFeature.properties.name ?? mapState.selectedFeature.properties.state ?? '')}
			/>
			<StateRoundup properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.localitiesFill}
			<ScopedAreaActions
				type="locality"
				code={String(mapState.selectedFeature.properties.code ?? '')}
				label={String(mapState.selectedFeature.properties.name ?? mapState.selectedFeature.properties.code ?? '')}
			/>
			<LocalityDetail properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.countiesOutline}
			<CountyDetail properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.federalProperties}
			<section>
				<p class="eyebrow">GSA federal property</p>
				<h2>{propString(mapState.selectedFeature.properties, 'name')}</h2>
				<dl class="grid">
					<dt>Agency</dt><dd>{propString(mapState.selectedFeature.properties, 'agency')}</dd>
					<dt>Type</dt><dd>{propString(mapState.selectedFeature.properties, 'property_type')}</dd>
					<dt>Address</dt><dd>{propString(mapState.selectedFeature.properties, 'address')}</dd>
					<dt>City</dt><dd>{propString(mapState.selectedFeature.properties, 'city')}</dd>
					<dt>State</dt><dd>{propString(mapState.selectedFeature.properties, 'state')}</dd>
					<dt>ZIP</dt><dd>{propString(mapState.selectedFeature.properties, 'zip')}</dd>
					<dt>Status</dt><dd>{propString(mapState.selectedFeature.properties, 'building_status')}</dd>
				</dl>
				<p class="src">Source: GSA Federal Real Property Profile (FRPP) per ADR-0025.</p>
			</section>
		{:else}
			<section>
				<p class="eyebrow">Metro area</p>
				<h2>{propString(mapState.selectedFeature.properties, 'name')}</h2>
				<dl class="grid">
					<dt>CBSA</dt><dd>{propString(mapState.selectedFeature.properties, 'cbsa_code')}</dd>
					<dt>Type</dt><dd>{propString(mapState.selectedFeature.properties, 'cbsa_type')}</dd>
					<dt>Open postings</dt><dd>{countValue(mapState.selectedFeature.properties.postings)}</dd>
					<dt>RPP overall</dt><dd>{propString(mapState.selectedFeature.properties, 'rpp_overall')}</dd>
					<dt>Pay/COL index</dt><dd>{propString(mapState.selectedFeature.properties, 'pay_vs_col')}</dd>
				</dl>
			</section>
		{/if}
	</aside>
{/if}

<style>
	.panel { position: absolute; right: 1rem; top: 5.25rem; width: min(24rem, calc(100vw - 2rem)); max-height: calc(100vh - 7.5rem); overflow: auto; background: var(--c-panel, rgba(14, 23, 38, 0.96)); border: 1px solid var(--c-border, #2a3a52); border-radius: 10px; padding: 0.8rem 0.95rem; font-size: 12px; color: var(--c-text-2, #cfd9e6); z-index: 5; box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35); backdrop-filter: blur(8px); }
	header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }
	.layer, .eyebrow { color: var(--c-accent, #7bd0f2); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	.close { appearance: none; background: transparent; border: none; color: var(--c-muted, #94a3b8); font-size: 20px; line-height: 1; cursor: pointer; padding: 0; }
	.close:hover { color: var(--c-text, #e5edf5); }
	.stack-nav { display: grid; grid-template-columns: auto auto 1fr auto; gap: 0.35rem; align-items: center; margin-bottom: 0.65rem; padding: 0.4rem; border: 1px solid var(--c-border-subtle, #22344c); border-radius: 8px; background: var(--c-row-bg, rgba(8, 13, 22, 0.55)); }
	.stack-nav button { appearance: none; border: 1px solid var(--c-border-input, #2c4870); border-radius: 999px; background: var(--c-row-hover, rgba(28, 42, 64, 0.75)); color: var(--c-text-2, #d8e6f3); cursor: pointer; font: inherit; font-size: 11px; padding: 0.25rem 0.55rem; }
	.stack-nav button:hover { border-color: var(--c-accent, #7bd0f2); color: var(--c-accent, #7bd0f2); }
	.stack-nav button:focus-visible { outline: 2px solid var(--c-accent, #7bd0f2); outline-offset: 2px; }
	.stack-nav span { color: var(--c-muted, #94a3b8); font-size: 11px; text-align: center; }
	h2 { margin: 0 0 0.75rem; font-size: 20px; line-height: 1.15; color: var(--c-text, #e5edf5); }
	.grid { display: grid; grid-template-columns: 1fr auto; gap: 0.45rem 0.8rem; margin: 0; }
	dt { color: var(--c-muted, #94a3b8); }
	dd { margin: 0; font-weight: 600; text-align: right; color: var(--c-text-2, #cfd9e6); }
	.src { margin-top: 0.6rem; font-size: 10px; color: var(--c-muted, #64748b); }
	@media (max-width: 640px) { .panel { top: auto; bottom: 6.5rem; right: 0.5rem; left: 0.5rem; width: auto; max-height: 48vh; } }
</style>
