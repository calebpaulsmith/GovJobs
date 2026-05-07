<script lang="ts">
	import { mapState } from './store.svelte';
	import { METRICS, METRIC_ORDER } from './metrics';
	import { countValue, metricValue, propString } from './format';

	let { properties }: { properties: Record<string, unknown> } = $props();
</script>

<section>
	<p class="eyebrow">State roundup</p>
	<h2>{propString(properties, 'name')} <span>{propString(properties, 'state')}</span></h2>
	<div class="hero">
		<strong>{metricValue(properties, mapState.metric)}</strong>
		<span>{METRICS[mapState.metric].label}</span>
	</div>
	<dl class="grid">
		{#each METRIC_ORDER as key (key)}
			<dt>{METRICS[key].short}</dt>
			<dd>{metricValue(properties, key)}</dd>
		{/each}
		<dt>Locality</dt>
		<dd>{propString(properties, 'locality_code')}</dd>
		<dt>GS-13 step 1</dt>
		<dd>{propString(properties, 'gs13_step1_locality')}</dd>
		<dt>RPP</dt>
		<dd>{propString(properties, 'rpp_overall')}</dd>
	</dl>
	<p class="note">
		{countValue(properties.postings)} open postings are marker-level USAJOBS records in this state;
		workforce, accessions, and separations are OPM workforce counts, not posting counts.
	</p>
</section>

<style>
	.eyebrow { margin: 0 0 0.25rem; color: #7bd0f2; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	h2 { margin: 0 0 0.75rem; font-size: 20px; line-height: 1.15; }
	h2 span { color: #94a3b8; font-size: 13px; font-weight: 400; }
	.hero { padding: 0.75rem; border: 1px solid #2a3a52; border-radius: 8px; background: rgba(123, 208, 242, 0.08); margin-bottom: 0.75rem; }
	.hero strong { display: block; font-size: 24px; }
	.hero span, .note { color: #94a3b8; font-size: 12px; }
	.grid { display: grid; grid-template-columns: 1fr auto; gap: 0.4rem 0.8rem; margin: 0; }
	dt { color: #94a3b8; }
	dd { margin: 0; font-weight: 600; }
	.note { margin: 0.8rem 0 0; line-height: 1.45; }
</style>
