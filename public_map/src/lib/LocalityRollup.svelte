<!--
	LocalityRollup — the centerpiece of the D.5.27 Localities screen (ADR-0032).
	A sortable table with one row per locality. The headline column is the
	posting count under the current NON-geographic filters (geography is the
	variable here). Multi-select rows + "Show jobs" drills into the existing
	JobList on /browse via locality:<code> geography chips (ADR-0032 §4) with all
	non-geographic filters preserved. A one-click Remote-only preset serves the
	relocation use case. All math lives in localities.ts (unit-tested); this is a
	thin renderer. Every column carries a D.5.13 calc-traceback tooltip.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { mapState } from './store.svelte';
	import { loadLocalities, loadCostOfLiving } from './data';
	import { stateRppFromCol, type StateRpp } from './compensation';
	import { writeFiltersToSearchParams } from './filters';
	import {
		computeLocalityRollup,
		localityMetaFromGeoJson,
		sortRollup,
		rollupTotals,
		formatPayPlanMix,
		gsRealPay,
		type LocalityMeta,
		type LocalityRollupRow,
		type SortKey,
		type SortDir
	} from './localities';
	import InfoTooltip from './InfoTooltip.svelte';

	// Selection is owned by the parent route so the paired LocalityMiniMap and
	// this table share one set (row ↔ polygon highlight is two-way).
	let { selected, onToggle }: { selected: Set<string>; onToggle: (code: string) => void } = $props();

	let meta = $state<Map<string, LocalityMeta>>(new Map());
	let stateRpp = $state<Record<string, StateRpp>>({});

	onMount(() => {
		void loadLocalities().then((fc) => (meta = localityMetaFromGeoJson(fc)));
		void loadCostOfLiving().then((col) => (stateRpp = stateRppFromCol(col)));
	});

	let sortKey = $state<SortKey>('postings');
	let sortDir = $state<SortDir>('desc');
	// Opt-in GS-anchored purchasing-power column (ADR-0032 §2/§6), off by default
	// because it only applies to GS postings (~70%).
	let showGs = $state(false);

	const rows = $derived(
		sortRollup(
			computeLocalityRollup(mapState.allJobs, mapState.allJobDetails, meta, mapState.filters, { stateRpp }),
			sortKey,
			sortDir
		)
	);
	const totals = $derived(rollupTotals(rows));
	const remoteOnly = $derived(mapState.filters.remote === 'remote');

	// Selected-set totals for the footer CTA.
	const selectedTotals = $derived.by(() => {
		let postings = 0;
		let localities = 0;
		for (const r of rows) {
			if (selected.has(r.code)) {
				postings += r.postings;
				localities += 1;
			}
		}
		return { postings, localities };
	});

	function setSort(key: SortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			// Sensible default direction per column: text asc, numbers desc.
			sortDir = key === 'name' ? 'asc' : 'desc';
		}
		// Sorting must not drop the multi-selection (ADR-0032 exit criterion):
		// `selected` is keyed by code, independent of row order, so it survives.
	}

	function toggleGs() {
		showGs = !showGs;
		// Don't leave the table sorted by a now-hidden column.
		if (!showGs && sortKey === 'gs') {
			sortKey = 'postings';
			sortDir = 'desc';
		}
	}
	function toggleRemotePreset() {
		mapState.filters = {
			...mapState.filters,
			remote: mapState.filters.remote === 'remote' ? 'any' : 'remote'
		};
	}

	// Drill-in: scope the existing JobList to the chosen localities via geography
	// chips (ADR-0032 §4 — no new filter primitive), preserving every
	// non-geographic filter and dropping radius chips (geographic). We encode the
	// resulting filters into the /browse URL rather than only mutating the store:
	// /browse's onMount hydrates its view FROM the URL (applySharedView), which
	// would otherwise reset the store filters we just set. Encoding also makes the
	// drilled-in view shareable. No viewport param is emitted, so /browse opens at
	// its national default and the (viewport-scoped) list shows every selected
	// locality's postings.
	function drillInto(codes: string[]) {
		if (codes.length === 0) return;
		const params = new URLSearchParams();
		writeFiltersToSearchParams(params, {
			...mapState.filters,
			geographies: codes.map((c) => `locality:${c}`),
			radii: []
		});
		mapState.listView = null;
		void goto(`/browse?${params.toString()}`);
	}

	function showSelected() {
		drillInto([...selected]);
	}
	// Single-row click is a shortcut: drill into just that locality (ADR-0032 §4).
	function rowShortcut(code: string) {
		drillInto([code]);
	}

	function fmtMoney(v: number | null): string {
		return v == null ? '—' : `$${Math.round(v).toLocaleString('en-US')}`;
	}
	function payRange(r: LocalityRollupRow): string {
		if (r.salaryMin == null && r.salaryMax == null) return '—';
		return `${fmtMoney(r.salaryMin)} – ${fmtMoney(r.salaryMax)}`;
	}
	function sortIndicator(key: SortKey): string {
		if (sortKey !== key) return '';
		return sortDir === 'asc' ? ' ▲' : ' ▼';
	}
</script>

<section class="rollup" aria-label="Locality rollup">
	<div class="head">
		<div class="summary">
			<strong>{totals.localities.toLocaleString()}</strong> localities ·
			<strong>{totals.postings.toLocaleString()}</strong> postings under the current filters
			<InfoTooltip title="What this table shows" align="start">
				<span
					>One row per OPM locality pay area. Counts, pay ranges, and pay-plan mix reflect every active
					filter EXCEPT geography — geography is the variable you're comparing here. Add a country,
					agency, series, grade, etc. filter and the whole table re-tallies.</span
				>
				<span class="src">Source: open USAJOBS postings in the current bundle, grouped by locality_code.</span>
			</InfoTooltip>
		</div>
		<div class="toggles">
			<button
				type="button"
				class="preset"
				class:on={showGs}
				onclick={toggleGs}
				aria-pressed={showGs}
				title="Show a GS-13 purchasing-power column (GS postings only)"
			>
				{showGs ? '✓ GS purchasing power' : 'GS purchasing power'}
			</button>
			<button
				type="button"
				class="preset"
				class:on={remoteOnly}
				onclick={toggleRemotePreset}
				aria-pressed={remoteOnly}
				title="Show only remote-eligible postings"
			>
				{remoteOnly ? '✓ Remote-only' : 'Remote-only'}
			</button>
		</div>
	</div>

	{#if rows.length === 0}
		<p class="empty" role="status">
			No postings match the current filters. Adjust filters (or clear the Remote-only preset) to see
			localities.
		</p>
	{:else}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th class="cb" aria-label="Select"></th>
						<th>
							<button type="button" class="sort" onclick={() => setSort('name')}
								>Locality{sortIndicator('name')}</button
							>
						</th>
						<th class="num">
							<button type="button" class="sort" onclick={() => setSort('postings')}
								>Postings{sortIndicator('postings')}</button
							>
						</th>
						<th class="num">
							<button type="button" class="sort" onclick={() => setSort('pay')}>Pay range{sortIndicator('pay')}</button>
							<InfoTooltip title="Posted pay range" align="end">
								<span
									>Lowest posted minimum to highest posted maximum across this locality's matching
									postings — pulled from each posting's salary, so it works for every pay plan (not a
									GS anchor).</span
								>
								<span class="src">Source: USAJOBS PositionRemuneration (salary_min / salary_max).</span>
							</InfoTooltip>
						</th>
						<th>
							Pay-plan mix
							<InfoTooltip title="Pay-plan mix" align="end">
								<span>Share of this locality's matching postings by pay plan. GS-family coverage is called out because pay-anchored metrics only apply to GS postings (~70% nationally).</span>
								<span class="src">Source: USAJOBS pay_plan on each posting.</span>
							</InfoTooltip>
						</th>
						<th class="num">
							<button type="button" class="sort" onclick={() => setSort('rpp')}>Cost of living{sortIndicator('rpp')}</button>
							<InfoTooltip title="Cost of living (RPP)" align="end">
								<span
									>BEA Regional Price Parities, where 100 = U.S. average. Uses the locality's own RPP
									when available, otherwise falls back to its primary state's RPP (flagged
									"approx").</span
								>
								<span class="src">Source: BEA Regional Price Parities (cost_of_living_index).</span>
							</InfoTooltip>
						</th>
						{#if showGs}
							<th class="num">
								<button type="button" class="sort" onclick={() => setSort('gs')}>GS-13 real pay{sortIndicator('gs')}</button>
								<InfoTooltip title="GS-13 purchasing power" align="end">
									<span
										>GS-13 step 1 locality-adjusted pay expressed in U.S.-average-cost dollars —
										i.e. pay ÷ (RPP ÷ 100). Higher means a GS-13 paycheck stretches further.
										<strong>GS-only</strong>: each row shows what share of its postings are GS, since
										non-GS plans aren't on the GS table.</span
									>
									<span class="formula">real_pay = gs13_step1_locality ÷ (RPP ÷ 100)</span>
									<span class="src">Source: OPM GS table × locality % (export), BEA RPP. Reuses the same GS pay figure shown on the map.</span>
								</InfoTooltip>
							</th>
						{/if}
					</tr>
				</thead>
				<tbody>
					{#each rows as r (r.code)}
						<tr class:selected={selected.has(r.code)}>
							<td class="cb">
								<input
									type="checkbox"
									checked={selected.has(r.code)}
									onchange={() => onToggle(r.code)}
									aria-label="Select {r.name}"
								/>
							</td>
							<td>
								<button type="button" class="loc" onclick={() => rowShortcut(r.code)} title="Show postings in {r.name}">
									{r.name}
								</button>
								<span class="code">{r.code}</span>
							</td>
							<td class="num strong">{r.postings.toLocaleString()}</td>
							<td class="num">{payRange(r)}</td>
							<td class="mix">
								{formatPayPlanMix(r.payPlanMix)}
								<span class="gs-cov">GS {r.gsCoveragePct}%</span>
							</td>
							<td class="num">
								{r.rppOverall == null ? '—' : r.rppOverall.toFixed(1)}
								{#if r.rppApproximate}<span class="approx" title={r.rppState ? `From ${r.rppState} state RPP` : 'Approximate'}>approx</span>{/if}
							</td>
							{#if showGs}
								{@const gp = gsRealPay(r)}
								<td class="num">
									{gp == null ? '—' : fmtMoney(gp)}
									{#if gp != null}<span class="gs-cov" title="Share of this locality's postings on a GS plan">GS {r.gsCoveragePct}%</span>{/if}
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div class="footer">
			{#if selectedTotals.localities > 0}
				<button type="button" class="show-jobs" onclick={showSelected}>
					Show {selectedTotals.postings.toLocaleString()} jobs in {selectedTotals.localities} localit{selectedTotals.localities === 1 ? 'y' : 'ies'}
				</button>
			{:else}
				<span class="hint">Select localities to drill into their postings, or click a locality name.</span>
			{/if}
		</div>
	{/if}
</section>

<style>
	.rollup {
		display: flex;
		flex-direction: column;
		min-height: 0;
		gap: 0.6rem;
		color: var(--c-text, #e5edf5);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.summary {
		font-size: 13px;
		color: var(--c-text-2, #cfd9e6);
	}
	.summary strong {
		color: var(--c-text, #e5edf5);
	}
	.toggles {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
	}
	.preset {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.35rem 0.7rem;
		border-radius: 999px;
		cursor: pointer;
		white-space: nowrap;
	}
	.preset.on {
		border-color: var(--c-accent-dim, #4979b3);
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
	}
	.empty {
		padding: 1.5rem 0.75rem;
		text-align: center;
		color: var(--c-muted, #94a3b8);
	}
	.table-wrap {
		overflow-x: auto;
		overflow-y: auto;
		min-height: 0;
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
	}
	thead th {
		position: sticky;
		top: 0;
		background: var(--c-panel, rgba(14, 23, 38, 0.96));
		text-align: left;
		padding: 0.5rem 0.6rem;
		border-bottom: 1px solid var(--c-border, #2a3a52);
		font-weight: 600;
		color: var(--c-muted, #94a3b8);
		white-space: nowrap;
		z-index: 1;
	}
	th.num,
	td.num {
		text-align: right;
		white-space: nowrap;
	}
	th.cb,
	td.cb {
		width: 1.8rem;
		text-align: center;
	}
	.sort {
		appearance: none;
		background: none;
		border: none;
		color: inherit;
		font: inherit;
		font-weight: 600;
		cursor: pointer;
		padding: 0;
	}
	.sort:hover {
		color: var(--c-accent, #7bd0f2);
	}
	tbody td {
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--c-border-subtle, #22344c);
		vertical-align: top;
	}
	tbody tr:hover {
		background: var(--c-row-hover, rgba(28, 42, 64, 0.85));
	}
	tbody tr.selected {
		background: var(--c-accent-bg, rgba(123, 208, 242, 0.08));
	}
	td.strong {
		font-weight: 700;
		color: var(--c-text, #e5edf5);
	}
	.loc {
		appearance: none;
		background: none;
		border: none;
		color: var(--c-accent, #7bd0f2);
		font: inherit;
		text-align: left;
		cursor: pointer;
		padding: 0;
	}
	.loc:hover {
		text-decoration: underline;
	}
	.code {
		display: inline-block;
		margin-left: 0.35rem;
		font-size: 10px;
		color: var(--c-faint, #64748b);
	}
	.mix {
		color: var(--c-text-2, #cfd9e6);
		min-width: 12rem;
	}
	.gs-cov {
		display: inline-block;
		margin-left: 0.35rem;
		font-size: 10px;
		color: var(--c-muted, #94a3b8);
	}
	.approx {
		display: inline-block;
		margin-left: 0.3rem;
		font-size: 10px;
		font-style: italic;
		color: var(--c-warn, #f0c878);
	}
	.footer {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.5rem;
		padding-top: 0.2rem;
	}
	.hint {
		font-size: 12px;
		color: var(--c-muted, #94a3b8);
	}
	.show-jobs {
		appearance: none;
		border: 1px solid var(--c-accent-dim, #4979b3);
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
		font: inherit;
		font-size: 13px;
		font-weight: 700;
		padding: 0.5rem 1rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.show-jobs:hover {
		background: var(--c-accent-bg, rgba(123, 208, 242, 0.28));
	}
	.src {
		display: block;
		margin-top: 0.3rem;
		font-size: 10px;
		color: var(--c-faint, #64748b);
	}
	.formula {
		display: block;
		margin-top: 0.3rem;
		font-size: 10px;
		font-family: ui-monospace, monospace;
		color: var(--c-muted, #94a3b8);
	}
</style>
