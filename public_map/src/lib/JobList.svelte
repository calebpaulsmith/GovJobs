<!--
	Shared job-list component used by both views:

	- Scoped mode (`/map`'s FeaturePanel): pass `listView`. The list is scoped
	  to a polygon (state, locality, county, CBSA), honors the active filter
	  chips, works from jobs.geojson features + loadJobDetailsIndex(), and
	  paginates 20/page with a prev/next pager.
	- Rich mode (`/browse`'s List tab): pass `richMode` and no `listView`. The
	  list works from the deduplicated jobs_detail.json (one row per posting),
	  excludes hidden jobs, paginates 25/page with a "show more" button, and
	  each row has working Save/Hide actions.
-->
<script lang="ts">
	import { mapState, type ListView } from './store.svelte';
	import { loadJobs, loadJobDetailsIndex, type Feature, type JobDetails } from './data';
	import { filterJobs, filterJobDetails } from './filters';
	import { LAYER_IDS } from './layers';
	import { gradeRange, propString, salaryRange, urgencyBadge } from './format';
	import { jobProfile } from './jobProfile.svelte';
	import QuickAdd from './QuickAdd.svelte';
	import { FACETS, rowMatchesSearch, type FacetKey } from './jobListFacets';

	let { listView, richMode = false }: { listView?: ListView; richMode?: boolean } = $props();

	// Normalized row model so sort/paging/templates work the same way in both
	// modes. Scoped rows carry the GeoJSON feature `props`; rich rows do not.
	type Row = { id: string; detail: JobDetails | undefined; props: Record<string, unknown> };

	let allJobs = $state<{ type: 'FeatureCollection'; features: Feature[] } | null>(null);
	let details = $state<Record<string, JobDetails>>({});
	let detailsIndex = $state<Record<string, JobDetails>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	// `newest` (by open_date desc) is rich-mode only — the scoped `<select>`
	// below does not expose it. Both modes share this union so a single
	// sort()-switch handles every value, but the scoped UI only renders the
	// pre-existing six options.
	type SortKey =
		| 'closing_soon'
		| 'closing_late'
		| 'salary_high'
		| 'salary_low'
		| 'title'
		| 'agency'
		| 'newest';
	let sortKey = $state<SortKey>('closing_soon');

	// Scoped pager (prev/next, 20/page).
	let page = $state(0);
	const PAGE_SIZE = 20;
	// Rich pager (incremental "show more", 25/page).
	const RICH_PAGE = 25;
	let visibleCount = $state(RICH_PAGE);

	// --- rich-mode in-list toolbar state (PR C of D.5.28) ---
	// TODO(D.5.29): hoist to `mapState.list = { search, sort, facets[] }`
	// for URL round-trip + saved-searches v2. Until then this state is
	// local to the component and is reset on full page reload.
	let listSearchDraft = $state('');
	let listSearch = $state('');
	let searchTimer: ReturnType<typeof setTimeout> | null = null;
	function onListSearch(value: string) {
		listSearchDraft = value;
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			listSearch = listSearchDraft;
		}, 200);
	}
	let activeFacets = $state<Set<FacetKey>>(new Set());
	function toggleFacet(key: FacetKey) {
		// Re-assign so Svelte 5 sees the mutation on the $state Set.
		const next = new Set(activeFacets);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		activeFacets = next;
	}

	// Rich mode loads only the deduplicated detail index — it must not pull the
	// ~70k-feature jobs.geojson. Scoped mode needs both.
	$effect(() => {
		loading = true;
		if (richMode) {
			loadJobDetailsIndex()
				.then((idx) => (detailsIndex = idx))
				.catch((err) => (error = (err as Error).message))
				.finally(() => (loading = false));
		} else {
			Promise.all([loadJobs(), loadJobDetailsIndex()])
				.then(([jobs, idx]) => {
					allJobs = jobs;
					details = idx;
				})
				.catch((err) => (error = (err as Error).message))
				.finally(() => (loading = false));
		}
	});

	// Reset paging when scope, filters, sort, in-list search, or facets change.
	$effect(() => {
		void listView?.scope;
		void listView?.code;
		void mapState.filters;
		void sortKey;
		void listSearch;
		void activeFacets;
		page = 0;
		visibleCount = RICH_PAGE;
	});

	function inScope(feature: Feature): boolean {
		if (!listView) return false;
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

	// Rich-mode base: global-filter applied + hidden-job exclusion. This is the
	// set the in-list search and the facet chips narrow further. Facet counts
	// are computed off this set (each facet is counted independently of the
	// others and independently of `listSearch`) so users see the absolute
	// size of each bucket.
	const richBase = $derived.by<Row[]>(() => {
		if (!richMode) return [];
		const list = filterJobDetails(Object.values(detailsIndex), mapState.filters);
		return list
			.filter((job) => !jobProfile.isHidden(String(job.id)))
			.map((job) => ({ id: String(job.id), detail: job, props: {} }));
	});

	// Per-facet counts against `richBase` — each chip shows its absolute size.
	const facetCounts = $derived.by<Record<FacetKey, number>>(() => {
		const counts: Record<FacetKey, number> = {
			gs_family: 0,
			remote_eligible: 0,
			closing_7d: 0,
			hide_viewed: 0
		};
		if (!richMode) return counts;
		const ctx = { isViewed: (id: string) => jobProfile.isViewed(id) };
		for (const row of richBase) {
			const detail = row.detail;
			if (!detail) continue;
			for (const def of FACETS) {
				if (def.match(detail, ctx)) counts[def.key] += 1;
			}
		}
		return counts;
	});

	// Normalized rows for the active mode. In rich mode we apply, in order:
	// the in-list search, then the active facets (AND across facets).
	const rows = $derived.by<Row[]>(() => {
		if (richMode) {
			const search = listSearch;
			const facets = activeFacets;
			const ctx = { isViewed: (id: string) => jobProfile.isViewed(id) };
			return richBase.filter((row) => {
				const detail = row.detail;
				if (!detail) return false;
				if (search && !rowMatchesSearch(detail, row.props, search)) return false;
				for (const key of facets) {
					const def = FACETS.find((f) => f.key === key);
					if (!def) continue;
					if (!def.match(detail, ctx)) return false;
				}
				return true;
			});
		}
		if (!allJobs) return [];
		const filtered = filterJobs(allJobs, mapState.filters, details);
		return filtered.features.filter(inScope).map((feature) => {
			const props = feature.properties ?? {};
			const id = String(props.id ?? '');
			return { id, detail: details[id], props };
		});
	});

	// Sort accessors read from row.detail first, falling back to row.props.
	function titleOf(row: Row): string {
		return String(row.detail?.title ?? row.props.title ?? '').trim().toLowerCase();
	}
	function agencyOf(row: Row): string {
		return String(row.detail?.agency ?? row.props.agency_code ?? '').trim().toLowerCase();
	}
	function salaryOf(row: Row): number {
		const v = Number(row.detail?.salary_min ?? row.props.salary_min ?? 0);
		return Number.isFinite(v) ? v : 0;
	}
	function closeDateOf(row: Row): number {
		// Higher number = later (use ascending for closing_soon).
		const raw = String(row.detail?.close_date ?? row.props.close_date ?? '');
		const t = Date.parse(raw);
		return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
	}
	function openDateOf(row: Row): number {
		// Higher number = later (use descending for newest).
		const raw = String(row.detail?.open_date ?? row.props.open_date ?? '');
		const t = Date.parse(raw);
		return Number.isFinite(t) ? t : Number.NEGATIVE_INFINITY;
	}

	const sorted = $derived.by<Row[]>(() => {
		const list = rows.slice();
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
			case 'newest':
				return list.sort((a, b) => openDateOf(b) - openDateOf(a));
			default:
				return list;
		}
	});

	const totalCount = $derived(sorted.length);

	// Scoped pager.
	const totalPages = $derived(Math.max(1, Math.ceil(totalCount / PAGE_SIZE)));
	const pageSafe = $derived(Math.min(page, Math.max(0, totalPages - 1)));
	const pageStart = $derived(pageSafe * PAGE_SIZE);
	const pageEnd = $derived(Math.min(pageStart + PAGE_SIZE, totalCount));

	// `visible` is the slice rendered for the active mode.
	const visible = $derived(
		richMode ? sorted.slice(0, visibleCount) : sorted.slice(pageStart, pageEnd)
	);

	function pickJob(row: Row) {
		mapState.selectedFeature = {
			source: LAYER_IDS.markers,
			label: 'Job card',
			properties: row.props
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

	// --- rich-mode helpers (ported from browse/+page.svelte) ---
	function locationLabel(job: JobDetails): string {
		if (String(job.remote_status ?? '').toLowerCase() === 'remote') return 'Anywhere remote';
		const locs = job.locations ?? [];
		if (locs.length === 0) return 'Location not listed';
		const first = String(locs[0]?.city ?? locs[0]?.location_text ?? '').trim() || 'Location not listed';
		return locs.length > 1 ? `${first} +${locs.length - 1} more` : first;
	}
	function toggleSave(job: JobDetails) {
		const id = String(job.id ?? '');
		if (!id) return;
		if (jobProfile.isSaved(id)) {
			jobProfile.unsaveJob(id);
		} else {
			jobProfile.saveJob(id, {
				title: String(job.title ?? 'Untitled posting'),
				agency: String(job.agency ?? job.agency_code ?? ''),
				close_date: job.close_date ?? null,
				url: job.url ?? null
			});
		}
	}
	function hide(job: JobDetails) {
		const id = String(job.id ?? '');
		if (id) jobProfile.hideJob(id);
	}
	function markViewed(job: JobDetails) {
		const id = String(job.id ?? '');
		if (id) jobProfile.markViewed(id);
	}

	// Rich mode renders nothing meaningful without a listView in scoped mode.
	const scopedReady = $derived(richMode || !!listView);
</script>

<section class="job-list" class:rich={richMode}>
	{#if !scopedReady}
		<!-- Scoped mode with no listView: render nothing. -->
	{:else}
		{#if !richMode && listView}
			<div class="header">
				<button type="button" class="back" onclick={backToRoundup} aria-label="Back to roundup">
					&lt;- Back
				</button>
				<div>
					<p class="eyebrow">Postings in scope</p>
					<h3>{listView.label}</h3>
				</div>
			</div>
		{/if}

		{#if loading}
			<p class="note">Loading postings...</p>
		{:else if error}
			<p class="error">{richMode ? `Couldn't load postings: ${error}` : error}</p>
		{:else if totalCount === 0}
			{#if richMode}
				<!-- Render the sticky toolbar even when empty so the user can clear
				     a too-narrow in-list search or active facet without first
				     loosening a global chip. -->
				<div class="rich-sticky">
					<div class="rich-search-row">
						<input
							type="search"
							class="rich-search"
							placeholder="Search within results…"
							value={listSearchDraft}
							oninput={(e) => onListSearch(e.currentTarget.value)}
							aria-label="Search within results"
						/>
						<label class="sort">
							<span class="sort-label">Sort</span>
							<select bind:value={sortKey} aria-label="Sort postings">
								<option value="closing_soon">Closing soonest</option>
								<option value="closing_late">Closing latest</option>
								<option value="salary_high">Highest pay</option>
								<option value="salary_low">Lowest pay</option>
								<option value="title">Title A–Z</option>
								<option value="agency">Agency A–Z</option>
								<option value="newest">Newest</option>
							</select>
						</label>
					</div>
					<div class="facets" role="group" aria-label="Result facets">
						{#each FACETS as f (f.key)}
							<button
								type="button"
								class="facet-chip"
								class:on={activeFacets.has(f.key)}
								aria-pressed={activeFacets.has(f.key)}
								onclick={() => toggleFacet(f.key)}
							>
								{f.label}
								<span class="count">({facetCounts[f.key].toLocaleString()})</span>
							</button>
						{/each}
					</div>
					<div class="rich-toolbar">
						<span class="count">0 of {Object.keys(detailsIndex).length.toLocaleString()} postings</span>
					</div>
				</div>
				<p class="empty">No postings match the current filter. Remove an agency or open More filters to widen it.</p>
			{:else}
				<p class="note">No postings match the current filters in {listView?.label}. Adjust your filter chips and try again.</p>
			{/if}
		{:else}
			{#if richMode}
				<div class="rich-sticky">
					<div class="rich-search-row">
						<input
							type="search"
							class="rich-search"
							placeholder="Search within results…"
							value={listSearchDraft}
							oninput={(e) => onListSearch(e.currentTarget.value)}
							aria-label="Search within results"
						/>
						<label class="sort">
							<span class="sort-label">Sort</span>
							<select bind:value={sortKey} aria-label="Sort postings">
								<option value="closing_soon">Closing soonest</option>
								<option value="closing_late">Closing latest</option>
								<option value="salary_high">Highest pay</option>
								<option value="salary_low">Lowest pay</option>
								<option value="title">Title A–Z</option>
								<option value="agency">Agency A–Z</option>
								<option value="newest">Newest</option>
							</select>
						</label>
					</div>
					<div class="facets" role="group" aria-label="Result facets">
						{#each FACETS as f (f.key)}
							<button
								type="button"
								class="facet-chip"
								class:on={activeFacets.has(f.key)}
								aria-pressed={activeFacets.has(f.key)}
								onclick={() => toggleFacet(f.key)}
							>
								{f.label}
								<span class="count">({facetCounts[f.key].toLocaleString()})</span>
							</button>
						{/each}
					</div>
					<div class="rich-toolbar">
						<span class="count">
							<strong>{totalCount.toLocaleString()}</strong> of {Object.keys(detailsIndex).length.toLocaleString()} postings
						</span>
					</div>
				</div>
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
			{/if}

			<ul class:rich-rows={richMode}>
				{#each visible as row, i (row.id || i)}
					{#if richMode}
						{@const job = row.detail}
						{#if job}
							{@const urg = urgencyBadge(job.close_date)}
							{@const saved = jobProfile.isSaved(row.id)}
							{@const viewed = jobProfile.isViewed(row.id)}
							<li class="row-rich" class:viewed>
								<div class="row-head">
									{#if job.url}
										<a
											class="row-title-rich"
											href={job.url}
											target="_blank"
											rel="noopener noreferrer"
											onclick={() => markViewed(job)}
										>
											{job.title ?? 'Untitled posting'}
										</a>
									{:else}
										<span class="row-title-rich">{job.title ?? 'Untitled posting'}</span>
									{/if}
									{#if urg.level}
										<span class="urgency {urg.level}">{urg.text}</span>
									{:else if viewed}
										<span class="urgency viewed-tag">Viewed</span>
									{/if}
								</div>
								<div class="row-meta-rich">
									<strong>{job.agency ?? job.agency_code ?? 'Agency unknown'}</strong>
									<span>{locationLabel(job)}</span>
									<span>{gradeRange(job.pay_plan, job.grade_low, job.grade_high)}</span>
									{#if job.series}<span>Series {job.series}</span>{/if}
								</div>
								<div class="row-foot">
									<span class="pay">{salaryRange(job.salary_min, job.salary_max, job.salary_type)}</span>
									<div class="row-actions">
										<button type="button" class="act save" class:on={saved} onclick={() => toggleSave(job)}>
											{saved ? '★ Saved' : '★ Save to My Postings'}
										</button>
										<button type="button" class="act hide" onclick={() => hide(job)}>⊘ Hide</button>
									</div>
								</div>
							</li>
						{/if}
					{:else}
						{@const props = row.props}
						{@const detail = row.detail}
						{@const urg = urgencyBadge(String(detail?.close_date ?? props.close_date ?? ''))}
						<li>
							<button type="button" class="row" onclick={() => pickJob(row)}>
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
					{/if}
				{/each}
			</ul>

			{#if richMode}
				{#if visibleCount < totalCount}
					<button type="button" class="load-more" onclick={() => (visibleCount += RICH_PAGE)}>
						Show {Math.min(RICH_PAGE, totalCount - visibleCount)} more
						<span class="muted">({visibleCount.toLocaleString()} of {totalCount.toLocaleString()})</span>
					</button>
				{:else}
					<p class="list-end">All {totalCount.toLocaleString()} matching postings shown.</p>
				{/if}
			{:else if totalPages > 1}
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

	/* --- rich mode (Browse list) — namespaced so it doesn't collide with
	   the scoped-mode .row button styles above. --- */

	/* The sticky in-list toolbar pins under the page-level toolbar in
	   browse/+page.svelte. The page-level toolbar is its own sticky element
	   inside the scrolling .content area, so this one's `top: 0;` lands flush
	   underneath it (sticky stacking is per-scroll-container). */
	.rich-sticky {
		position: sticky;
		top: 0;
		z-index: 1;
		background: var(--c-bg, #06111f);
		border-bottom: 1px solid var(--c-border-subtle, #22344c);
		padding: 0.55rem 0.75rem 0.4rem;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.rich-search-row {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		flex-wrap: wrap;
	}
	.rich-search {
		flex: 1 1 12rem;
		min-width: 0;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 6px;
		padding: 0.4rem 0.6rem;
		font-size: 12.5px;
		outline: none;
	}
	.rich-search:focus {
		border-color: var(--c-accent, #7bd0f2);
	}
	.facets {
		display: flex;
		gap: 0.3rem;
		overflow-x: auto;
		flex-wrap: nowrap;
		-webkit-overflow-scrolling: touch;
		scrollbar-width: thin;
		margin: 0 -0.15rem;
		padding: 0.05rem 0.15rem 0.2rem;
	}
	.facet-chip {
		flex-shrink: 0;
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.25rem 0.6rem;
		font-size: 11px;
		font-weight: 600;
		line-height: 1.2;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		cursor: pointer;
		white-space: nowrap;
	}
	.facet-chip:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.facet-chip:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 1px;
	}
	.facet-chip.on {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.facet-chip .count {
		color: var(--c-muted, #94a3b8);
		font-weight: 500;
		margin-left: 0.05rem;
	}
	.facet-chip.on .count {
		color: var(--c-accent, #7bd0f2);
	}

	.rich-toolbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.6rem;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
		padding: 0;
	}
	.rich-toolbar .count strong {
		color: var(--c-text, #e5edf5);
	}
	.rich-rows {
		padding: 0.6rem 0.75rem;
		gap: 0.5rem;
	}
	.row-rich {
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		padding: 0.65rem 0.7rem;
	}
	.row-rich.viewed {
		opacity: 0.72;
	}
	.row-head {
		display: flex;
		gap: 0.4rem;
		align-items: baseline;
	}
	.row-title-rich {
		flex: 1;
		font-size: 13px;
		font-weight: 600;
		color: var(--c-text, #e5edf5);
		text-decoration: none;
		line-height: 1.3;
	}
	a.row-title-rich:hover {
		color: var(--c-accent, #7bd0f2);
		text-decoration: underline;
	}
	.urgency {
		flex-shrink: 0;
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		padding: 0.1rem 0.4rem;
		border-radius: 4px;
	}
	.urgency.critical {
		background: rgba(220, 80, 80, 0.18);
		border: 1px solid #dc5050;
		color: var(--c-danger, #f7a0a0);
	}
	.urgency.soon {
		background: rgba(220, 160, 50, 0.18);
		border: 1px solid #e0a030;
		color: var(--c-warn, #f0c878);
	}
	.urgency.viewed-tag {
		background: rgba(140, 140, 160, 0.16);
		border: 1px solid #6a6a82;
		color: var(--c-muted, #94a3b8);
	}
	.row-meta-rich {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 0.5rem;
		margin: 0.3rem 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.row-meta-rich strong {
		color: var(--c-text-2, #cfd9e6);
		font-weight: 600;
	}
	.row-foot {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.pay {
		font-size: 12px;
		font-weight: 700;
		color: var(--c-text, #e5edf5);
	}
	.row-actions {
		display: flex;
		gap: 0.3rem;
	}
	.act {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-bg, #06111f);
		color: var(--c-text-2, #cfd9e6);
		font-size: 10px;
		font-weight: 600;
		padding: 0.3rem 0.5rem;
		border-radius: 5px;
		cursor: pointer;
	}
	.act.save:hover,
	.act.save.on {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.act.hide:hover {
		border-color: var(--c-danger-border, #6b2020);
		color: var(--c-danger, #f7a0a0);
	}
	.load-more {
		display: block;
		width: calc(100% - 1.5rem);
		margin: 0 0.75rem 0.9rem;
		appearance: none;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 8px;
		padding: 0.55rem;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
	}
	.load-more:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.list-end,
	.empty {
		text-align: center;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
		padding: 0.9rem 1rem;
	}
	.muted {
		color: var(--c-muted, #94a3b8);
		font-weight: 500;
	}
</style>
