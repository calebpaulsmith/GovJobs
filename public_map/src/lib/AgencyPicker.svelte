<!--
	Code-backed agency multi-select. Typing matches an agency by code, name,
	department, or alias (so "FEMA" finds HSCB) and the user commits a chip
	from the dropdown — free text alone never filters. Mirrors the proven
	picker in FilterPanel.svelte; writes to the shared mapState.filters.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { mapState } from './store.svelte';
	import { loadAgencyOptions, type AgencyOption } from './data';

	let agencyOptions = $state<AgencyOption[]>([]);
	let search = $state('');

	onMount(() => {
		void loadAgencyOptions().then((opts) => {
			agencyOptions = opts.filter((o) => o.code);
		});
	});

	function searchText(o: AgencyOption): string {
		return [o.code, o.name, o.label, o.department_name, ...(o.aliases ?? [])]
			.map((v) => String(v ?? '').toLowerCase())
			.join(' ');
	}

	const selected = $derived(
		agencyOptions.filter((o) => o.code && mapState.filters.agencies.includes(o.code))
	);

	const results = $derived.by(() => {
		const q = search.trim().toLowerCase();
		if (!q) return [] as AgencyOption[];
		const chosen = new Set(mapState.filters.agencies);
		return agencyOptions
			.filter((o) => o.code && !chosen.has(o.code) && searchText(o).includes(q))
			.sort((a, b) => b.postings - a.postings)
			.slice(0, 8);
	});

	function add(o: AgencyOption) {
		if (!o.code || mapState.filters.agencies.includes(o.code)) return;
		// Reassign the whole filters object so every $derived re-runs.
		mapState.filters = {
			...mapState.filters,
			agencies: [...mapState.filters.agencies, o.code]
		};
		search = '';
	}

	function remove(code: string) {
		mapState.filters = {
			...mapState.filters,
			agencies: mapState.filters.agencies.filter((c) => c !== code)
		};
	}

	function onEnter(e: KeyboardEvent) {
		if (e.key !== 'Enter') return;
		e.preventDefault();
		if (results.length > 0) add(results[0]);
	}
</script>

<div class="agency-picker">
	<label class="field-label" for="agency-search">Agency</label>
	<input
		id="agency-search"
		class="search"
		type="search"
		placeholder="Type an agency — FEMA, HSCB, Homeland Security…"
		bind:value={search}
		onkeydown={onEnter}
		autocomplete="off"
	/>

	{#if results.length > 0}
		<ul class="results" role="listbox">
			{#each results as o (o.code)}
				<li>
					<button type="button" onclick={() => add(o)}>
						<span class="r-name">{o.name}</span>
						<span class="r-meta">{o.code} · {o.department_name ?? '—'} · {o.postings.toLocaleString()} postings</span>
					</button>
				</li>
			{/each}
		</ul>
	{:else if search.trim()}
		<p class="no-match">No agency matches “{search.trim()}”. Try a department name or the agency code.</p>
	{/if}

	{#if selected.length > 0}
		<div class="chips">
			{#each selected as o (o.code)}
				<button type="button" class="chip" onclick={() => remove(o.code ?? '')}>
					{o.name} <span class="x" aria-hidden="true">×</span>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.agency-picker {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.field-label {
		font-size: 9px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--c-accent, #7bd0f2);
	}
	.search {
		width: 100%;
		box-sizing: border-box;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 6px;
		padding: 0.5rem 0.6rem;
		font-size: 13px;
		outline: none;
	}
	.search:focus {
		border-color: var(--c-accent, #7bd0f2);
	}
	.results {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		max-height: 14rem;
		overflow-y: auto;
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 6px;
		background: var(--c-panel, rgba(14, 23, 38, 0.96));
		padding: 0.2rem;
	}
	.results button {
		appearance: none;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		border-radius: 4px;
		padding: 0.4rem 0.5rem;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.results button:hover {
		background: var(--c-row-hover, rgba(28, 42, 64, 0.85));
	}
	.r-name {
		font-size: 12.5px;
		font-weight: 600;
		color: var(--c-text, #e5edf5);
	}
	.r-meta {
		font-size: 10px;
		color: var(--c-muted, #94a3b8);
	}
	.no-match {
		margin: 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
		line-height: 1.4;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.chip {
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border: 1px solid var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
		padding: 0.22rem 0.55rem;
		border-radius: 999px;
		font-size: 11px;
		font-weight: 600;
		cursor: pointer;
	}
	.chip .x {
		color: var(--c-muted, #94a3b8);
	}
</style>
