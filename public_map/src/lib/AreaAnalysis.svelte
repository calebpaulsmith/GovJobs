<!--
	AreaAnalysis — the area metrics block on the Analysis screen (ADR-0039).

	Formerly the Browse "Here" tab (SmallestAreaCard). Browse is now for
	finding jobs; this card analyzes ONE explicitly chosen area at any level
	(nationwide / state / locality / metro / county) under the user's
	non-geographic filters: a deterministic templated summary, the live pulse
	band, four tap-to-expand metric blocks (Postings / Workforce / Pay vs COL /
	Urgency), and the click-to-load trend + "What to watch" notes.

	Scoping: the area replaces Browse's geography/radius chips
	(analysisArea.ts::filtersForArea). Metro and county areas are scoped by
	point-in-polygon over duty-station coordinates — postings without a
	mappable duty station can't be placed and are named as excluded.
-->
<script lang="ts" module>
	import { loadClosedJobs as loadClosedJobsRaw, type FeatureCollection as FC } from './data';
	// The card remounts on every area switch; the closed-jobs overlay is a
	// big file, so parse it once per page load, not once per switch.
	let closedCache: Promise<FC> | null = null;
	function loadClosedJobsOnce(): Promise<FC> {
		closedCache ??= loadClosedJobsRaw();
		return closedCache;
	}
</script>

<script lang="ts">
	import {
		loadJobDetailsIndex,
		loadJobs,
		type FeatureCollection,
		type JobDetails
	} from './data';
	import { filterJobDetails, filterJobs } from './filters';
	import { mapState } from './store.svelte';
	import { money, percent, propString } from './format';
	import InfoTooltip from './InfoTooltip.svelte';
	import { urgencyCounts } from './areaCard';
	import { computeAreaPulse } from './areaPulse';
	import { coordsByJobId, pointInGeometry, geometryBbox } from './geo';
	import {
		filtersForArea,
		jobIdsInArea,
		needsPolygonScope,
		type AnalysisArea
	} from './analysisArea';
	import type { TrendArea } from './areaTrend';
	import AreaTrendSparkline from './AreaTrendSparkline.svelte';
	import AreaWatchNote from './AreaWatchNote.svelte';

	interface Props {
		area: AnalysisArea;
		/** Jump to Browse with the postings list scoped to this area. */
		onViewList?: () => void;
	}

	let { area, onViewList }: Props = $props();

	let jobIndex = $state<Record<string, JobDetails>>({});
	let jobsGeo = $state<FeatureCollection | null>(null);
	let closedJobs = $state<FeatureCollection | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Pay vs COL is open by default — the headline value most users want.
	type MetricKey = 'postings' | 'workforce' | 'paycol' | 'urgency';
	let openMetric = $state<MetricKey | null>('paycol');

	function toggle(key: MetricKey) {
		openMetric = openMetric === key ? null : key;
	}

	$effect(() => {
		loading = true;
		error = null;
		// Reuse the jobs collection the page already parsed into the shared
		// store (tens of MB) — only fall back to fetching on a cold store.
		const shared = mapState.allJobs;
		const jobsPromise = shared && shared.features?.length ? Promise.resolve(shared) : loadJobs();
		Promise.all([loadJobDetailsIndex(), jobsPromise, loadClosedJobsOnce()])
			.then(([idx, jobs, closed]) => {
				jobIndex = idx;
				jobsGeo = jobs;
				closedJobs = closed;
			})
			.catch((err) => (error = (err as Error).message))
			.finally(() => (loading = false));
	});

	// --- area-scoped, filter-aware job sets ------------------------------------

	const areaFilters = $derived(filtersForArea(mapState.filters, area));
	const polygonScoped = $derived(needsPolygonScope(area));
	const coords = $derived(coordsByJobId(jobsGeo));
	const idsInPolygon = $derived(polygonScoped ? jobIdsInArea(area, coords) : null);

	const filteredJobs = $derived.by<JobDetails[]>(() => {
		const base = filterJobDetails(Object.values(jobIndex), areaFilters);
		const ids = idsInPolygon;
		return ids ? base.filter((j) => ids.has(String(j.id))) : base;
	});
	const filteredJobCount = $derived(filteredJobs.length);
	const urgency = $derived(urgencyCounts(filteredJobs));

	// Postings under the filter that have no mappable duty station — they
	// can't be placed in a county/metro, so name them instead of hiding them.
	const unplaceable = $derived.by(() => {
		if (!polygonScoped) return 0;
		let n = 0;
		for (const job of filterJobDetails(Object.values(jobIndex), areaFilters)) {
			if (!coords.has(String(job.id))) n += 1;
		}
		return n;
	});

	// Closed-within-90d features for the pulse baseline (invariant #22's one
	// bundled historic slice), scoped the same way as the open postings.
	const filteredClosed = $derived.by(() => {
		if (!closedJobs) return [];
		const feats = filterJobs(closedJobs, areaFilters, jobIndex).features;
		if (!polygonScoped) return feats;
		const geom = area.feature?.geometry;
		const bbox = geometryBbox(geom);
		if (!geom || !bbox) return [];
		return feats.filter((f) => {
			if (f.geometry?.type !== 'Point') return false;
			const pt = f.geometry.coordinates as [number, number];
			if (pt[0] < bbox[0] || pt[0] > bbox[2] || pt[1] < bbox[1] || pt[1] > bbox[3]) return false;
			return pointInGeometry(pt, geom);
		});
	});

	const pulse = $derived(
		loading || error
			? null
			: computeAreaPulse(filteredJobs, filteredClosed, {
					scope: area.level,
					code: area.code ?? '',
					label: area.label
				})
	);

	// The trend/watch components take the Here card's area shape; county and
	// metro pass their primary state (HistoricJoa has no finer filter).
	const trendArea = $derived.by<TrendArea>(() => {
		if (area.level === 'nationwide') return { scope: 'nationwide', code: null, label: 'Nationwide', feature: null };
		if (area.level === 'state') return { scope: 'state', code: area.code ?? '', label: area.label, feature: area.feature };
		if (area.level === 'locality')
			return { scope: 'locality', code: area.code ?? '', label: area.label, feature: area.feature ?? { type: 'Feature', geometry: null, properties: {} } };
		return { scope: area.level, code: area.code ?? '', label: area.label, primaryState: area.primaryState };
	});

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

	const LEVEL_NOUN: Record<string, string> = {
		nationwide: 'Nationwide',
		state: 'State',
		locality: 'Locality pay area',
		metro: 'Metro area (CBSA)',
		county: 'County'
	};

	// Subtitle composition — short fact line under the title.
	const subtitle = $derived.by(() => {
		const parts: string[] = [LEVEL_NOUN[area.level] ?? area.level];
		if (area.level !== 'nationwide' && area.code) parts.push(area.code);
		if (area.level === 'locality') {
			const counties = numProp('county_count');
			if (counties !== null) parts.push(`${counties.toLocaleString()} counties`);
		}
		parts.push(`${filteredJobCount.toLocaleString()} open postings match your filters`);
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
		const areaLabel = area.level === 'nationwide' ? 'nationwide' : `in ${area.label}`;
		sentences.push(
			`${filteredJobCount.toLocaleString()} open postings ${areaLabel} match your filters.`
		);
		if (urgency.le3d > 0) {
			sentences.push(`${urgency.le3d.toLocaleString()} close within 3 days.`);
		}
		const gs13v = numProp('gs13_step1_locality');
		const payCol = numProp('pay_vs_col');
		if (gs13v !== null && payCol !== null && area.level !== 'nationwide') {
			sentences.push(
				`GS-13 step 1 here pays ${money(gs13v)}, ${payCol.toFixed(1)} on the pay-vs-COL index (national average = 100).`
			);
		}
		if (topAgencies.length > 0) {
			sentences.push(`Top hiring agencies: ${topAgencies.join(', ')}.`);
		}
		return sentences.join(' ');
	});

	// --- metric block values --------------------------------------------------

	const referenceYear = $derived(mapState.manifest?.reference_year ?? 2026);

	// Pay vs COL — value + delta vs national 100. States, localities and
	// counties carry it; metros only carry RPP.
	const payVsCol = $derived(numProp('pay_vs_col'));
	const payVsColDelta = $derived.by(() => {
		if (payVsCol === null) return null;
		return payVsCol - 100;
	});

	// Workforce — OPM FedScope is state-level only.
	const workforce = $derived(area.level === 'state' ? numProp('workforce') : null);
	const accessions = $derived(area.level === 'state' ? numProp('accessions') : null);
	const separations = $derived(area.level === 'state' ? numProp('separations') : null);

	const adjustmentPct = $derived(area.level === 'locality' ? numProp('adjustment_pct') : null);
	const gs13 = $derived(numProp('gs13_step1_locality'));
	const rpp = $derived(numProp('rpp_overall'));
	const rppSource = $derived(area.level === 'county' ? strProp('rpp_overall_source') : '');

	const viewListLabel = $derived(
		`See ${filteredJobCount.toLocaleString()} posting${filteredJobCount === 1 ? '' : 's'} in Browse →`
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

<section class="tab-here area-analysis">
	{#if loading}
		<div class="eyebrow">Analysis</div>
		<p class="muted">Loading area data…</p>
	{:else if error}
		<div class="eyebrow">Analysis</div>
		<p class="muted">Couldn't load area data: {error}</p>
	{:else}
		<div class="eyebrow">Analysis · {LEVEL_NOUN[area.level] ?? area.level}</div>
		<h2>{area.label}</h2>
		<p class="subtitle">{subtitle}</p>
		{#if unplaceable > 0}
			<p class="scope-note">
				{unplaceable.toLocaleString()} matching posting{unplaceable === 1 ? ' has' : 's have'} no mappable duty station and
				can't be placed in a {area.level === 'metro' ? 'metro' : 'county'}, so {unplaceable === 1 ? 'it is' : 'they are'} not counted here.
			</p>
		{/if}

		<!-- Deterministic, templated area summary — no LLM call, ever. -->
		<div class="area-summary">
			<div class="label">Area summary · auto-generated</div>
			{summary}
		</div>

		<!-- D.5.28 pulse band: four headline numbers with deltas vs. the
		     trailing-90-day average, computed from the bundle for this area.
		     Dashed placeholders while loading — never fabricated numbers. -->
		<div class="pulse-band" data-status={pulse ? 'live' : 'placeholder'}>
			{#each [
				{ label: 'Open postings', value: pulse?.openPostings, deltaKey: 'openPostings' },
				{ label: 'New in last 7d', value: pulse?.newLast7d, deltaKey: 'newLast7d' },
				{ label: 'Median window', value: pulse?.medianWindowDays, deltaKey: 'medianWindowDays', unit: 'd' },
				{ label: 'Closing ≤ 3d', value: pulse?.closingSoon3d, deltaKey: 'closingSoon3d' }
			] as cell (cell.label)}
				{@const delta = pulse?.deltas?.[cell.deltaKey]}
				<div class="pulse-cell" class:empty={cell.value == null}>
					<div class="pulse-label">{cell.label}</div>
					<div class="pulse-value">
						{cell.value != null ? `${cell.value.toLocaleString()}${cell.unit ?? ''}` : '—'}
					</div>
					{#if delta != null}
						<div
							class="pulse-delta"
							class:up={delta > 0}
							class:down={delta < 0}
							title="New postings this week vs. the trailing-90-day weekly average of posting openings (open + closed-within-90-days postings under the current filter; approximate)"
						>
							{delta > 0 ? '↑' : delta < 0 ? '↓' : ''} {Math.abs(delta)}% vs 90d avg
						</div>
					{/if}
				</div>
			{/each}
			{#if !pulse}
				<div class="pulse-caption">PLACEHOLDER — needs historical slice</div>
			{/if}
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
						<dt>Matching your filters</dt>
						<dd>{fmtCount(filteredJobCount)}</dd>
						<dt>Closing within 3 days</dt>
						<dd>{fmtCount(urgency.le3d)}</dd>
						<dt>Closing within 7 days</dt>
						<dd>{fmtCount(urgency.le7d)}</dd>
						<dt>Area</dt>
						<dd>{area.label}</dd>
						<dt>Active agency chips</dt>
						<dd>
							{mapState.filters.agencies.length > 0
								? mapState.filters.agencies.join(', ')
								: '—'}
						</dd>
					</dl>
					<div class="detail-src">Source: USAJOBS /Search, your filters, scoped to this area</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Postings (open)</div>
					<div class="value">{fmtCount(filteredJobCount)}</div>
					<div class="delta">matching your filters</div>
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
						{#if area.level !== 'state'}
							State-level only; not available for {area.level === 'nationwide' ? 'the national view' : `a ${LEVEL_NOUN[area.level]?.toLowerCase() ?? area.level}`} — switch to State to see it.
						{/if}
					</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Workforce</div>
					<div class="value">{fmtCount(workforce)}</div>
					<div class="delta">
						{area.level === 'state' ? 'civilian, OPM' : 'state-level only'}
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
						{#if area.level === 'locality'}
							<dt>Locality pay adjustment</dt>
							<dd>{percent(adjustmentPct)}</dd>
						{/if}
						<dt>GS-13 step 1 ({referenceYear})</dt>
						<dd>{money(gs13)}</dd>
						<dt>BEA RPP (overall)</dt>
						<dd>{rpp ?? '—'}{#if rppSource === 'county'} (county, ACS rent-derived){:else if rppSource === 'state'} (state fallback){/if}</dd>
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
							{area.level === 'nationwide' ? 'area-level only' : area.level === 'metro' ? 'not computed for metros' : '—'}
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
					<div class="detail-src">Source: USAJOBS close_date, your filters, this area</div>
					<div class="collapse-hint">▴ tap to collapse</div>
				{:else}
					<div class="label">Urgency</div>
					<div class="value">{fmtCount(urgency.le3d)}</div>
					<div class="delta {urgency.le3d > 0 ? 'down' : ''}">closing ≤ 3d</div>
					<div class="expand-hint">▾ tap to expand</div>
				{/if}
			</button>
		</div>

		<!-- D.5.28 volume sparkline: click-to-load 12-month HistoricJoa trend
		     via the edge-cached /api/job-history Function (ADR-0029 / invariant
		     #22 — on-demand, never bundled). -->
		<AreaTrendSparkline area={trendArea} />

		<!-- ADR-0036 "What to watch": deterministic, keyless 3-year context
		     from the same Function. Click-to-load, like the sparkline. -->
		<AreaWatchNote area={trendArea} />

		{#if onViewList}
			<div class="actions">
				<button
					type="button"
					class="pill-btn primary"
					onclick={() => onViewList?.()}
					disabled={filteredJobCount === 0}
				>
					{viewListLabel}
				</button>
			</div>
		{/if}

	{/if}
</section>

<style>
	.tab-here {
		padding: 0.9rem 1rem 1.2rem;
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
	.scope-note {
		margin: -0.35rem 0 0.7rem;
		color: var(--c-warn, #f5c451);
		font-size: 11px;
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
	/* D.5.28 pulse band. Dashed border + explicit caption while the data
	   slice is absent (data-status="placeholder"). */
	.pulse-band {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.35rem;
		margin: 0 0 0.5rem;
		position: relative;
	}
	.pulse-band[data-status='placeholder'] {
		padding-bottom: 0.9rem;
	}
	.pulse-cell {
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 6px;
		padding: 0.35rem 0.45rem;
	}
	.pulse-band[data-status='placeholder'] .pulse-cell {
		border-style: dashed;
		opacity: 0.75;
	}
	.pulse-label {
		font-size: 8.5px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--c-muted, #94a3b8);
	}
	.pulse-value {
		font-size: 14px;
		font-weight: 700;
		color: var(--c-text, #e5edf5);
	}
	.pulse-cell.empty .pulse-value {
		color: var(--c-faint, #64748b);
	}
	.pulse-delta {
		font-size: 9px;
		color: var(--c-muted, #94a3b8);
	}
	.pulse-delta.up {
		color: var(--c-success, #9be0b4);
	}
	.pulse-delta.down {
		color: var(--c-danger, #f3a0a0);
	}
	.pulse-caption {
		position: absolute;
		left: 0;
		bottom: 0;
		font-size: 8.5px;
		letter-spacing: 0.04em;
		color: var(--c-faint, #64748b);
	}
</style>
