<!--
	FedFinder — Browse view (mobile-first).

	Increment 1 of the mobile Browse build: the dock shell + a fully wired
	List tab. The single filter (mapState.filters) drives the list; the Map,
	Here, and Saved tabs are scaffolded and filled in later increments.

	Spec: public_map/mocks/browse/mobile-dock.html (rev 2), ADR-0033.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from '$lib/store.svelte';
	import { loadJobs, loadJobDetailsIndex, type Feature, type JobDetails } from '$lib/data';
	import { filterJobs, activeFilterCount } from '$lib/filters';
	import { gradeRange, propString, salaryRange, urgencyBadge } from '$lib/format';
	import { jobProfile } from '$lib/jobProfile.svelte';

	type Tab = 'map' | 'list' | 'here' | 'saved';
	let tab = $state<Tab>('list');

	const THEME_KEY = 'fedfinder.public_map.theme.v1';

	let allJobs = $state<{ type: 'FeatureCollection'; features: Feature[] } | null>(null);
	let details = $state<Record<string, JobDetails>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	type SortKey = 'closing_soon' | 'closing_late' | 'salary_high' | 'salary_low' | 'title';
	let sortKey = $state<SortKey>('closing_soon');

	const PAGE = 25;
	let visibleCount = $state(PAGE);

	// Theme: read once on mount, persist on change. Mirrors map/+page.svelte so
	// /browse themes correctly when opened directly.
	onMount(() => {
		if (!browser) return;
		const stored = localStorage.getItem(THEME_KEY);
		if (stored === 'light' || stored === 'dark') mapState.theme = stored;
	});
	$effect(() => {
		if (!browser) return;
		document.documentElement.dataset.theme = mapState.theme;
		localStorage.setItem(THEME_KEY, mapState.theme);
	});
	function toggleTheme() {
		mapState.theme = mapState.theme === 'dark' ? 'light' : 'dark';
	}

	// Load the job bundle once.
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

	// Reset the visible window when the filter or sort changes.
	$effect(() => {
		void mapState.filters;
		void sortKey;
		visibleCount = PAGE;
	});

	function detailFor(props: Record<string, unknown>): JobDetails | undefined {
		return details[String(props.id ?? '')];
	}
	function idOf(feature: Feature): string {
		return String(feature.properties?.id ?? '');
	}

	// The single filter pipeline. Hidden jobs are removed everywhere by default.
	const filtered = $derived.by(() => {
		if (!allJobs) return [] as Feature[];
		const fc = filterJobs(allJobs, mapState.filters, details);
		return fc.features.filter((f) => !jobProfile.isHidden(idOf(f)));
	});

	function titleOf(f: Feature): string {
		const p = f.properties ?? {};
		return String(detailFor(p)?.title ?? p.title ?? '').trim().toLowerCase();
	}
	function salaryOf(f: Feature): number {
		const p = f.properties ?? {};
		const v = Number(detailFor(p)?.salary_min ?? p.salary_min ?? 0);
		return Number.isFinite(v) ? v : 0;
	}
	function closeOf(f: Feature): number {
		const p = f.properties ?? {};
		const t = Date.parse(String(detailFor(p)?.close_date ?? p.close_date ?? ''));
		return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
	}

	const sorted = $derived.by(() => {
		const list = filtered.slice();
		switch (sortKey) {
			case 'closing_soon':
				return list.sort((a, b) => closeOf(a) - closeOf(b));
			case 'closing_late':
				return list.sort((a, b) => closeOf(b) - closeOf(a));
			case 'salary_high':
				return list.sort((a, b) => salaryOf(b) - salaryOf(a));
			case 'salary_low':
				return list.sort((a, b) => salaryOf(a) - salaryOf(b));
			case 'title':
				return list.sort((a, b) => titleOf(a).localeCompare(titleOf(b)));
			default:
				return list;
		}
	});

	const totalJobs = $derived(allJobs?.features.length ?? 0);
	const filteredCount = $derived(filtered.length);
	const visible = $derived(sorted.slice(0, visibleCount));
	const filterCount = $derived(activeFilterCount(mapState.filters));

	// Facet chips — wired straight to the shared filter.
	const gsOnly = $derived(mapState.filters.payPlan.toUpperCase() === 'GS');
	const remoteOnly = $derived(mapState.filters.remote === 'remote');
	function toggleGsOnly() {
		mapState.filters.payPlan = gsOnly ? '' : 'GS';
	}
	function toggleRemote() {
		mapState.filters.remote = remoteOnly ? 'any' : 'remote';
	}

	function removeGeo(geo: string) {
		mapState.filters.geographies = mapState.filters.geographies.filter((g) => g !== geo);
	}
	function removeAgency(code: string) {
		mapState.filters.agencies = mapState.filters.agencies.filter((a) => a !== code);
	}
	function geoLabel(geo: string): string {
		const [type, code] = geo.split(':');
		return `${type === 'state' ? 'State' : type === 'locality' ? 'Locality' : type} ${code}`;
	}

	function saveMeta(f: Feature) {
		const p = f.properties ?? {};
		const d = detailFor(p);
		return {
			title: String(d?.title ?? p.title ?? 'Untitled posting'),
			agency: String(d?.agency ?? p.agency ?? p.agency_code ?? ''),
			close_date: (d?.close_date ?? (p.close_date as string) ?? null) || null,
			url: (d?.url ?? (p.url as string) ?? null) || null
		};
	}
	function toggleSave(f: Feature) {
		const id = idOf(f);
		if (!id) return;
		if (jobProfile.isSaved(id)) jobProfile.unsaveJob(id);
		else jobProfile.saveJob(id, saveMeta(f));
	}
	function hide(f: Feature) {
		const id = idOf(f);
		if (id) jobProfile.hideJob(id);
	}
	function markViewed(f: Feature) {
		const id = idOf(f);
		if (id) jobProfile.markViewed(id);
	}

	const savedCount = $derived(jobProfile.savedJobs.length);
</script>

<svelte:head>
	<title>FedFinder — Browse federal jobs</title>
</svelte:head>

<div class="browse" data-theme={mapState.theme}>
	<!-- Masthead -->
	<header class="masthead">
		<span class="brand">FedFinder</span>
		<nav class="modes" aria-label="View mode">
			<span class="mode active">Browse</span>
			<a class="mode" href="/map">Map only</a>
			<span class="mode disabled" aria-disabled="true" title="Coming soon">Localities</span>
		</nav>
		<button
			type="button"
			class="theme-btn"
			onclick={toggleTheme}
			aria-label="Toggle light or dark mode"
		>
			{mapState.theme === 'dark' ? '☀' : '☾'}
		</button>
	</header>

	<!-- Scope bar — the single filter's geography / agency chips. -->
	<div class="scope-bar">
		{#if mapState.filters.geographies.length === 0 && mapState.filters.agencies.length === 0}
			<span class="scope-empty">Nationwide · no geography or agency filter</span>
		{:else}
			{#each mapState.filters.geographies as geo (geo)}
				<button type="button" class="chip" onclick={() => removeGeo(geo)}>
					{geoLabel(geo)} <span class="x" aria-hidden="true">×</span>
				</button>
			{/each}
			{#each mapState.filters.agencies as code (code)}
				<button type="button" class="chip" onclick={() => removeAgency(code)}>
					{code} <span class="x" aria-hidden="true">×</span>
				</button>
			{/each}
		{/if}
	</div>

	<main class="content">
		<!-- ===================== List tab ===================== -->
		{#if tab === 'list'}
			<section class="tab-list">
				<div class="toolbar">
					<div class="toolbar-row">
						<input
							class="search"
							type="text"
							placeholder="Filter — title, agency, series, location…"
							bind:value={mapState.filters.keyword}
						/>
						<select class="sort" bind:value={sortKey} aria-label="Sort postings">
							<option value="closing_soon">Closing soonest</option>
							<option value="closing_late">Closing latest</option>
							<option value="salary_high">Highest pay</option>
							<option value="salary_low">Lowest pay</option>
							<option value="title">Title A–Z</option>
						</select>
					</div>
					<div class="facets">
						<button type="button" class="facet" class:on={gsOnly} onclick={toggleGsOnly}>
							GS only
						</button>
						<button type="button" class="facet" class:on={remoteOnly} onclick={toggleRemote}>
							Remote-eligible
						</button>
					</div>
					<div class="summary">
						{#if loading}
							<span>Loading postings…</span>
						{:else if error}
							<span class="err">Couldn't load postings: {error}</span>
						{:else}
							<span>
								<strong>{filteredCount.toLocaleString()}</strong>
								of {totalJobs.toLocaleString()} postings
								{#if filterCount > 0}· {filterCount} filter{filterCount === 1 ? '' : 's'}{/if}
							</span>
						{/if}
					</div>
				</div>

				{#if !loading && !error}
					{#if filteredCount === 0}
						<p class="empty">No postings match the current filter. Remove a chip or clear the search.</p>
					{:else}
						<ul class="rows">
							{#each visible as feature, i (feature.properties?.id ?? i)}
								{@const props = feature.properties ?? {}}
								{@const d = detailFor(props)}
								{@const urg = urgencyBadge(String(d?.close_date ?? props.close_date ?? ''))}
								{@const id = idOf(feature)}
								{@const saved = jobProfile.isSaved(id)}
								{@const viewed = jobProfile.isViewed(id)}
								{@const url = d?.url ?? (props.url as string | undefined)}
								<li class="row" class:viewed>
									<div class="row-head">
										{#if url}
											<a
												class="row-title"
												href={url}
												target="_blank"
												rel="noopener noreferrer"
												onclick={() => markViewed(feature)}
											>
												{d?.title ?? propString(props, 'title', 'Untitled posting')}
											</a>
										{:else}
											<span class="row-title">
												{d?.title ?? propString(props, 'title', 'Untitled posting')}
											</span>
										{/if}
										{#if urg.level}
											<span class="urgency {urg.level}">{urg.text}</span>
										{:else if viewed}
											<span class="urgency viewed-tag">Viewed</span>
										{/if}
									</div>
									<div class="row-meta">
										<strong>{String(d?.agency ?? props.agency ?? props.agency_code ?? 'Agency unknown')}</strong>
										<span>{propString(props, 'city')}, {propString(props, 'state', '')}</span>
										<span>{gradeRange(d?.pay_plan ?? props.pay_plan, d?.grade_low ?? props.grade_low, d?.grade_high ?? props.grade_high)}</span>
										{#if (d?.series ?? props.series)}<span>Series {String(d?.series ?? props.series)}</span>{/if}
									</div>
									<div class="row-foot">
										<span class="pay">{salaryRange(d?.salary_min ?? props.salary_min, d?.salary_max ?? props.salary_max, d?.salary_type)}</span>
										<div class="row-actions">
											<button type="button" class="act save" class:on={saved} onclick={() => toggleSave(feature)}>
												{saved ? '★ Saved' : '★ Save to My Postings'}
											</button>
											<button type="button" class="act hide" onclick={() => hide(feature)}>⊘ Hide</button>
										</div>
									</div>
								</li>
							{/each}
						</ul>

						{#if visibleCount < filteredCount}
							<button type="button" class="load-more" onclick={() => (visibleCount += PAGE)}>
								Show {Math.min(PAGE, filteredCount - visibleCount)} more
								<span class="muted">({visibleCount.toLocaleString()} of {filteredCount.toLocaleString()})</span>
							</button>
						{:else}
							<p class="list-end">All {filteredCount.toLocaleString()} matching postings shown.</p>
						{/if}
					{/if}
				{/if}
			</section>

		<!-- ===================== Map tab ===================== -->
		{:else if tab === 'map'}
			<section class="tab-stub">
				<div class="eyebrow">Map</div>
				<h2>Map view — next increment</h2>
				<p>
					The live map drops in here, crossfiltered to the same filter that drives
					this List. Markers, clusters, and the geography chips you see in the scope
					bar will all reflect one filter.
				</p>
				<p class="muted">Until then, the full map is available in Map-only mode.</p>
				<a class="stub-link" href="/map">Open the current map →</a>
			</section>

		<!-- ===================== Here tab ===================== -->
		{:else if tab === 'here'}
			<section class="tab-stub">
				<div class="eyebrow">Here</div>
				<h2>Area card — next increment</h2>
				<p>
					The smallest area containing the map viewport, with a deterministic
					summary and four tap-to-expand metric blocks: Postings, Workforce,
					Pay vs COL, and Urgency.
				</p>
				<p class="muted">Spec: public_map/mocks/browse/mobile-dock.html (rev 2).</p>
			</section>

		<!-- ===================== Saved tab ===================== -->
		{:else}
			<section class="tab-stub">
				<div class="eyebrow">Saved</div>
				<h2>Saved &amp; tracked — next increment</h2>
				<p>
					Job Lists (saved filter sets) and My Postings (individual saved jobs),
					plus Hidden and Viewed-closed.
				</p>
				<p class="muted">
					You currently have {savedCount} posting{savedCount === 1 ? '' : 's'} saved.
					Save and Hide from the List tab already work and persist locally.
				</p>
			</section>
		{/if}
	</main>

	<!-- Dock -->
	<nav class="dock" aria-label="Browse sections">
		<button type="button" class:active={tab === 'map'} onclick={() => (tab = 'map')}>
			<span class="icon" aria-hidden="true">🗺</span><span>Map</span>
		</button>
		<button type="button" class:active={tab === 'list'} onclick={() => (tab = 'list')}>
			<span class="icon" aria-hidden="true">≡</span><span>List</span>
		</button>
		<button type="button" class:active={tab === 'here'} onclick={() => (tab = 'here')}>
			<span class="icon" aria-hidden="true">◉</span><span>Here</span>
		</button>
		<button type="button" class:active={tab === 'saved'} onclick={() => (tab = 'saved')}>
			<span class="icon" aria-hidden="true">★</span><span>Saved</span>
			{#if savedCount > 0}<span class="pip">{savedCount}</span>{/if}
		</button>
	</nav>
</div>

<style>
	.browse {
		position: fixed;
		inset: 0;
		display: flex;
		flex-direction: column;
		background: var(--c-bg, #06111f);
		color: var(--c-text, #e5edf5);
		font-size: 14px;
	}

	/* Masthead */
	.masthead {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.5rem 0.75rem;
		background: var(--c-panel, rgba(14, 23, 38, 0.96));
		border-bottom: 1px solid var(--c-border, #2a3a52);
	}
	.brand {
		font-weight: 700;
		letter-spacing: 0.01em;
		font-size: 14px;
	}
	.modes {
		display: inline-flex;
		gap: 0.1rem;
		background: var(--c-bg, #06111f);
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 999px;
		padding: 0.15rem;
	}
	.mode {
		font-size: 11px;
		font-weight: 600;
		padding: 0.28rem 0.6rem;
		border-radius: 999px;
		color: var(--c-text-2, #cfd9e6);
		text-decoration: none;
	}
	.mode.active {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
	}
	.mode.disabled {
		color: var(--c-faint, #64748b);
		cursor: not-allowed;
	}
	.theme-btn {
		margin-left: auto;
		appearance: none;
		width: 1.9rem;
		height: 1.9rem;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		cursor: pointer;
		font-size: 13px;
	}
	.theme-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}

	/* Scope bar */
	.scope-bar {
		flex-shrink: 0;
		display: flex;
		gap: 0.3rem;
		overflow-x: auto;
		padding: 0.45rem 0.75rem;
		background: var(--c-panel-blur, rgba(14, 23, 38, 0.85));
		border-bottom: 1px solid var(--c-border-subtle, #22344c);
	}
	.scope-empty {
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.chip {
		flex-shrink: 0;
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		background: var(--c-accent-bg, rgba(123, 208, 242, 0.08));
		border: 1px solid var(--c-accent-dim, #4979b3);
		color: var(--c-accent, #7bd0f2);
		padding: 0.18rem 0.55rem;
		border-radius: 999px;
		font-size: 11px;
		font-weight: 600;
		cursor: pointer;
	}
	.chip .x {
		color: var(--c-muted, #94a3b8);
	}

	/* Content */
	.content {
		flex: 1;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
	}

	/* Toolbar */
	.toolbar {
		position: sticky;
		top: 0;
		z-index: 2;
		background: var(--c-bg, #06111f);
		padding: 0.6rem 0.75rem;
		border-bottom: 1px solid var(--c-border-subtle, #22344c);
	}
	.toolbar-row {
		display: flex;
		gap: 0.35rem;
	}
	.search {
		flex: 1;
		min-width: 0;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 6px;
		padding: 0.45rem 0.6rem;
		font-size: 13px;
		outline: none;
	}
	.search:focus {
		border-color: var(--c-accent, #7bd0f2);
	}
	.sort {
		appearance: none;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text-2, #cfd9e6);
		border-radius: 6px;
		padding: 0.45rem 0.4rem;
		font-size: 12px;
		cursor: pointer;
	}
	.facets {
		display: flex;
		gap: 0.3rem;
		margin-top: 0.45rem;
	}
	.facet {
		appearance: none;
		font-size: 11px;
		font-weight: 600;
		padding: 0.22rem 0.6rem;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		cursor: pointer;
	}
	.facet.on {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.summary {
		margin-top: 0.45rem;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.summary strong {
		color: var(--c-text, #e5edf5);
	}
	.summary .err {
		color: var(--c-danger, #f7a0a0);
	}

	/* Rows */
	.rows {
		list-style: none;
		margin: 0;
		padding: 0.6rem 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.row {
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		padding: 0.65rem 0.7rem;
	}
	.row.viewed {
		opacity: 0.72;
	}
	.row-head {
		display: flex;
		gap: 0.4rem;
		align-items: baseline;
	}
	.row-title {
		flex: 1;
		font-size: 13px;
		font-weight: 600;
		color: var(--c-text, #e5edf5);
		text-decoration: none;
		line-height: 1.3;
	}
	a.row-title:hover {
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
	.row-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 0.5rem;
		margin: 0.3rem 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.row-meta strong {
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

	/* Stub tabs */
	.tab-stub {
		padding: 1.5rem 1.1rem;
		max-width: 30rem;
	}
	.eyebrow {
		color: var(--c-accent, #7bd0f2);
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.tab-stub h2 {
		margin: 0.25rem 0 0.6rem;
		font-size: 17px;
	}
	.tab-stub p {
		margin: 0 0 0.6rem;
		font-size: 12.5px;
		line-height: 1.5;
		color: var(--c-text-2, #cfd9e6);
	}
	.tab-stub p.muted {
		color: var(--c-muted, #94a3b8);
	}
	.stub-link {
		display: inline-block;
		margin-top: 0.3rem;
		font-size: 12px;
		font-weight: 600;
		color: var(--c-accent, #7bd0f2);
	}

	/* Dock */
	.dock {
		flex-shrink: 0;
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.15rem;
		background: var(--c-panel, rgba(14, 23, 38, 0.96));
		border-top: 1px solid var(--c-border, #2a3a52);
		padding: 0.35rem 0.4rem calc(0.35rem + env(safe-area-inset-bottom, 0px));
	}
	.dock button {
		appearance: none;
		background: transparent;
		border: none;
		color: var(--c-muted, #94a3b8);
		font-size: 10px;
		font-weight: 600;
		padding: 0.4rem 0.2rem 0.3rem;
		border-radius: 10px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.2rem;
		cursor: pointer;
		position: relative;
	}
	.dock button .icon {
		font-size: 18px;
		line-height: 1;
	}
	.dock button.active {
		color: var(--c-accent, #7bd0f2);
		background: var(--c-accent-bg, rgba(123, 208, 242, 0.08));
	}
	.dock button .pip {
		position: absolute;
		top: 0.25rem;
		left: 50%;
		margin-left: 0.35rem;
		min-width: 14px;
		height: 14px;
		padding: 0 0.2rem;
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border: 1px solid var(--c-accent-dim, #4979b3);
		color: var(--c-accent, #7bd0f2);
		border-radius: 999px;
		font-size: 8px;
		font-weight: 700;
		display: grid;
		place-items: center;
	}

	/* On wide screens, present the mobile shell as a centered phone-width
	   column. The full desktop mosaic is a later increment. */
	@media (min-width: 720px) {
		.browse {
			max-width: 30rem;
			margin: 0 auto;
			border-left: 1px solid var(--c-border, #2a3a52);
			border-right: 1px solid var(--c-border, #2a3a52);
		}
	}
</style>
