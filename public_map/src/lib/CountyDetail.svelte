<script lang="ts">
	import { countValue, money, propString } from './format';
	import InfoTooltip from './InfoTooltip.svelte';
	import { mapState } from './store.svelte';
	let { properties }: { properties: Record<string, unknown> } = $props();

	const localityCode = $derived(propString(properties, 'locality_code'));
	const gs13Locality = $derived(propString(properties, 'gs13_step1_locality'));
	const rppOverall = $derived(propString(properties, 'rpp_overall'));
	const payVsCol = $derived(propString(properties, 'pay_vs_col'));
	const referenceYear = $derived(mapState.manifest?.reference_year ?? 2025);
</script>

<section>
	<p class="eyebrow">County detail</p>
	<h2>{propString(properties, 'name')} <span>{propString(properties, 'state')}</span></h2>
	<dl class="grid">
		<dt>FIPS</dt><dd>{propString(properties, 'fips')}</dd>
		<dt>Open postings</dt><dd>{countValue(properties.postings)}</dd>
		<dt>Locality code</dt>
		<dd>
			{localityCode}
			<InfoTooltip title="Locality pay area" align="end">
				<span>The OPM locality pay area assigned to this county. Drives the locality % adjustment used in the pay calculations below.</span>
				<span class="src">Source: OPM annual locality definitions per 5 CFR 531.603 (locality_pay_counties)</span>
			</InfoTooltip>
		</dd>
		<dt>CBSA</dt>
		<dd>
			{propString(properties, 'cbsa_code')}
			<InfoTooltip title="Core-based statistical area" align="end">
				<span>Census Bureau CBSA code for this county. Used to join BEA metro-level RPP when a county-level value is not published.</span>
				<span class="src">Source: Census TIGER 2023 metro/county relationship tables (counties.cbsa_code)</span>
			</InfoTooltip>
		</dd>
		<dt>GS-13 step 1</dt>
		<dd>
			{money(properties.gs13_step1_locality)}
			<InfoTooltip title="GS-13 step 1, locality-adjusted" align="end">
				<span>Illustrative locality-adjusted base pay for a GS-13 step 1 employee in this county's locality.</span>
				<span class="formula">base × (1 + adjustment_pct ÷ 100) = {gs13Locality}</span>
				<span class="src">Source: OPM {referenceYear} GS pay tables × locality % (pay_scales × locality_pay_areas)</span>
			</InfoTooltip>
		</dd>
		<dt>RPP overall</dt>
		<dd>
			{rppOverall}
			<InfoTooltip title="Regional Price Parity" align="end">
				<span>Cost-of-living index for this county. 100 = U.S. average. Higher = more expensive.</span>
				<span>Where BEA county RPP is unavailable, the export falls back to the state-level value.</span>
				<span class="src">Source: BEA Regional Price Parities (cost_of_living_index)</span>
			</InfoTooltip>
		</dd>
		<dt>Pay/COL index</dt>
		<dd>
			{payVsCol}
			<InfoTooltip title="Purchasing-power index" align="end">
				<span>How far a GS-13 step 1 paycheck stretches in this county relative to the U.S. average. 100 = average; &gt;100 = pay outpaces COL; &lt;100 = pay lags COL.</span>
				<span class="formula">(locality_pay ÷ national_base_pay) ÷ (rpp ÷ 100) × 100</span>
				<span class="formula">= ({gs13Locality} ÷ national_base) ÷ ({rppOverall} ÷ 100) × 100 = {payVsCol}</span>
				<span class="src">Sources: OPM pay tables (numerator) + BEA RPP (denominator). National base = GS-13 step 1 base ({referenceYear}).</span>
			</InfoTooltip>
		</dd>
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
