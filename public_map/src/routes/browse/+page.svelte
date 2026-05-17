<!--
	FedFinder — Browse view (mobile-first).

	The List tab works from the deduplicated jobs_detail.json (one row per
	posting). Agency is a code-backed picker (AgencyPicker.svelte); pay plan,
	remote, grade, series, salary, and keyword live behind "More filters".
	All inputs drive the one shared filter, mapState.filters. The list itself
	is the shared JobList component in rich mode.

	Spec: public_map/mocks/browse/mobile-dock.html (rev 2), ADR-0033.
	Map / Here / Saved tabs are filled in by later increments.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from '$lib/store.svelte';
	import { DEFAULT_FILTERS, type JobFilters } from '$lib/filters';
	import { jobProfile } from '$lib/jobProfile.svelte';
	import AgencyPicker from '$lib/AgencyPicker.svelte';
	import JobList from '$lib/JobList.svelte';

	type Tab = 'map' | 'list' | 'here' | 'saved';
	let tab = $state<Tab>('list');

	const THEME_KEY = 'fedfinder.public_map.theme.v1';

	let moreOpen = $state(false);

	// Theme — read once, persist on change (so /browse themes when opened direct).
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

	// --- the single shared filter ---
	function setFilter<K extends keyof JobFilters>(key: K, value: JobFilters[K]) {
		mapState.filters = {
			...mapState.filters,
			[key]: value,
			agencies: [...mapState.filters.agencies],
			geographies: [...mapState.filters.geographies]
		};
	}

	// Keyword is debounced — it is the only free-text field that filters.
	let keywordDraft = $state('');
	let kwTimer: ReturnType<typeof setTimeout> | null = null;
	function onKeyword(v: string) {
		keywordDraft = v;
		if (kwTimer) clearTimeout(kwTimer);
		kwTimer = setTimeout(() => setFilter('keyword', keywordDraft.trim()), 200);
	}

	function clearAll() {
		mapState.filters = { ...DEFAULT_FILTERS, agencies: [], geographies: [] };
		keywordDraft = '';
	}

	const moreCount = $derived.by(() => {
		const f = mapState.filters;
		let n = 0;
		if (f.keyword) n += 1;
		if (f.payPlan) n += 1;
		if (f.remote !== 'any') n += 1;
		if (f.gradeMin) n += 1;
		if (f.gradeMax) n += 1;
		if (f.series) n += 1;
		if (f.salaryMin) n += 1;
		return n;
	});
	const anyFilter = $derived(
		mapState.filters.agencies.length > 0 || moreCount > 0 || mapState.filters.geographies.length > 0
	);

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
		<button type="button" class="theme-btn" onclick={toggleTheme} aria-label="Toggle light or dark mode">
			{mapState.theme === 'dark' ? '☀' : '☾'}
		</button>
	</header>

	<main class="content">
		<!-- ===================== List tab ===================== -->
		{#if tab === 'list'}
			<section class="tab-list">
				<div class="toolbar">
					<!-- Primary filter: code-backed agency picker. -->
					<AgencyPicker />

					<div class="tools">
						<button
							type="button"
							class="more-btn"
							class:on={moreOpen || moreCount > 0}
							onclick={() => (moreOpen = !moreOpen)}
						>
							More filters{#if moreCount > 0}<span class="badge">{moreCount}</span>{/if}
							<span class="caret">{moreOpen ? '▴' : '▾'}</span>
						</button>
						{#if anyFilter}
							<button type="button" class="clear" onclick={clearAll}>Clear filters</button>
						{/if}
					</div>

					{#if moreOpen}
						<div class="more-panel">
							<label class="fld">
								<span>Keyword</span>
								<input
									type="search"
									placeholder="title, series, city…"
									value={keywordDraft}
									oninput={(e) => onKeyword(e.currentTarget.value)}
								/>
							</label>
							<div class="fld-row">
								<label class="fld">
									<span>Pay plan</span>
									<select
										value={mapState.filters.payPlan}
										onchange={(e) => setFilter('payPlan', e.currentTarget.value)}
									>
										<option value="">Any</option>
										<option value="GS">GS — General Schedule</option>
										<option value="WG">WG — Wage Grade</option>
										<option value="WS">WS — Wage Supervisor</option>
										<option value="FV">FV — FAA</option>
										<option value="FG">FG — FAA</option>
										<option value="GL">GL — Law Enforcement</option>
										<option value="FP">FP — Foreign Service</option>
										<option value="AT">AT — Air Traffic</option>
										<option value="ES">ES — Senior Executive</option>
										<option value="AD">AD — Administratively Determined</option>
									</select>
								</label>
								<label class="fld">
									<span>Remote</span>
									<select
										value={mapState.filters.remote}
										onchange={(e) => setFilter('remote', e.currentTarget.value as JobFilters['remote'])}
									>
										<option value="any">Any</option>
										<option value="remote">Remote</option>
										<option value="hybrid">Hybrid</option>
										<option value="onsite">Onsite</option>
									</select>
								</label>
							</div>
							<div class="fld-row">
								<label class="fld">
									<span>Grade min</span>
									<input
										type="number"
										min="1"
										max="15"
										value={mapState.filters.gradeMin}
										oninput={(e) => setFilter('gradeMin', e.currentTarget.value)}
									/>
								</label>
								<label class="fld">
									<span>Grade max</span>
									<input
										type="number"
										min="1"
										max="15"
										value={mapState.filters.gradeMax}
										oninput={(e) => setFilter('gradeMax', e.currentTarget.value)}
									/>
								</label>
							</div>
							<div class="fld-row">
								<label class="fld">
									<span>Series</span>
									<input
										type="text"
										inputmode="numeric"
										placeholder="0301"
										value={mapState.filters.series}
										oninput={(e) => setFilter('series', e.currentTarget.value)}
									/>
								</label>
								<label class="fld">
									<span>Salary min</span>
									<input
										type="number"
										min="0"
										placeholder="90000"
										value={mapState.filters.salaryMin}
										oninput={(e) => setFilter('salaryMin', e.currentTarget.value)}
									/>
								</label>
							</div>
						</div>
					{/if}
				</div>

				<JobList richMode />
			</section>

		<!-- ===================== Map tab ===================== -->
		{:else if tab === 'map'}
			<section class="tab-stub">
				<div class="eyebrow">Map</div>
				<h2>Map view — next increment</h2>
				<p>
					The live map drops in here, crossfiltered to the same agency and
					filters that drive this List.
				</p>
				<a class="stub-link" href="/map">Open the current map →</a>
			</section>

		<!-- ===================== Here tab ===================== -->
		{:else if tab === 'here'}
			<section class="tab-stub">
				<div class="eyebrow">Here</div>
				<h2>Area card — next increment</h2>
				<p>
					The smallest area containing the map viewport, with a deterministic
					summary and four tap-to-expand metric blocks.
				</p>
			</section>

		<!-- ===================== Saved tab ===================== -->
		{:else}
			<section class="tab-stub">
				<div class="eyebrow">Saved</div>
				<h2>Saved &amp; tracked — next increment</h2>
				<p>Job Lists, My Postings, Hidden, and Viewed-closed.</p>
				<p class="muted">
					You have {savedCount} posting{savedCount === 1 ? '' : 's'} saved. Save and Hide
					from the List tab already work and persist locally.
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

	.content {
		flex: 1;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
	}

	/* Toolbar — the single filter area. */
	.toolbar {
		position: sticky;
		top: 0;
		z-index: 2;
		background: var(--c-bg, #06111f);
		padding: 0.65rem 0.75rem;
		border-bottom: 1px solid var(--c-border-subtle, #22344c);
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
	}
	.tools {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}
	.more-btn {
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text-2, #cfd9e6);
		font-size: 12px;
		font-weight: 600;
		padding: 0.4rem 0.6rem;
		border-radius: 6px;
		cursor: pointer;
	}
	.more-btn.on {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.more-btn .badge {
		display: grid;
		place-items: center;
		min-width: 15px;
		height: 15px;
		padding: 0 0.2rem;
		border-radius: 999px;
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 9px;
	}
	.more-btn .caret {
		font-size: 9px;
	}
	.clear {
		margin-left: auto;
		appearance: none;
		background: transparent;
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text-2, #cfd9e6);
		font-size: 10px;
		font-weight: 600;
		padding: 0.3rem 0.6rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.clear:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}

	/* More filters */
	.more-panel {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.6rem;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
	}
	.fld-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.5rem;
	}
	.fld {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.fld span {
		font-size: 9px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--c-muted, #94a3b8);
	}
	.fld input,
	.fld select {
		width: 100%;
		box-sizing: border-box;
		background: var(--c-bg, #06111f);
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 6px;
		padding: 0.4rem 0.5rem;
		font-size: 13px;
		outline: none;
	}
	.fld input:focus,
	.fld select:focus {
		border-color: var(--c-accent, #7bd0f2);
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

	@media (min-width: 720px) {
		.browse {
			max-width: 30rem;
			margin: 0 auto;
			border-left: 1px solid var(--c-border, #2a3a52);
			border-right: 1px solid var(--c-border, #2a3a52);
		}
	}
</style>
