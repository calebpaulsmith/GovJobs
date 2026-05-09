<script lang="ts">
	import { mapState } from './store.svelte';
	import { countValue, money, percent, propString } from './format';
	import InfoTooltip from './InfoTooltip.svelte';
	import QuickAdd from './QuickAdd.svelte';
	let { properties }: { properties: Record<string, unknown> } = $props();

	const localityName = $derived(propString(properties, 'name'));
	const localityCode = $derived(propString(properties, 'code'));
	const postings = $derived(Number.isFinite(Number(properties.postings)) ? Number(properties.postings) : 0);
	const referenceYear = $derived(mapState.manifest?.reference_year ?? 2025);
	const adjustmentPctRaw = $derived(propString(properties, 'adjustment_pct'));
	const gs13Locality = $derived(propString(properties, 'gs13_step1_locality'));
	const rppOverall = $derived(propString(properties, 'rpp_overall'));
	const payVsCol = $derived(propString(properties, 'pay_vs_col'));
	const isRppApprox = $derived(Boolean(properties.rpp_overall_approximate));

	function viewPostings() {
		if (!localityCode) return;
		mapState.selectedFeature = null;
		mapState.jobStack = null;
		mapState.listView = {
			scope: 'locality',
			code: localityCode,
			label: `${localityName} (${localityCode})`
		};
	}
</script>

<section>
	<p class="eyebrow">Locality pay area</p>
	<h2>
		{localityName}
		<span>
			<QuickAdd type="geography" value="locality:{localityCode}" label={localityCode} />
		</span>
	</h2>

	<button type="button" class="postings-btn" onclick={viewPostings} disabled={postings === 0 || !localityCode}>
		<span class="num">{countValue(postings)}</span>
		<span class="lbl">View open postings in this locality -></span>
	</button>
	<p class="postings-hint">Filter chips you've set apply to this list.</p>

	<dl class="grid">
		<dt>Open postings</dt><dd>{countValue(properties.postings)}</dd>
		<dt>County count</dt>
		<dd>
			{countValue(properties.county_count)}
			<InfoTooltip title="Counties in this locality" align="end">
				<span>Number of constituent counties OPM has assigned to {localityCode} for the active reference year.</span>
				<span class="src">Source: OPM annual locality definitions per 5 CFR 531.603 (locality_pay_counties)</span>
			</InfoTooltip>
		</dd>
		<dt>Locality adjustment</dt>
		<dd>
			{percent(properties.adjustment_pct)}
			<InfoTooltip title="Locality pay adjustment" align="end">
				<span>The percentage added to base GS pay for employees stationed in {localityCode}.</span>
				<span class="formula">locality_pay = base × (1 + {adjustmentPctRaw} ÷ 100)</span>
				<span class="src">Source: OPM {referenceYear} locality pay percentages (locality_pay_areas.adjustment_pct)</span>
			</InfoTooltip>
		</dd>
		<dt>GS-13 step 1</dt>
		<dd>
			{money(properties.gs13_step1_locality)}
			<InfoTooltip title="GS-13 step 1, locality-adjusted" align="end">
				<span>Illustrative locality-adjusted base pay for a GS-13 step 1 employee assigned to {localityCode}.</span>
				<span class="formula">base × (1 + adjustment_pct ÷ 100) = {gs13Locality}</span>
				<span class="src">Source: OPM {referenceYear} GS pay tables × locality % (pay_scales × locality_pay_areas)</span>
			</InfoTooltip>
		</dd>
		<dt>RPP overall</dt>
		<dd>
			{propString(properties, 'rpp_overall')}
			<InfoTooltip title="Regional Price Parity" align="end">
				<span>BEA Regional Price Parity for this locality. 100 = U.S. average. Higher = more expensive.</span>
				{#if isRppApprox}
					<span>Marked approximate — derived from CBSA coverage of the locality's constituent counties.</span>
				{/if}
				<span class="src">Source: BEA Regional Price Parities (cost_of_living_index)</span>
			</InfoTooltip>
		</dd>
		<dt>Pay/COL index</dt>
		<dd>
			{propString(properties, 'pay_vs_col')}
			<InfoTooltip title="Purchasing-power index" align="end">
				<span>How far a GS-13 step 1 paycheck stretches in {localityCode} relative to the U.S. average. 100 = average; &gt;100 = pay outpaces COL; &lt;100 = pay lags COL.</span>
				<span class="formula">(locality_pay ÷ national_base_pay) ÷ (rpp ÷ 100) × 100</span>
				<span class="formula">= ({gs13Locality} ÷ national_base) ÷ ({rppOverall} ÷ 100) × 100 = {payVsCol}</span>
				<span class="src">Sources: OPM pay tables (numerator) + BEA RPP (denominator). National base = GS-13 step 1 base ({referenceYear}).</span>
			</InfoTooltip>
		</dd>
	</dl>
	{#if isRppApprox}
		<p class="note">RPP is approximated from CBSA coverage for counties in this locality.</p>
	{/if}
</section>

<style>
	.eyebrow { margin: 0 0 0.25rem; color: #7bd0f2; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	h2 { margin: 0 0 0.75rem; font-size: 20px; line-height: 1.15; }
	h2 span { color: #94a3b8; font-size: 13px; font-weight: 400; }
	.postings-btn {
		appearance: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.6rem;
		width: 100%;
		padding: 0.55rem 0.75rem;
		margin-bottom: 0.25rem;
		background: rgba(73, 121, 179, 0.18);
		border: 1px solid #4979b3;
		border-radius: 8px;
		color: #e5edf5;
		font-size: 12px;
		cursor: pointer;
		transition: background 120ms ease, border-color 120ms ease;
	}
	.postings-btn:hover:not(:disabled) {
		background: rgba(123, 208, 242, 0.18);
		border-color: #7bd0f2;
	}
	.postings-btn:disabled {
		cursor: not-allowed;
		opacity: 0.45;
	}
	.postings-btn .num {
		font-weight: 700;
		font-size: 14px;
		color: #7bd0f2;
	}
	.postings-btn .lbl {
		flex: 1;
		text-align: right;
	}
	.postings-hint {
		margin: 0 0 0.7rem;
		color: #64748b;
		font-size: 10px;
	}
	.grid { display: grid; grid-template-columns: 1fr auto; gap: 0.45rem 0.8rem; margin: 0; }
	dt { color: #94a3b8; }
	dd { margin: 0; font-weight: 600; text-align: right; }
	.note { margin: 0.8rem 0 0; color: #94a3b8; font-size: 12px; line-height: 1.45; }
</style>
