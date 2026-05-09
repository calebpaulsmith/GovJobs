<!--
	Filtered list of job postings inside a polygon scope (state, locality,
	county, CBSA). Honors the active filter chips so the list matches the map.
	Paginated at 20/page with a sort selector so large lists (e.g. a state
	with thousands of postings) stay responsive.
-->
<script lang="ts">
	import { mapState, type ListView } from './store.svelte';
	import { loadJobs, loadJobDetailsIndex, type Feature, type JobDetails } from './data';
	import { filterJobs } from './filters';
	import { LAYER_IDS } from './layers';
	import { gradeRange, propString, salaryRange, urgencyBadge } from './format';
	import QuickAdd from './QuickAdd.svelte';

	let { listView }: { listView: ListView } = $props();
	let allJobs = $state<{ type: 'FeatureCollection'; features: Feature[] } | null>(null);
	let details = $state<Record<string, JobDetails>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	type SortKey = 'closing_soon' | 'closing_late' | 'salary_high' | 'salary_low' | 'title' | 'agency';
	let sortKey = $state<SortKey>('closing_soon');
	let page = $state(0);
	const PAGE_SIZE = 20;

	$effect(() => {
		loading = true;
		Promise.all([loadJobs(), loadJobDetailsIndex()])
			.then(([jobs, idx]) => {
				allJobs = jobs;
				details = idx;
			})
			.catch((err) => (error = (err as Error).message))
			.finally(() => (loading = false));
	});

	// Reset to first page when scope, filters, or sort changes.
	$effect(() => {
		void listView.scope;
		void listView.code;
		void mapState.filters;
		void sortKey;
		page = 0;
	});

	function inScope(feature: Feature): boolean {
		const props = feature.properties ?? {};
		switch (listView.scope) {
			case 'state':
				return String(props.state ?? '').toUpperCase() === listView.code.toUpperCase();
			case 'locality':
				return String(props.locality_code ?? '').toUpperCase() === listView.code.toUpperCase();
			case 'county':
				return String(details[String(props.id ?? '')]?.locations?.[0]?.state ?? '') === listView.code;
			case 'cbsa':
				return false;
			default:
				return false;
		}
	}

	const inScopeFiltered = $derived.by(() => {
		if (!allJobs) return [] as Feature[];
		const filtered = filterJobs(allJobs, mapState.filters, details);
		return filtered.features.filter(inScope);
	});

	function detailFor(props: Record<string, unknown>): JobDetails | undefined {
		return details[String(props.id ?? '')];
	}

	function titleOf(feature: Feature): string {
		const props = feature.properties ?? {};
		return String(detailFor(props)?.title ?? props.title ?? '').trim().toLowerCase();
	}

	function agencyOf(feature: Feature): string {
		const props = feature.properties ?? {};
		return String(detailFor(props)?.agency ?? props.agency_code ?? '').trim().toLowerCase();
	}

	function salaryOf(feature: Feature): number {
		const props = feature.properties ?? {};
		const v = Number(detailFor(props)?.salary_min ?? props.salary_min ?? 0);
		return Number.isFinite(v) ? v : 0;
	}

	function closeDateOf(feature: Feature): number {
		// Higher number = sooner (use negative epoch-days so closing_soon = ascending).
		const props = feature.properties ?? {};
		const raw = String(detailFor(props)?.close_date ?? props.close_date ?? '');
		const t = Date.parse(raw);
		return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
	}

	const sorted = $derived.by(() => {
		const list = inScopeFiltered.slice();
		switch (sortKey) {
			case 'closing_soon':
				return list.sort((a, b) => closeDateOf(a) - closeDateOf(b));
			case 'closing_late':
				return list.sort((a, b) => closeDateOf(b) - closeDateOf(a));
			case 'salary_high':
				return list.sort((a, b) => salaryOf(b) - salaryOf(a));
			case 'salary_low':
				return list.sort((a, b) => salaryOf(a) - salaryOf(b));
			case 'title':
				return list.sort((a, b) => titleOf(a).localeCompare(titleOf(b)));
			case 'agency':
				return list.sort((a, b) => agencyOf(a).localeCompare(agencyOf(b)));
			default:
				return list;
		}
	});

	const totalCount = $derived(sorted.length);
	const totalPages = $derived(Math.max(1, Math.ceil(totalCount / PAGE_SIZE)));
	const pageSafe = $derived(Math.min(page, Math.max(0, totalPages - 1)));
	const pageStart = $derived(pageSafe * PAGE_SIZE);
	const pageEnd = $derived(Math.min(pageStart + PAGE_SIZE, totalCount));
	const visible = $derived(sorted.slice(pageStart, pageEnd));

	function pickJob(feature: Feature) {
		mapState.selectedFeature = {
			source: LAYER_IDS.markers,
			label: 'Job card',
			properties: feature.properties ?? {}
		};
		mapState.listView = null;
	}

	function backToRoundup() {
		mapState.listView = null;
	}

	function prevPage() {
		page = Math.max(0, pageSafe - 1);
	}
	function nextPage() {
		page = Math.min(totalPages - 1, pageSafe + 1);
	}
</script>

<section class="job-list">
	<div class="header">
		<button type="button" class="back" onclick={backToRoundup} aria-label="Back to roundup">
			&lt;- Back
		</button>
		<div>
			<p class="eyebrow">Postings in scope</p>
			<h3>{listView.label}</h3>
		</div>
	</div>

	{#if loading}
		<p class="note">Loading postings...</p>
	{:else if error}
		<p class="error">{error}</p>
	{:else if totalCount === 0}
		<p class="note">No postings match the current filters in {listView.label}. Adjust your filter chips and try again.</p>
	{:else}
		<div class="toolbar">
			<span class="count">
				{#if totalCount > PAGE_SIZE}
					{pageStart + 1}–{pageEnd} of {totalCount.toLocaleString()}
				{:else}
					{totalCount.toLocaleString()} posting{totalCount === 1 ? '' : 's'}
				{/if}
			</span>
			<label class="sort">
				<span class="sort-label">Sort</span>
				<select bind:value={sortKey}>
					<option value="closing_soon">Closing soonest</option>
					<option value="closing_late">Closing latest</option>
					<option value="salary_high">Salary (high → low)</option>
					<option value="salary_low">Salary (low → high)</option>
					<option value="title">Title (A → Z)</option>
					<option value="agency">Agency (A → Z)</option>
				</select>
			</label>
		</div>

		<ul>
			{#each visible as feature, i (feature.properties?.id ?? i)}
				{@const props = feature.properties ?? {}}
				{@const detail = detailFor(props)}
				{@const urg = urgencyBadge(String(detail?.close_date ?? props.close_date ?? ''))}
				<li>
					<button type="button" class="row" onclick={() => pickJob(feature)}>
						<div class="row-header">
							<div class="row-title">{detail?.title ?? propString(props, 'title', 'Loading…')}</div>
							{#if urg.level}<span class="urgency-badge urgency-{urg.level}">{urg.text}</span>{/if}
						</div>
						<div class="row-agency">
							<QuickAdd
								type="agency"
								value={String(detail?.agency_code ?? props.agency_code ?? '')}
								label={String(detail?.agency ?? props.agency_code ?? 'Agency unknown')}
							/>
						</div>
						<div class="row-dept">{String(detail?.department ?? 'Department unknown')}</div>
						<div class="row-meta">
							<span>{gradeRange(detail?.pay_plan ?? props.pay_plan, detail?.grade_low ?? props.grade_low, detail?.grade_high ?? props.grade_high)}</span>
							<span>Series <QuickAdd type="series" value={String(detail?.series ?? props.series ?? '')} /></span>
						</div>
						<div class="row-meta">
							<span>{salaryRange(detail?.salary_min ?? props.salary_min, detail?.salary_max ?? props.salary_max, detail?.salary_type)}</span>
							<span>{String(detail?.remote_status ?? props.remote_status ?? 'Remote unknown')}</span>
						</div>
						<div class="row-meta">
							<span>Closes {String(detail?.close_date ?? props.close_date ?? '-')}</span>
							<span>{propString(props, 'city')}, {propString(props, 'state', '')}</span>
							<span>Locality {propString(props, 'locality_code')}</span>
						</div>
					</button>
				</li>
			{/each}
		</ul>

		{#if totalPages > 1}
			<nav class="pager" aria-label="Posting list pages">
				<button type="button" onclick={prevPage} disabled={pageSafe === 0} aria-label="Previous page">
					‹ Prev
				</button>
				<span class="page-indicator">Page {pageSafe + 1} of {totalPages}</span>
				<button type="button" onclick={nextPage} disabled={pageSafe >= totalPages - 1} aria-label="Next page">
					Next ›
				</button>
			</nav>
		{/if}
	{/if}
</section>

<style>
	.job-list {
		display: flex;
		flex-direction: column;
		min-height: 0;
	}
	.header {
		display: flex;
		gap: 0.6rem;
		align-items: flex-start;
		margin-bottom: 0.6rem;
	}
	.back {
		appearance: none;
		border: 1px solid #2c4870;
		background: rgba(28, 42, 64, 0.4);
		color: #cfd9e6;
		padding: 0.25rem 0.55rem;
		border-radius: 999px;
		cursor: pointer;
		font-size: 11px;
	}
	.back:hover {
		border-color: #7bd0f2;
		color: #7bd0f2;
	}
	.eyebrow {
		margin: 0;
		color: #7bd0f2;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	h3 {
		margin: 0.1rem 0 0;
		font-size: 14px;
		line-height: 1.2;
	}
	.note,
	.error {
		margin: 0.5rem 0;
		font-size: 12px;
		line-height: 1.45;
		color: #94a3b8;
	}
	.error {
		color: #f1bcbc;
	}
	.toolbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		margin: 0 0 0.5rem;
		font-size: 11px;
	}
	.count {
		color: #94a3b8;
	}
	.sort {
		display: inline-flex;
		gap: 0.35rem;
		align-items: center;
	}
	.sort-label {
		color: #94a3b8;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.sort select {
		appearance: none;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text, #e5edf5);
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 4px;
		padding: 0.2rem 0.45rem;
		font-size: 11px;
		cursor: pointer;
	}
	.sort select:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 1px;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.row {
		display: block;
		width: 100%;
		text-align: left;
		appearance: none;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 6px;
		padding: 0.5rem 0.65rem;
		color: inherit;
		cursor: pointer;
		transition: border-color 120ms ease, background 120ms ease;
	}
	.row:hover {
		border-color: var(--c-accent-dim, #4979b3);
		background: var(--c-row-hover, rgba(28, 42, 64, 0.85));
	}
	.row:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.row-header {
		display: flex;
		align-items: flex-start;
		gap: 0.4rem;
		flex-wrap: wrap;
	}
	.row-title {
		font-weight: 600;
		font-size: 12.5px;
		color: var(--c-text, #e5edf5);
		line-height: 1.3;
		flex: 1 1 auto;
	}
	.urgency-badge {
		flex-shrink: 0;
		display: inline-block;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		white-space: nowrap;
	}
	.urgency-critical {
		background: rgba(220, 80, 80, 0.18);
		border: 1px solid #dc5050;
		color: #f7a0a0;
	}
	.urgency-soon {
		background: rgba(220, 160, 50, 0.18);
		border: 1px solid #e0a030;
		color: #f0c878;
	}
	.row-agency {
		margin-top: 0.2rem;
		color: var(--c-text-2, #cfd9e6);
		font-size: 11px;
		font-weight: 600;
	}
	.row-dept {
		margin-top: 0.15rem;
		color: var(--c-muted, #94a3b8);
		font-size: 10.5px;
	}
	.row-meta {
		margin-top: 0.2rem;
		display: flex;
		gap: 0.35rem 0.55rem;
		flex-wrap: wrap;
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
	}
	.pager {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		margin: 0.7rem 0 0.4rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--c-border-subtle, #22344c);
		font-size: 11px;
	}
	.pager button {
		appearance: none;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text, #e5edf5);
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 4px;
		padding: 0.25rem 0.6rem;
		font-size: 11px;
		cursor: pointer;
	}
	.pager button:hover:not(:disabled) {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.pager button:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.page-indicator {
		color: var(--c-muted, #94a3b8);
	}
</style>
