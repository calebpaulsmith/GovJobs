<!--
	Shared filter inputs for the public map. Rendered inside FilterPanel.svelte
	(the /map drawer) and FilterSheet.svelte (the /browse mobile sheet) so both
	surfaces present the EXACT same fields and write the one mapState.filters
	store — there is no second filter implementation to drift. Positioning,
	open/close chrome, and URL round-trip live in the wrappers, not here.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { mapState } from './store.svelte';
	import { DEFAULT_FILTERS, activeFilterCount, type JobFilters } from './filters';
	import { loadAgencyOptions, type AgencyOption } from './data';

	let agencyOptions = $state<AgencyOption[]>([]);
	let agencySearch = $state('');
	let agencyValidation = $state('');

	onMount(() => {
		void loadAgencyOptions().then((options) => {
			agencyOptions = options.filter((option) => option.code);
		});
	});

	function setFilter<K extends keyof JobFilters>(key: K, value: JobFilters[K]) {
		// Mutate the field on the proxy AND reassign the parent so every
		// consumer that captured the prior mapState.filters reference re-runs.
		(mapState.filters as JobFilters)[key] = value;
		mapState.filters = {
			...mapState.filters,
			agencies: [...mapState.filters.agencies],
			geographies: [...mapState.filters.geographies]
		};
	}

	function selectedAgencyOptions(): AgencyOption[] {
		const selected = new Set(mapState.filters.agencies);
		return agencyOptions.filter((option) => option.code && selected.has(option.code));
	}

	function filteredAgencyOptions(): AgencyOption[] {
		const selected = new Set(mapState.filters.agencies);
		const query = agencySearch.trim().toLowerCase();
		return agencyOptions
			.filter((option) => option.code && !selected.has(option.code))
			.filter((option) => !query || agencySearchText(option).includes(query))
			.slice(0, 8);
	}

	function agencySearchText(option: AgencyOption): string {
		return [option.code, option.name, option.label, option.department_name, ...(option.aliases ?? [])]
			.map((value) => String(value ?? '').toLowerCase())
			.join(' ');
	}

	function addAgency(option: AgencyOption) {
		if (!option.code || mapState.filters.agencies.includes(option.code)) return;
		setFilter('agencies', [...mapState.filters.agencies, option.code]);
		agencySearch = '';
		agencyValidation = '';
	}

	function removeAgency(code: string) {
		setFilter('agencies', mapState.filters.agencies.filter((agency) => agency !== code));
	}

	function selectAgencyFromSearch() {
		const query = agencySearch.trim();
		if (!query) return;
		const normalized = query.toLowerCase();
		const match = agencyOptions.find((option) => {
			const aliases = option.aliases ?? [];
			return (
				String(option.code ?? '').toLowerCase() === normalized ||
				option.name.toLowerCase() === normalized ||
				aliases.some((alias) => alias.toLowerCase() === normalized)
			);
		}) ?? filteredAgencyOptions()[0];
		if (match) addAgency(match);
		else agencyValidation = 'Choose a listed agency or known alias; free-text agencies do not change results.';
	}

	function resetFilters() {
		mapState.filters = { ...DEFAULT_FILTERS, agencies: [], geographies: [] };
	}

	function removeGeo(geo: string) {
		setFilter('geographies', mapState.filters.geographies.filter((g) => g !== geo));
	}

	function geoLabel(geo: string): string {
		const sep = geo.indexOf(':');
		if (sep === -1) return geo;
		const type = geo.slice(0, sep);
		const code = geo.slice(sep + 1);
		return type === 'state' ? `State: ${code}` : type === 'locality' ? `Locality: ${code}` : geo;
	}
</script>

<div class="fields">
	<label>
		<span>Keyword</span>
		<input
			type="search"
			placeholder="title, agency, city…"
			value={mapState.filters.keyword}
			oninput={(e) => setFilter('keyword', e.currentTarget.value)}
		/>
	</label>

	<label>
		<span>Posted in last</span>
		<select
			value={mapState.filters.postedWithin}
			onchange={(e) => setFilter('postedWithin', e.currentTarget.value as JobFilters['postedWithin'])}
		>
			<option value="">Any time</option>
			<option value="1">1 day</option>
			<option value="3">3 days</option>
			<option value="7">7 days</option>
			<option value="30">30 days</option>
		</select>
	</label>

	<div class="agency-picker">
		<span>Agencies</span>
		<div class="chips" aria-label="Selected agencies">
			{#each selectedAgencyOptions() as option (option.code)}
				<button type="button" class="chip" onclick={() => removeAgency(option.code ?? '')}>
					{option.code} · {option.name}
					<strong aria-hidden="true">×</strong>
				</button>
			{/each}
		</div>
		<div class="agency-search">
			<input
				type="search"
				placeholder="Search FEMA, HSCB, DHS…"
				value={agencySearch}
				oninput={(e) => { agencySearch = e.currentTarget.value; agencyValidation = ''; }}
				onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); selectAgencyFromSearch(); } }}
			/>
			<button type="button" onclick={selectAgencyFromSearch}>Add</button>
		</div>
		{#if agencySearch.trim()}
			<div class="agency-results">
				{#each filteredAgencyOptions() as option (option.code)}
					<button type="button" onclick={() => addAgency(option)}>
						<strong>{option.code}</strong>
						<span>{option.name}</span>
						<small>{option.postings.toLocaleString()} postings{option.aliases?.length ? ` · aliases: ${option.aliases.join(', ')}` : ''}</small>
					</button>
				{/each}
			</div>
		{/if}
		{#if agencyValidation}<p class="validation">{agencyValidation}</p>{/if}
	</div>

	{#if mapState.filters.geographies.length > 0}
		<div class="geo-chips">
			<span>Geography scope</span>
			<div class="chips" aria-label="Active geography filters">
				{#each mapState.filters.geographies as geo (geo)}
					<button type="button" class="chip chip-geo" onclick={() => removeGeo(geo)}>
						{geoLabel(geo)}
						<strong aria-hidden="true">×</strong>
					</button>
				{/each}
			</div>
			<p class="geo-hint">Jobs outside these areas are hidden. Add areas with the "Add this area to my list" button on any state or locality.</p>
		</div>
	{/if}

	<div class="row">
		<label>
			<span>Series</span>
			<input
				type="text"
				inputmode="numeric"
				placeholder="0301"
				value={mapState.filters.series}
				oninput={(e) => setFilter('series', e.currentTarget.value)}
			/>
		</label>
	</div>

	<div class="row three">
		<label>
			<span>Grade min</span>
			<input type="number" min="1" max="15" value={mapState.filters.gradeMin} oninput={(e) => setFilter('gradeMin', e.currentTarget.value)} />
		</label>
		<label>
			<span>Grade max</span>
			<input type="number" min="1" max="15" value={mapState.filters.gradeMax} oninput={(e) => setFilter('gradeMax', e.currentTarget.value)} />
		</label>
		<label>
			<span>Pay plan</span>
			<input type="text" placeholder="GS" value={mapState.filters.payPlan} oninput={(e) => setFilter('payPlan', e.currentTarget.value.toUpperCase())} />
		</label>
	</div>

	<div class="row">
		<label>
			<span>Salary minimum</span>
			<input type="number" min="0" placeholder="90000" value={mapState.filters.salaryMin} oninput={(e) => setFilter('salaryMin', e.currentTarget.value)} />
		</label>
		<label>
			<span>Remote</span>
			<select value={mapState.filters.remote} onchange={(e) => setFilter('remote', e.currentTarget.value as JobFilters['remote'])}>
				<option value="any">Any</option>
				<option value="remote">Remote</option>
				<option value="hybrid">Hybrid</option>
				<option value="onsite">Onsite</option>
			</select>
		</label>
	</div>

	<label>
		<span>Hiring path</span>
		<input
			type="text"
			placeholder="public, vet, fed-competitive…"
			value={mapState.filters.hiringPath}
			oninput={(e) => setFilter('hiringPath', e.currentTarget.value)}
		/>
	</label>

	<div class="summary" aria-live="polite">
		<span>{mapState.filteredJobCount.toLocaleString()} of {mapState.totalJobCount.toLocaleString()} mapped posting locations shown</span>
		<button type="button" onclick={resetFilters} disabled={activeFilterCount(mapState.filters) === 0}>
			Reset
		</button>
	</div>
</div>

<style>
	.fields {
		display: block;
	}
	label,
	.row {
		display: grid;
		gap: 0.35rem;
	}
	.fields > label,
	.agency-picker,
	.geo-chips,
	.row {
		margin-bottom: 0.7rem;
	}
	.row {
		grid-template-columns: 1fr 0.7fr;
		gap: 0.65rem;
	}
	.row.three {
		grid-template-columns: repeat(3, 1fr);
	}
	span {
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
	}
	input,
	select {
		width: 100%;
		box-sizing: border-box;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 6px;
		background: var(--c-row-bg, rgba(8, 13, 22, 0.85));
		color: var(--c-text, #e5edf5);
		padding: 0.45rem 0.55rem;
		font: inherit;
	}
	input:focus,
	select:focus,
	.agency-search button:focus-visible,
	.agency-results button:focus-visible,
	.chip:focus-visible,
	.summary button:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.agency-picker,
	.geo-chips {
		display: grid;
		gap: 0.45rem;
	}
	.geo-hint {
		margin: 0;
		font-size: 10px;
		color: var(--c-faint, #64748b);
		line-height: 1.4;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
	}
	.chip {
		appearance: none;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 999px;
		background: var(--c-accent-bg-strong, rgba(73, 121, 179, 0.2));
		color: var(--c-text, #e5edf5);
		padding: 0.28rem 0.5rem;
		cursor: pointer;
		font: inherit;
		font-size: 11px;
	}
	.chip-geo {
		border-color: #5e9a4a;
		background: rgba(94, 154, 74, 0.15);
		color: var(--c-text, #e5edf5);
	}
	.chip strong {
		margin-left: 0.35rem;
		color: var(--c-text, #fff);
	}
	.agency-search {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.35rem;
	}
	.agency-search button,
	.agency-results button {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 6px;
		background: var(--c-row-hover, rgba(28, 42, 64, 0.85));
		color: var(--c-text-2, #d8e6f3);
		cursor: pointer;
		font: inherit;
	}
	.agency-search button {
		padding: 0 0.7rem;
	}
	.agency-results {
		display: grid;
		gap: 0.25rem;
		max-height: 10rem;
		overflow: auto;
	}
	.agency-results button {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.1rem 0.45rem;
		text-align: left;
		padding: 0.45rem 0.55rem;
	}
	.agency-results button strong {
		color: var(--c-text, #fff);
	}
	.agency-results button span {
		color: var(--c-text-2, #d8e6f3);
	}
	.agency-results button small {
		grid-column: 2;
		color: var(--c-muted, #94a3b8);
	}
	.validation {
		margin: 0;
		color: #fbbf24;
	}
	.summary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding-top: 0.45rem;
		border-top: 1px solid var(--c-border-subtle, #22344c);
	}
	.summary button {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 999px;
		background: var(--c-row-hover, rgba(28, 42, 64, 0.75));
		color: var(--c-text-2, #cfd9e6);
		padding: 0.35rem 0.7rem;
		cursor: pointer;
	}
	.summary button:disabled {
		cursor: not-allowed;
		opacity: 0.45;
	}
	@media (max-width: 719px) {
		.row,
		.row.three {
			grid-template-columns: 1fr;
		}
	}
</style>
