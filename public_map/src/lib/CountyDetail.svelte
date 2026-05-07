<script lang="ts">
	import { countValue, money, propString } from './format';
	let { properties }: { properties: Record<string, unknown> } = $props();
</script>

<section>
	<p class="eyebrow">County detail</p>
	<h2>{propString(properties, 'name')} <span>{propString(properties, 'state')}</span></h2>
	<dl class="grid">
		<dt>FIPS</dt><dd>{propString(properties, 'fips')}</dd>
		<dt>Open postings</dt><dd>{countValue(properties.postings)}</dd>
		<dt>Locality code</dt><dd>{propString(properties, 'locality_code')}</dd>
		<dt>CBSA</dt><dd>{propString(properties, 'cbsa_code')}</dd>
		<dt>GS-13 step 1</dt><dd>{money(properties.gs13_step1_locality)}</dd>
		<dt>RPP overall</dt><dd>{propString(properties, 'rpp_overall')}</dd>
		<dt>Pay/COL index</dt><dd>{propString(properties, 'pay_vs_col')}</dd>
	</dl>
	<p class="note">County RPP uses the export's state-level fallback where BEA county RPP is unavailable.</p>
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
