<script lang="ts">
	import { countValue, money, percent, propString } from './format';
	let { properties }: { properties: Record<string, unknown> } = $props();
</script>

<section>
	<p class="eyebrow">Locality pay area</p>
	<h2>{propString(properties, 'name')} <span>{propString(properties, 'code')}</span></h2>
	<dl class="grid">
		<dt>Open postings</dt><dd>{countValue(properties.postings)}</dd>
		<dt>County count</dt><dd>{countValue(properties.county_count)}</dd>
		<dt>Locality adjustment</dt><dd>{percent(properties.adjustment_pct)}</dd>
		<dt>GS-13 step 1</dt><dd>{money(properties.gs13_step1_locality)}</dd>
		<dt>RPP overall</dt><dd>{propString(properties, 'rpp_overall')}</dd>
		<dt>Pay/COL index</dt><dd>{propString(properties, 'pay_vs_col')}</dd>
	</dl>
	{#if properties.rpp_overall_approximate}
		<p class="note">RPP is approximated from CBSA coverage for counties in this locality.</p>
	{/if}
</section>

<style>
	.eyebrow { margin: 0 0 0.25rem; color: #7bd0f2; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	h2 { margin: 0 0 0.75rem; font-size: 20px; line-height: 1.15; }
	h2 span { color: #94a3b8; font-size: 13px; font-weight: 400; }
	.grid { display: grid; grid-template-columns: 1fr auto; gap: 0.45rem 0.8rem; margin: 0; }
	dt { color: #94a3b8; }
	dd { margin: 0; font-weight: 600; text-align: right; }
	.note { margin: 0.8rem 0 0; color: #94a3b8; font-size: 12px; line-height: 1.45; }
</style>
