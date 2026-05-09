<!--
	D.5.17 — Personal compensation / cost-of-living comparator (per ADR-0028).
	Drawer launched from a "Pay Compare" pill in the masthead. Local-only;
	no persistence beyond the open drawer.
-->
<script lang="ts">
	import { mapState } from './store.svelte';
	import { loadPayTables, loadLocalities, loadCostOfLiving } from './data';
	import {
		compute,
		gsBasePay,
		localitiesFromGeoJson,
		stateRppFromCol,
		STATE_NAMES,
		type CompMode,
		type CompResult,
		type LocalityInfo,
		type StateRpp
	} from './compensation';
	import type { PayTables } from './data';
	import { money, percent } from './format';

	let mode = $state<CompMode>('gs');
	let grade = $state<string>('13');
	let step = $state<string>('1');
	let localityCode = $state<string>('DCB');
	let customAnnual = $state<string>('');
	let customStateCode = $state<string>('');
	let targetStateCode = $state<string>('');

	let payTables = $state<PayTables>({});
	let localities = $state<LocalityInfo[]>([]);
	let stateRpp = $state<Record<string, StateRpp>>({});
	let loaded = $state<boolean>(false);

	const year = $derived(mapState.manifest?.reference_year ?? 2025);

	$effect(() => {
		if (!mapState.compareOpen || loaded) return;
		Promise.all([loadPayTables(), loadLocalities(), loadCostOfLiving()]).then(
			([pt, locs, col]) => {
				payTables = pt;
				localities = localitiesFromGeoJson(locs);
				stateRpp = stateRppFromCol(col);
				loaded = true;
				if (!localityCode && localities.length > 0) localityCode = localities[0].code;
			}
		);
	});

	const grades = ['1','2','3','4','5','6','7','8','9','10','11','12','13','14','15'];
	const steps = ['1','2','3','4','5','6','7','8','9','10'];

	const stateOptions = $derived(
		Object.keys(stateRpp)
			.filter((code) => STATE_NAMES[code])
			.sort((a, b) => STATE_NAMES[a].localeCompare(STATE_NAMES[b]))
	);

	const result = $derived<CompResult>(
		compute({
			mode,
			year,
			grade,
			step,
			localityCode,
			customAnnual: customAnnual ? Number(customAnnual.replace(/[^0-9.]/g, '')) : undefined,
			customStateCode: customStateCode || undefined,
			targetStateCode: targetStateCode || undefined,
			payTables,
			localities,
			stateRpp
		})
	);

	const sourceLabel = $derived(buildSourceLabel(result));
	const targetLabel = $derived(targetStateCode ? STATE_NAMES[targetStateCode] : null);

	function buildSourceLabel(r: CompResult): string {
		if (r.breakdown.method === 'gs' && r.breakdown.locality_name) {
			return `GS-${grade} Step ${step} in ${r.breakdown.locality_name}`;
		}
		if (r.breakdown.method === 'custom' && r.source_state) {
			return `${money(r.annual_pay)} in ${STATE_NAMES[r.source_state] ?? r.source_state}`;
		}
		return 'Your pay';
	}

	function close() {
		mapState.compareOpen = false;
	}

	// Show GS pay preview as user adjusts grade/step (used to display alongside locality select).
	const gsBasePreview = $derived(
		grade && step ? gsBasePay(payTables, year, grade, step) : null
	);
</script>

{#if mapState.compareOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="overlay" onclick={close}></div>
	<aside class="drawer" aria-label="Pay and cost-of-living comparator">
		<div class="header">
			<h2>Pay & COL Compare</h2>
			<button type="button" class="close" onclick={close} aria-label="Close comparator">✕</button>
		</div>

		{#if !loaded}
			<p class="muted">Loading pay tables…</p>
		{:else}
			<fieldset class="mode-row">
				<legend>Pay basis</legend>
				<label>
					<input type="radio" name="comp-mode" value="gs" checked={mode === 'gs'} onchange={() => (mode = 'gs')} />
					GS schedule
				</label>
				<label>
					<input type="radio" name="comp-mode" value="custom" checked={mode === 'custom'} onchange={() => (mode = 'custom')} />
					Custom wage
				</label>
			</fieldset>

			{#if mode === 'gs'}
				<div class="row">
					<label class="field">
						<span>Grade</span>
						<select bind:value={grade}>
							{#each grades as g}
								<option value={g}>GS-{g}</option>
							{/each}
						</select>
					</label>
					<label class="field">
						<span>Step</span>
						<select bind:value={step}>
							{#each steps as s}
								<option value={s}>{s}</option>
							{/each}
						</select>
					</label>
				</div>
				<label class="field">
					<span>Locality</span>
					<select bind:value={localityCode}>
						{#each localities as l (l.code)}
							<option value={l.code}>{l.code} — {l.name} (+{percent(l.adjustment_pct)})</option>
						{/each}
					</select>
				</label>
				{#if gsBasePreview !== null}
					<p class="muted small">
						Base GS-{grade} step {step}: {money(gsBasePreview)} (before locality adjustment).
					</p>
				{/if}
			{:else}
				<label class="field">
					<span>Annual wage (USD)</span>
					<input
						type="text"
						inputmode="numeric"
						placeholder="e.g. 95000"
						bind:value={customAnnual}
					/>
				</label>
				<label class="field">
					<span>State you earn this in</span>
					<select bind:value={customStateCode}>
						<option value="">— pick a state —</option>
						{#each stateOptions as code}
							<option value={code}>{STATE_NAMES[code]}</option>
						{/each}
					</select>
				</label>
			{/if}

			<label class="field compare-field">
				<span>Compare to (target state)</span>
				<select bind:value={targetStateCode}>
					<option value="">— pick a state —</option>
					{#each stateOptions as code}
						<option value={code}>{STATE_NAMES[code]}</option>
					{/each}
				</select>
			</label>

			<section class="result" aria-live="polite">
				{#if result.annual_pay !== null}
					<div class="line">
						<strong>{sourceLabel}</strong>
						<span class="big">{money(result.annual_pay)}/yr</span>
					</div>
					{#if result.breakdown.method === 'gs'}
						<p class="small muted">
							{money(result.breakdown.gs_base)} base × (1 + {percent(result.breakdown.locality_adjustment_pct)})
						</p>
					{/if}

					{#if result.equivalent_pay !== null && targetLabel}
						<div class="equiv">
							<p>
								Equivalent in <strong>{targetLabel}</strong>:
								<span class="big">{money(result.equivalent_pay)}/yr</span>
							</p>
							<p class="small muted">
								{money(result.annual_pay)} × ({result.target_state_rpp} ÷ {result.source_state_rpp}) =
								{money(result.equivalent_pay)}
							</p>
							{#if result.source_state_rpp_approximate}
								<p class="small approx">
									Source RPP is the primary state for the locality; OPM localities can span multiple states, so this is approximate.
								</p>
							{/if}
						</div>
					{/if}
				{/if}

				{#if result.notes.length > 0}
					<ul class="notes">
						{#each result.notes as note}
							<li>{note}</li>
						{/each}
					</ul>
				{/if}

				{#if result.sources.length > 0}
					<details class="sources">
						<summary>Sources</summary>
						<ul>
							{#each result.sources as src}
								<li>{src}</li>
							{/each}
						</ul>
					</details>
				{/if}
			</section>
		{/if}
	</aside>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.45);
		z-index: 50;
	}
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(28rem, 100vw);
		background: var(--c-panel, rgba(14, 23, 38, 0.97));
		border-left: 1px solid var(--c-border, #2a3a52);
		z-index: 51;
		padding: 1rem 1.1rem;
		overflow-y: auto;
		color: var(--c-text, #e5edf5);
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
	}
	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
	}
	h2 { margin: 0; font-size: 14px; }
	.close {
		appearance: none;
		background: transparent;
		border: 1px solid var(--c-border, #2a3a52);
		color: var(--c-text-2, #cfd9e6);
		border-radius: 999px;
		width: 1.7rem;
		height: 1.7rem;
		cursor: pointer;
	}
	.close:hover { color: var(--c-accent, #7bd0f2); border-color: var(--c-accent, #7bd0f2); }
	.muted { color: var(--c-muted, #94a3b8); }
	.small { font-size: 11px; }
	.mode-row {
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		padding: 0.5rem 0.75rem;
		display: flex;
		gap: 1rem;
	}
	.mode-row legend {
		padding: 0 0.35rem;
		font-size: 11px;
		color: var(--c-muted);
	}
	.mode-row label {
		display: flex;
		gap: 0.35rem;
		align-items: center;
		font-size: 12px;
	}
	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.6rem;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 12px;
	}
	.field span { color: var(--c-text-2, #cfd9e6); font-size: 11px; }
	.field input, .field select {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text, #e5edf5);
		padding: 0.4rem 0.55rem;
		border-radius: 6px;
		font: inherit;
	}
	.field input:focus, .field select:focus { outline: 2px solid var(--c-accent, #7bd0f2); outline-offset: 1px; }
	.compare-field { border-top: 1px dashed var(--c-border-subtle, #22344c); padding-top: 0.7rem; margin-top: 0.2rem; }

	.result {
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 8px;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		padding: 0.75rem 0.85rem;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}
	.line {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.5rem;
	}
	.big { font-size: 18px; color: var(--c-accent, #7bd0f2); font-weight: 600; }
	.equiv {
		border-top: 1px solid var(--c-border-subtle, #22344c);
		padding-top: 0.55rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.equiv p { margin: 0; }
	.approx { color: var(--c-warn, #f0c878); }
	.notes {
		margin: 0;
		padding-left: 1rem;
		font-size: 11px;
		color: var(--c-warn, #f0c878);
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.sources summary {
		cursor: pointer;
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
	}
	.sources ul {
		margin: 0.35rem 0 0;
		padding-left: 1rem;
		font-size: 11px;
		color: var(--c-text-2, #cfd9e6);
	}
</style>
