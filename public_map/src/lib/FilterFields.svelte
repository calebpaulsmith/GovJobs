<!--
	Shared filter inputs for the public map. Rendered inside FilterPanel.svelte
	(the /map drawer) and FilterSheet.svelte (the /browse mobile sheet) so both
	surfaces present the EXACT same fields and write the one mapState.filters
	store — there is no second filter implementation to drift. Positioning,
	open/close chrome, and URL round-trip live in the wrappers, not here.

	Agency, pay plan, hiring path, and series are all code-backed multi-selects
	(MultiSelect.svelte). Agency offers the full catalog (with alias search so
	"FEMA" finds HSCB); pay plan, hiring path, and series offer only the values
	present in the CURRENTLY FILTERED results — see filterFacets.ts.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { mapState } from './store.svelte';
	import { DEFAULT_FILTERS, activeFilterCount, type JobFilters } from './filters';
	import { loadAgencyOptions, loadSeriesOptions, type AgencyOption } from './data';
	import {
		payPlanFacet,
		hiringPathFacet,
		seriesFacet,
		payPlanLabel,
		hiringPathLabel,
		type FacetOption
	} from './filterFacets';
	import { ungeocodedFilteredDetails } from './filters';
	import MultiSelect from './MultiSelect.svelte';

	// Open postings the map could not place (no geocodable duty station), narrowed
	// by the active filters (geography/radius dropped — they can't apply to a job
	// with no location). Surfaced at the bottom of the filters as an escape hatch
	// to the swipe-away list. Uses the same helper the list reads, so the count
	// and the rows always agree.
	const ungeocodedCount = $derived(
		ungeocodedFilteredDetails(mapState.allJobDetails, mapState.allJobs, mapState.filters).length
	);

	let agencyOptions = $state<AgencyOption[]>([]);
	let seriesLabels = $state<Record<string, string>>({});

	onMount(() => {
		void loadAgencyOptions().then((options) => {
			agencyOptions = options.filter((option) => option.code);
		});
		void loadSeriesOptions().then((options) => {
			const labels: Record<string, string> = {};
			for (const option of options) labels[option.code] = option.label;
			seriesLabels = labels;
		});
	});

	// All loaded postings (deduped, one per job) — the corpus the facet
	// narrowing tallies. Empty until Map.svelte finishes loading the bundle.
	const jobs = $derived(Object.values(mapState.allJobDetails));

	// Agency uses the full catalog (so alias search keeps working regardless of
	// the current results); the other three narrow to what's reachable.
	const agencyFacetOptions = $derived<FacetOption[]>(
		agencyOptions
			.filter((o) => o.code)
			.map((o) => ({
				value: o.code as string,
				label: o.name,
				sub: [o.code, o.department_name].filter(Boolean).join(' · '),
				count: o.postings,
				keywords: [o.code, o.department_name, ...(o.aliases ?? [])].join(' ')
			}))
			.sort((a, b) => b.count - a.count)
	);

	const payPlanOptions = $derived(payPlanFacet(jobs, mapState.filters));
	const hiringPathOptions = $derived(hiringPathFacet(jobs, mapState.filters));
	const seriesOptions = $derived(seriesFacet(jobs, mapState.filters, seriesLabels));

	function agencyLabel(code: string): string {
		const upper = code.toUpperCase();
		const opt = agencyOptions.find((o) => (o.code ?? '').toUpperCase() === upper);
		return opt?.name ?? code;
	}
	function seriesLabel(code: string): string {
		const title = seriesLabels[code];
		return title && title !== code ? `${code} — ${title}` : code;
	}

	// Single writer: reassign the whole filters object (with fresh array copies)
	// so every consumer that captured the prior mapState.filters reference — and
	// every $derived — re-runs. Mirrors the pattern proven in ActiveFilterStrip.
	function patchFilters(patch: Partial<JobFilters>) {
		mapState.filters = {
			...mapState.filters,
			...patch,
			agencies: [...(patch.agencies ?? mapState.filters.agencies)],
			series: [...(patch.series ?? mapState.filters.series)],
			payPlans: [...(patch.payPlans ?? mapState.filters.payPlans)],
			hiringPaths: [...(patch.hiringPaths ?? mapState.filters.hiringPaths)],
			geographies: [...(patch.geographies ?? mapState.filters.geographies)]
		};
	}

	function setFilter<K extends keyof JobFilters>(key: K, value: JobFilters[K]) {
		patchFilters({ [key]: value } as Partial<JobFilters>);
	}

	type ListKey = 'agencies' | 'series' | 'payPlans' | 'hiringPaths';
	function addValue(key: ListKey, value: string) {
		const current = mapState.filters[key];
		if (!value || current.includes(value)) return;
		patchFilters({ [key]: [...current, value] } as Partial<JobFilters>);
	}
	function removeValue(key: ListKey, value: string) {
		patchFilters({ [key]: mapState.filters[key].filter((v) => v !== value) } as Partial<JobFilters>);
	}

	function resetFilters() {
		mapState.filters = {
			...DEFAULT_FILTERS,
			agencies: [],
			series: [],
			payPlans: [],
			hiringPaths: [],
			geographies: []
		};
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

	<div class="facet">
		<MultiSelect
			label="Agencies"
			selected={mapState.filters.agencies}
			options={agencyFacetOptions}
			chipLabel={agencyLabel}
			placeholder="Search FEMA, HSCB, Homeland Security…"
			emptyHint="Type an agency name, code, or known alias."
			onAdd={(v) => addValue('agencies', v)}
			onRemove={(v) => removeValue('agencies', v)}
		/>
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

	<div class="facet">
		<MultiSelect
			label="Series"
			selected={mapState.filters.series}
			options={seriesOptions}
			chipLabel={seriesLabel}
			placeholder="Search series — 0301, IT, nurse…"
			emptyHint="Series appear once postings load; the list narrows to your other filters."
			onAdd={(v) => addValue('series', v)}
			onRemove={(v) => removeValue('series', v)}
		/>
	</div>

	<div class="row">
		<label>
			<span>Grade min</span>
			<input type="number" min="1" max="15" value={mapState.filters.gradeMin} oninput={(e) => setFilter('gradeMin', e.currentTarget.value)} />
		</label>
		<label>
			<span>Grade max</span>
			<input type="number" min="1" max="15" value={mapState.filters.gradeMax} oninput={(e) => setFilter('gradeMax', e.currentTarget.value)} />
		</label>
	</div>

	<div class="facet">
		<MultiSelect
			label="Pay plan"
			selected={mapState.filters.payPlans}
			options={payPlanOptions}
			chipLabel={payPlanLabel}
			placeholder="Search GS, Wage Grade, VA Nurse…"
			emptyHint="Pay plans appear once postings load; the list narrows to your other filters."
			onAdd={(v) => addValue('payPlans', v)}
			onRemove={(v) => removeValue('payPlans', v)}
		/>
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

	<div class="facet">
		<MultiSelect
			label="Hiring path"
			selected={mapState.filters.hiringPaths}
			options={hiringPathOptions}
			chipLabel={hiringPathLabel}
			placeholder="Search public, veterans, military spouse…"
			emptyHint="Hiring paths appear once postings load; the list narrows to your other filters."
			onAdd={(v) => addValue('hiringPaths', v)}
			onRemove={(v) => removeValue('hiringPaths', v)}
		/>
	</div>

	<div class="summary" aria-live="polite">
		<span>{mapState.filteredJobCount.toLocaleString()} of {mapState.totalJobCount.toLocaleString()} mapped posting locations shown</span>
		<button type="button" onclick={resetFilters} disabled={activeFilterCount(mapState.filters) === 0}>
			Reset
		</button>
	</div>

	{#if ungeocodedCount > 0}
		<button type="button" class="ungeo" onclick={() => (mapState.ungeocodedOpen = true)}>
			<span class="ungeo-count">{ungeocodedCount.toLocaleString()}</span>
			posting{ungeocodedCount === 1 ? '' : 's'} not on the map
			<span class="ungeo-hint">View list →</span>
		</button>
	{/if}
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
	.facet,
	.geo-chips,
	.row {
		margin-bottom: 0.7rem;
	}
	.row {
		grid-template-columns: 1fr 1fr;
		gap: 0.65rem;
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
	.chip:focus-visible,
	.summary button:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
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
	.ungeo {
		appearance: none;
		width: 100%;
		box-sizing: border-box;
		margin-top: 0.6rem;
		display: flex;
		align-items: center;
		gap: 0.4rem;
		border: 1px dashed var(--c-border-input, #2c4870);
		border-radius: 8px;
		background: var(--c-row-bg, rgba(8, 13, 22, 0.85));
		color: var(--c-text-2, #cfd9e6);
		padding: 0.5rem 0.65rem;
		cursor: pointer;
		font: inherit;
		font-size: 12px;
		text-align: left;
	}
	.ungeo:hover {
		border-color: var(--c-accent, #7bd0f2);
	}
	.ungeo:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.ungeo-count {
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 11px;
		font-weight: 700;
		padding: 0.05rem 0.45rem;
		border-radius: 999px;
	}
	.ungeo-hint {
		margin-left: auto;
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
		white-space: nowrap;
	}
	@media (max-width: 719px) {
		.row {
			grid-template-columns: 1fr;
		}
	}
</style>
