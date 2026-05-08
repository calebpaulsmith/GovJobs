<script lang="ts">
	import { fly } from 'svelte/transition';
	import { mapState } from './store.svelte';
	import { LAYER_IDS } from './layers';
	import StateRoundup from './StateRoundup.svelte';
	import LocalityDetail from './LocalityDetail.svelte';
	import CountyDetail from './CountyDetail.svelte';
	import JobCard from './JobCard.svelte';
	import { countValue, propString } from './format';

	function close() {
		mapState.selectedFeature = null;
	}
</script>

{#if mapState.selectedFeature}
	<aside class="panel" aria-live="polite" transition:fly={{ x: 24, duration: 200 }}>
		<header>
			<span class="layer">{mapState.selectedFeature.label}</span>
			<button type="button" class="close" onclick={close} aria-label="Close">×</button>
		</header>
		{#if mapState.selectedFeature.source === LAYER_IDS.markers}
			<JobCard properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.statesFill}
			<StateRoundup properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.localitiesFill}
			<LocalityDetail properties={mapState.selectedFeature.properties} />
		{:else if mapState.selectedFeature.source === LAYER_IDS.countiesOutline}
			<CountyDetail properties={mapState.selectedFeature.properties} />
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
	.panel { position: absolute; right: 1rem; top: 5.25rem; width: min(24rem, calc(100vw - 2rem)); max-height: calc(100vh - 7.5rem); overflow: auto; background: rgba(14, 23, 38, 0.96); border: 1px solid #2a3a52; border-radius: 10px; padding: 0.8rem 0.95rem; font-size: 12px; color: #cfd9e6; z-index: 5; box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35); backdrop-filter: blur(8px); }
	header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }
	.layer, .eyebrow { color: #7bd0f2; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	.close { appearance: none; background: transparent; border: none; color: #94a3b8; font-size: 20px; line-height: 1; cursor: pointer; padding: 0; }
	.close:hover { color: #e5edf5; }
	h2 { margin: 0 0 0.75rem; font-size: 20px; line-height: 1.15; }
	.grid { display: grid; grid-template-columns: 1fr auto; gap: 0.45rem 0.8rem; margin: 0; }
	dt { color: #94a3b8; }
	dd { margin: 0; font-weight: 600; text-align: right; }
	@media (max-width: 640px) { .panel { top: auto; bottom: 1.5rem; right: 0.5rem; left: 0.5rem; width: auto; max-height: 48vh; } }
</style>
