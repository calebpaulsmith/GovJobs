<script lang="ts">
	import { countValue, money, propNumber, propString } from './format';
	import InfoTooltip from './InfoTooltip.svelte';
	import { mapState } from './store.svelte';
	let { properties }: { properties: Record<string, unknown> } = $props();

	const localityCode = $derived(propString(properties, 'locality_code'));
	const gs13Locality = $derived(propString(properties, 'gs13_step1_locality'));
	const rppOverall = $derived(propString(properties, 'rpp_overall'));
	const rppSource = $derived(propString(properties, 'rpp_overall_source', 'state'));
	const stateRpp = $derived(propString(properties, 'rpp_state'));
	const rentMedian = $derived(propNumber(properties, 'rent_median'));
	const rppLabel = $derived(rppSource === 'county' ? 'County COL index' : 'RPP overall');
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
		{#if rentMedian !== null}
			<dt>Median gross rent</dt>
			<dd>
				{money(rentMedian)}
				<InfoTooltip title="ACS median gross rent" align="end">
					<span>Census ACS 5-year median gross rent (table B25064) for this county. Used as the within-state rent ratio for the county COL estimate.</span>
					<span class="src">Source: U.S. Census Bureau, ACS 5-year B25064 (cost_of_living_index, geo_type=county)</span>
				</InfoTooltip>
			</dd>
		{/if}
		<dt>{rppLabel}</dt>
		<dd>
			{rppOverall}
			<InfoTooltip title={rppSource === 'county' ? 'County COL estimate' : 'Regional Price Parity'} align="end">
				{#if rppSource === 'county'}
					<span>Estimated cost-of-living index for this county. 100 = U.S. average. Higher = more expensive.</span>
					<span class="formula">state_rpp × (county_rent ÷ state_median_rent)</span>
					<span class="formula">= {stateRpp} × ({rentMedian ?? '—'} ÷ state_median) = {rppOverall}</span>
					<span class="src">Sources: BEA state RPP × Census ACS B25064 county rents (D.5.10).</span>
					<span class="src note">Approximation. BEA does not publish county-level RPP; this scales the state RPP by the county's rent ratio within its state.</span>
				{:else}
					<span>Cost-of-living index for this county. 100 = U.S. average. Higher = more expensive.</span>
					<span>State-level fallback: this county is not yet covered by the ACS county-rent ingest.</span>
					<span class="src">Source: BEA Regional Price Parities (cost_of_living_index, geo_type=state)</span>
				{/if}
			</InfoTooltip>
		</dd>
		<dt>Pay/COL index</dt>
		<dd>
			{payVsCol}
			<InfoTooltip title="Purchasing-power index" align="end">
				<span>How far a GS-13 step 1 paycheck stretches in this county relative to the U.S. average. 100 = average; &gt;100 = pay outpaces COL; &lt;100 = pay lags COL.</span>
				<span class="formula">(locality_pay ÷ national_base_pay) ÷ (rpp ÷ 100) × 100</span>
				<span class="formula">= ({gs13Locality} ÷ national_base) ÷ ({rppOverall} ÷ 100) × 100 = {payVsCol}</span>
				<span class="src">Sources: OPM pay tables (numerator) + {rppSource === 'county' ? 'derived county COL' : 'BEA RPP'} (denominator). National base = GS-13 step 1 base ({referenceYear}).</span>
			</InfoTooltip>
		</dd>
	</dl>
	<p class="note">
		{#if rppSource === 'county'}
			County COL estimated from BEA state RPP scaled by the county's ACS rent ratio. Refresh ACS data to update.
		{:else}
			County RPP uses the state-level fallback where ACS county rent has not been ingested yet.
		{/if}
	</p>
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
