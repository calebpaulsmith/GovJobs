<script lang="ts">
	import { mapState } from './store.svelte';
	import { METRICS, METRIC_ORDER } from './metrics';
	import { countValue, metricValue, propString } from './format';
	import InfoTooltip from './InfoTooltip.svelte';

	let { properties }: { properties: Record<string, unknown> } = $props();

	function num(key: string): number | null {
		const v = properties?.[key];
		if (v === null || v === undefined || v === '') return null;
		const n = Number(v);
		return Number.isFinite(n) ? n : null;
	}

	function fmtMoney(value: number | null): string {
		if (value === null) return '—';
		return value.toLocaleString(undefined, {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 0
		});
	}

	const stateName = $derived(propString(properties, 'name'));
	const stateCode = $derived(propString(properties, 'state'));
	const postings = $derived(num('postings') ?? 0);
	const localityCode = $derived(propString(properties, 'locality_code'));
	const gs13Pay = $derived(num('gs13_step1_locality'));
	const rpp = $derived(num('rpp_overall'));
	const payVsCol = $derived(num('pay_vs_col'));
	// Reference-year national base — same value the export used as the
	// denominator. We re-derive it client-side for the tooltip rather than
	// adding a new property to every state feature.
	const referenceYear = $derived(mapState.manifest?.reference_year ?? 2025);

	function viewPostings() {
		mapState.listView = {
			scope: 'state',
			code: stateCode,
			label: `${stateName} (${stateCode})`
		};
	}
</script>

<section>
	<p class="eyebrow">State roundup</p>
	<h2>{stateName} <span>{stateCode}</span></h2>
	<div class="hero">
		<strong>{metricValue(properties, mapState.metric)}</strong>
		<span>{METRICS[mapState.metric].label}</span>
	</div>

	<button type="button" class="postings-btn" onclick={viewPostings} disabled={postings === 0}>
		<span class="num">{countValue(postings)}</span>
		<span class="lbl">View open postings in this state →</span>
	</button>
	<p class="postings-hint">Filter chips you've set apply to this list.</p>

	<dl class="grid">
		{#each METRIC_ORDER as key (key)}
			<dt>{METRICS[key].short}</dt>
			<dd>{metricValue(properties, key)}</dd>
		{/each}

		<dt>Locality</dt>
		<dd>
			{localityCode}
			<InfoTooltip title="Dominant locality">
				<span>The OPM locality pay area that covers the most counties of {stateCode}, excluding Rest of U.S. (RUS).</span>
				<span class="src">Source: OPM annual locality definitions per 5 CFR 531.603 (locality_pay_counties table)</span>
			</InfoTooltip>
		</dd>

		<dt>GS-13 step 1</dt>
		<dd>
			{fmtMoney(gs13Pay)}
			<InfoTooltip title="GS-13 step 1, locality-adjusted">
				<span>Illustrative locality-adjusted base pay for a GS-13 step 1 employee assigned to {localityCode}.</span>
				<span class="formula">base × (1 + adjustment_pct ÷ 100)</span>
				<span class="src">Source: OPM {referenceYear} GS pay tables + locality % adjustments (pay_scales × locality_pay_areas)</span>
			</InfoTooltip>
		</dd>

		<dt>RPP</dt>
		<dd>
			{rpp ?? '—'}
			<InfoTooltip title="Regional Price Parity">
				<span>BEA Regional Price Parity for {stateCode}. 100 = U.S. average. Higher = more expensive.</span>
				<span class="src">Source: BEA Regional Price Parities, state-level (cost_of_living_index, geo_type=state)</span>
			</InfoTooltip>
		</dd>

		<dt>Pay/COL index</dt>
		<dd>
			{payVsCol ?? '—'}
			<InfoTooltip title="Purchasing-power index">
				<span>How far a GS-13 step 1 paycheck stretches in {stateCode} relative to the U.S. average. 100 = average; &gt;100 = pay outpaces COL; &lt;100 = pay lags COL.</span>
				<span class="formula">(locality_pay ÷ national_base_pay) ÷ (rpp ÷ 100) × 100</span>
				{#if gs13Pay && rpp}
					<span class="formula">= ({fmtMoney(gs13Pay)} ÷ national_base) ÷ ({rpp} ÷ 100) × 100</span>
				{/if}
				<span class="src">Sources: OPM pay tables (numerator) + BEA RPP (denominator). National base = GS-13 step 1 base ({referenceYear}).</span>
			</InfoTooltip>
		</dd>
	</dl>

	<p class="note">
		Open postings are USAJOBS markers in this state. Workforce / accessions / separations are
		OPM workforce counts, not posting counts.
	</p>
</section>

<style>
	.eyebrow {
		margin: 0 0 0.25rem;
		color: #7bd0f2;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	h2 {
		margin: 0 0 0.75rem;
		font-size: 20px;
		line-height: 1.15;
	}
	h2 span {
		color: #94a3b8;
		font-size: 13px;
		font-weight: 400;
	}
	.hero {
		padding: 0.75rem;
		border: 1px solid #2a3a52;
		border-radius: 8px;
		background: rgba(123, 208, 242, 0.08);
		margin-bottom: 0.6rem;
	}
	.hero strong {
		display: block;
		font-size: 24px;
	}
	.hero span,
	.note {
		color: #94a3b8;
		font-size: 12px;
	}
	.postings-btn {
		appearance: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.6rem;
		width: 100%;
		padding: 0.55rem 0.75rem;
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
		margin: 0.25rem 0 0.7rem;
		color: #64748b;
		font-size: 10px;
	}
	.grid {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.4rem 0.8rem;
		margin: 0;
	}
	dt {
		color: #94a3b8;
	}
	dd {
		margin: 0;
		font-weight: 600;
	}
	.note {
		margin: 0.8rem 0 0;
		line-height: 1.45;
	}
</style>
