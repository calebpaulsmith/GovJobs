<script lang="ts">
	import { mapState } from './store.svelte';
	import { countValue, money, percent, propString } from './format';
	let { properties }: { properties: Record<string, unknown> } = $props();

	const localityName = $derived(propString(properties, 'name'));
	const localityCode = $derived(propString(properties, 'code'));
	const postings = $derived(Number.isFinite(Number(properties.postings)) ? Number(properties.postings) : 0);

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
	<h2>{localityName} <span>{localityCode}</span></h2>

	<button type="button" class="postings-btn" onclick={viewPostings} disabled={postings === 0 || !localityCode}>
		<span class="num">{countValue(postings)}</span>
		<span class="lbl">View open postings in this locality -></span>
	</button>
	<p class="postings-hint">Filter chips you've set apply to this list.</p>

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
