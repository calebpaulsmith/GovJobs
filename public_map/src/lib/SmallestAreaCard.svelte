<!--
	SmallestAreaCard — the Here tab on /browse.

	Renders context for the user's active geographic scope (locality > state >
	Nationwide), a deterministic templated summary, four tap-to-expand metric
	blocks (Postings / Workforce / Pay vs COL / Urgency), and an actions row.

	Pure helpers (resolveArea, urgencyCounts) live in ./areaCard.ts and are
	unit-tested in ./areaCard.test.ts. This component composes them with the
	loaded state/locality feature collections and the filter-aware job list.

	Mock: public_map/mocks/browse/mobile-dock.html, <section class="tab tab-here">.
-->
<script lang="ts">
	import {
		loadStates,
		loadLocalities,
		loadJobDetailsIndex,
		type FeatureCollection,
		type JobDetails
	} from './data';
	import { filterJobDetails } from './filters';
	import { mapState } from './store.svelte';
	import { money, percent, propString } from './format';
	import InfoTooltip from './InfoTooltip.svelte';
	import { resolveArea, urgencyCounts, type ResolvedArea } from './areaCard';

	interface Props {
		// Parent passes `() => (tab = 'list')`. Optional so the component is
		// usable in isolation (e.g. tests, mock-data screens).
		onViewList?: () => void;
	}

	let { onViewList }: Props = $props();

	let states = $state<FeatureCollection | null>(null);
	let localities = $state<FeatureCollection | null>(null);
	let jobIndex = $state<Record<string, JobDetails>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Pay vs COL is open by default per the mock — meaningful default since
	// the pay-vs-COL number is the headline value most users want to see.
	type MetricKey = 'postings' | 'workforce' | 'paycol' | 'urgency';
	let openMetric = $state<MetricKey | null>('paycol');

	function toggle(key: MetricKey) {
		openMetric = openMetric === key ? null : key;
	}

	$effect(() => {
		loading = true;
		error = null;
		Promise.all([loadStates(), loadLocalities(), loadJobDetailsIndex()])
			.then(([s, l, idx]) => {
				states = s;
				localities = l;
				jobIndex = idx;
			})
			.catch((err) => (error = (err as Error).message))
			.finally(() => (loading = false));
	});

	// --- area resolution + filter-aware job set -------------------------------

	const area = $derived<ResolvedArea>(resolveArea(mapState.filters, states, localities));

	// Posting + urgency counts must honor the WHOLE filter (geo + non-geo),
	// because the area's pre-computed `postings` only counts by geography.
	const filteredJobs = $derived<JobDetails[]>(
		filterJobDetails(Object.values(jobIndex), mapState.filters)
	);
	const filteredJobCount = $derived(filteredJobs.length);
	const urgency = $derived(urgencyCounts(filteredJobs));

	// --- area feature properties ----------------------------------------------

	function numProp(key: string): number | null {
		const props = area.feature?.properties;
		if (!props) return null;
		const v = props[key];
		if (v === null || v === undefined || v === '') return null;
		const n = Number(v);
		return Number.isFinite(n) ? n : null;
	}

	function strProp(key: string): string {
		return propString(area.feature?.properties ?? null, key, '—');
	}

	// Subtitle composition — short fact line under the title.
	const subtitle = $derived.by(() => {
		if (area.scope === 'nationwide') {
			return `${filteredJobCount.toLocaleString()} open postings matching the current filter`;
		}
		if (area.scope === 'state') {
			const postings = numProp('postings');
			const parts = [area.code];
			if (postings !== null) parts.push(`${postings.toLocaleString()} open postings`);
			return parts.join(' · ');
		}
		// locality
		const postings = numProp('postings');
		const counties = numProp('county_count');
		const parts = [area.code];
		if (postings !== null) parts.push(`${postings.toLocaleString()} open postings`);
		if (counties !== null) parts.push(`${counties.toLocaleString()} counties`);
		return parts.join(' · ');
	});

	// Top hiring agencies (top 3 by count) under the current filter — used in
	// the templated summary so the line is concrete, not boilerplate.
	const topAgencies = $derived.by<string[]>(() => {
		const counts = new Map<string, number>();
		for (const job of filteredJobs) {
			const code = (job.agency_code ?? '').trim().toUpperCase();
			if (!code) continue;
			counts.set(code, (counts.get(code) ?? 0) + 1);
		}
		return [...counts.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 3)
			.map(([code]) => code);
	});

	// Deterministic, templated summary. No LLM, ever. Honest about gaps:
	// clauses are skipped when the underlying value is unavailable.
	const summary = $derived.by(() => {
		const sentences: string[] = [];
		const areaLabel = area.scope === 'nationwide' ? 'nationwide' : `in ${area.label}`;
		sentences.push(
			`${filteredJobCount.toLocaleString()} open postings ${areaLabel} match the current filter.`
		);
		if (urgency.le3d > 0) {
			sentences.push(`${urgency.le3d.toLocaleString()} close within 3 days.`);
		}
		const gs13 = numProp('gs13_step1_locality');
		const payCol = numProp('pay_vs_col');
		if (gs13 !== null && payCol !== null && area.scope !== 'nationwide') {
			sentences.push(
				`GS-13 step 1 here pays ${money(gs13)}, ${payCol.toFixed(1)} on the pay-vs-COL index (national average = 100).`
			);
		}
		if (topAgencies.length > 0) {
			sentences.push(`Top hiring agencies: ${topAgencies.join(', ')}.`);
		}
		return sentences.join(' ');
	});

	// --- metric block values --------------------------------------------------

	const referenceYear = $derived(mapState.manifest?.reference_year ?? 2026);

	// Pay vs COL — value + delta vs national 100.
	const payVsCol = $derived(numProp('pay_vs_col'));
	const payVsColDelta = $derived.by(() => {
		if (payVsCol === null) return null;
		return payVsCol - 100;
	});

	// Workforce — only meaningful at state scope (export's localities feature
	// has no workforce property).
	const workforce = $derived(area.scope === 'state' ? numProp('workforce') : null);
	const accessions = $derived(area.scope === 'state' ? numProp('accessions') : null);
	const separations = $derived(area.scope === 'state' ? numProp('separations') : null);

	// Locality pay adjustment — only on locality features.
	const adjustmentPct = $derived(area.scope === 'locality' ? numProp('adjustment_pct') : null);
	const gs13 = $derived(numProp('gs13_step1_locality'));
	const rpp = $derived(numProp('rpp_overall'));
	const localityCodeProp = $derived(area.scope === 'state' ? strProp('locality_code') : '');

	// Action button label scales with filteredJobCount.
	const viewListLabel = $derived(
		`View ${filteredJobCount.toLocaleString()} posting${filteredJobCount === 1 ? '' : 's'} →`
	);

	function fmtCount(n: number | null | undefined): string {
		if (n === null || n === undefined || !Number.isFinite(n)) return '—';
		return Math.round(n).toLocaleString();
	}

	function fmtIndex(n: number | null | undefined): string {
		if (n === null || n === undefined || !Number.isFinite(n)) return '—';
		return n.toFixed(1);
	}
</script>

<section class="tab-here">
	{#if loading}
		<div class="eyebrow">Here</div>
		<p class="muted">Loading area context…</p>
	{:else if error}
		<div class="eyebrow">Here</div>
		<p class="muted">Couldn't load area data: {error}</p>
	{:else}
		<div class="eyebrow">Here · smallest area containing the active filter</div>
		<h2>{area.label}</h2>
		<p class="subtitle">{subtitle}</p>

		<!-- Deterministic, templated area summary — no LLM call, ever. -->
		<div class="area-summary">
			<div class="label">Area summary · auto-generated</div>
			{summary}
		</div>

		<!-- Four metric blocks. 2x2; opening one expands it across the row,
		     and only one is open at a time. -->
		<div class="metric-blocks">
			<!-- Postings (open) ---------------------------------------------- -->
			<button
				type="button"
				class="mblock"
				class:open={openMetric === 'postings'}
				onclick={() => toggle('postings')}
				aria-expanded={openMetric === 'postings'}
			>
				{#if openMetric === 'postings'}
					<div class="head">
						<span class="label">Postings (open)</span>
						<span class="value">{fmtCount(filteredJobCount)}</span>
					</div>
					<dl class="detail-grid">
						<dt>Matching current filter</dt>
						<dd>{fmtCount(filteredJobCount)}</dd>
						<dt>Closing within 3 days</dt>
						<dd>{fmtCount(urgency.le3d)}</dd>
						<dt>Closing within 7 days</dt>
						<dd>{fmtCount(urgency.le7d)}</dd>
						<dt>Active geo chips</dt>
						<dd>
							{mapState.filters.geographies.length > 0
								? mapState.filters.geographies.join(', ')
								: '—'}
						</dd>
						<dt>Active agency chips</dt>
						<dd>
							{mapState.filters.agencies.length > 0
								? mapState.filters.agencies.join(', ')
								: '—'}
						</dd>
					</dl>
					<div class="detail-src">Source: USAJOBS /Search, current filter</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Postings (open)</div>
					<div class="value">{fmtCount(filteredJobCount)}</div>
					<div class="delta">matching current filter</div>
					<div class="expand-hint">▾ tap to expand</div>
				{/if}
			</button>

			<!-- Workforce ----------------------------------------------------- -->
			<button
				type="button"
				class="mblock"
				class:open={openMetric === 'workforce'}
				onclick={() => toggle('workforce')}
				aria-expanded={openMetric === 'workforce'}
			>
				{#if openMetric === 'workforce'}
					<div class="head">
						<span class="label">Workforce</span>
						<span class="value">{fmtCount(workforce)}</span>
					</div>
					<dl class="detail-grid">
						<dt>Civilian headcount</dt>
						<dd>{fmtCount(workforce)}</dd>
						<dt>Accessions</dt>
						<dd>{fmtCount(accessions)}</dd>
						<dt>Separations</dt>
						<dd>{fmtCount(separations)}</dd>
					</dl>
					<div class="detail-src">
						Source: OPM FedScope — workforce counts, not postings.
						{#if area.scope !== 'state'}
							State-level only; not available for {area.scope === 'nationwide' ? 'the national view' : 'localities'}.
						{/if}
					</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Workforce</div>
					<div class="value">{fmtCount(workforce)}</div>
					<div class="delta">
						{area.scope === 'state' ? 'civilian, OPM' : 'state-level only'}
					</div>
					<div class="expand-hint">▾ tap to expand</div>
				{/if}
			</button>

			<!-- Pay vs COL ---------------------------------------------------- -->
			<button
				type="button"
				class="mblock"
				class:open={openMetric === 'paycol'}
				onclick={() => toggle('paycol')}
				aria-expanded={openMetric === 'paycol'}
			>
				{#if openMetric === 'paycol'}
					<div class="head">
						<span class="label">Pay vs COL</span>
						<span class="value">{fmtIndex(payVsCol)}</span>
						{#if payVsColDelta !== null}
							<span class="delta {payVsColDelta >= 0 ? 'up' : 'down'}">
								{payVsColDelta >= 0 ? '↑' : '↓'} {Math.abs(payVsColDelta).toFixed(1)}
								{payVsColDelta >= 0 ? 'above' : 'below'} national
							</span>
						{/if}
					</div>
					<dl class="detail-grid">
						{#if area.scope === 'locality'}
							<dt>Locality pay adjustment</dt>
							<dd>{percent(adjustmentPct)}</dd>
						{/if}
						<dt>GS-13 step 1 ({referenceYear})</dt>
						<dd>{money(gs13)}</dd>
						<dt>BEA RPP (overall)</dt>
						<dd>{rpp ?? '—'}</dd>
						<dt>Index formula</dt>
						<dd class="formula">(locality pay ÷ national base) ÷ (RPP ÷ 100) × 100</dd>
					</dl>
					<div class="detail-src">
						Sources: OPM {referenceYear} locality tables · BEA RPP · Census ACS.
						<InfoTooltip title="Purchasing-power index">
							<span>How far a GS-13 step 1 paycheck stretches relative to the U.S. average. 100 = average; &gt;100 = pay outpaces COL; &lt;100 = pay lags COL.</span>
							<span class="formula">(locality_pay ÷ national_base_pay) ÷ (rpp ÷ 100) × 100</span>
							<span class="src">Sources: OPM pay tables (numerator) + BEA RPP (denominator). National base = GS-13 step 1 base ({referenceYear}).</span>
						</InfoTooltip>
					</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Pay vs COL</div>
					<div class="value">{fmtIndex(payVsCol)}</div>
					<div class="delta {payVsColDelta !== null && payVsColDelta >= 0 ? 'up' : payVsColDelta !== null ? 'down' : ''}">
						{#if payVsColDelta === null}
							{area.scope === 'nationwide' ? 'area-level only' : '—'}
						{:else}
							{payVsColDelta >= 0 ? '↑' : '↓'} {Math.abs(payVsColDelta).toFixed(1)}
							{payVsColDelta >= 0 ? 'above' : 'below'} national
						{/if}
					</div>
					<div class="expand-hint">▾ tap to expand</div>
				{/if}
			</button>

			<!-- Urgency ------------------------------------------------------- -->
			<button
				type="button"
				class="mblock"
				class:open={openMetric === 'urgency'}
				onclick={() => toggle('urgency')}
				aria-expanded={openMetric === 'urgency'}
			>
				{#if openMetric === 'urgency'}
					<div class="head">
						<span class="label">Urgency</span>
						<span class="value">{fmtCount(urgency.le3d)}</span>
					</div>
					<dl class="detail-grid">
						<dt>Closing today</dt>
						<dd>{fmtCount(urgency.today)}</dd>
						<dt>Closing in ≤ 3 days</dt>
						<dd>{fmtCount(urgency.le3d)}</dd>
						<dt>Closing in ≤ 7 days</dt>
						<dd>{fmtCount(urgency.le7d)}</dd>
					</dl>
					<div class="detail-src">Source: USAJOBS close_date on the current filter</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Urgency</div>
					<div class="value">{fmtCount(urgency.le3d)}</div>
					<div class="delta {urgency.le3d > 0 ? 'down' : ''}">closing ≤ 3d</div>
					<div class="expand-hint">▾ tap to expand</div>
				{/if}
			</button>
		</div>

		<div class="actions">
			<!-- Deferred: "+ Save as Job List" button + provenance toast.
			     The slot is preserved so Saved-tab work can drop in later. -->
			<button
				type="button"
				class="pill-btn primary"
				onclick={() => onViewList?.()}
				disabled={filteredJobCount === 0}
			>
				{viewListLabel}
			</button>
		</div>

		{#if area.scope === 'state' && localityCodeProp && localityCodeProp !== '—'}
			<p class="note">Locality {localityCodeProp} covers the most counties of {area.code}.</p>
		{/if}
	{/if}
</section>

<style>
	.tab-here {
		padding: 0.9rem 1rem 1.2rem;
		max-width: 36rem;
		color: var(--c-text, #e5edf5);
	}
	.eyebrow {
		margin: 0 0 0.15rem;
		color: var(--c-accent, #7bd0f2);
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	h2 {
		margin: 0 0 0.25rem;
		font-size: 18px;
		line-height: 1.2;
	}
	.subtitle {
		color: var(--c-muted, #94a3b8);
		font-size: 12px;
		margin: 0 0 0.7rem;
	}
	.muted {
		color: var(--c-muted, #94a3b8);
		font-size: 12px;
	}

	.area-summary {
		font-size: 11.5px;
		color: var(--c-text-2, #cfd9e6);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-left: 3px solid var(--c-accent-dim, #4979b3);
		padding: 0.55rem 0.7rem;
		border-radius: 6px;
		margin: 0 0 0.7rem;
		line-height: 1.55;
	}
	.area-summary .label {
		color: var(--c-muted, #94a3b8);
		font-size: 9px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.25rem;
		font-weight: 600;
	}

	.metric-blocks {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.45rem;
		margin: 0 0 0.7rem;
	}

	.mblock {
		appearance: none;
		text-align: left;
		font: inherit;
		color: inherit;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		padding: 0.55rem 0.6rem;
		cursor: pointer;
		transition: border-color 100ms ease;
	}
	.mblock:hover {
		border-color: var(--c-accent-dim, #4979b3);
	}
	.mblock.open {
		grid-column: 1 / -1;
		border-color: var(--c-accent-dim, #4979b3);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.7));
	}
	.mblock .label {
		color: var(--c-muted, #94a3b8);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		font-size: 9px;
		font-weight: 600;
	}
	.mblock .value {
		font-size: 18px;
		font-weight: 700;
		color: var(--c-text, #e5edf5);
		margin: 0.12rem 0;
	}
	.mblock .delta {
		font-size: 10px;
		color: var(--c-muted, #94a3b8);
	}
	.mblock .delta.up {
		color: var(--c-success, #7bb29b);
	}
	.mblock .delta.down {
		color: var(--c-danger, #c87c7c);
	}
	.mblock .expand-hint {
		font-size: 9px;
		color: var(--c-faint, #64748b);
		margin-top: 0.25rem;
	}

	.mblock.open .head {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.mblock.open .head .value {
		font-size: 16px;
		margin: 0;
	}
	.mblock.open .detail-grid {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.2rem 0.8rem;
		font-size: 11px;
		margin: 0.5rem 0 0;
	}
	.mblock.open .detail-grid dt {
		color: var(--c-muted, #94a3b8);
	}
	.mblock.open .detail-grid dd {
		margin: 0;
		font-weight: 600;
		text-align: right;
		color: var(--c-text-2, #cfd9e6);
	}
	.mblock.open .detail-grid dd.formula {
		font-weight: 500;
		color: var(--c-muted, #94a3b8);
		font-size: 10px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}
	.mblock.open .detail-src {
		font-size: 9.5px;
		color: var(--c-faint, #64748b);
		margin-top: 0.45rem;
		line-height: 1.45;
	}
	.mblock.open .collapse-hint {
		font-size: 9px;
		color: var(--c-faint, #64748b);
		text-align: right;
		margin-top: 0.3rem;
	}

	.actions {
		display: flex;
		gap: 0.35rem;
		flex-wrap: wrap;
		margin-top: 0.4rem;
	}
	.pill-btn {
		appearance: none;
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.45rem 0.85rem;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		cursor: pointer;
		transition: border-color 100ms ease, color 100ms ease, background 100ms ease;
	}
	.pill-btn:hover:not(:disabled) {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.pill-btn.primary {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border-color: var(--c-accent-dim, #4979b3);
		color: var(--c-accent, #7bd0f2);
	}
	.pill-btn:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.note {
		margin: 0.7rem 0 0;
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
		line-height: 1.45;
	}
</style>
