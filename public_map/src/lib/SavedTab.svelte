<!--
	SavedTab — the Saved tab on /browse.

	Replaces the "next increment" stub in browse/+page.svelte. Surfaces four
	categories of locally-persisted user state:

	1. Job Lists — saved filter sets (savedSearches.ts, localStorage).
	   Apply restores filters into mapState.filters and switches the dock to
	   List (via onViewList). Rename + Delete edit the localStorage store.
	2. My Postings — jobProfile.savedJobs (localStorage). Open opens the
	   posting URL in a new tab. Remove unsaves.
	3. Hidden — jobProfile.hiddenJobs (id + ts only). Each row is enriched
	   from loadJobDetailsIndex() when available. Unhide removes the entry.
	4. Viewed-closed — jobProfile.viewedClosedJobs(detailsIndex). Read-only.

	Pure helpers (relativeTime, summariseSavedSearch) live in ./savedTab.ts
	and are unit-tested in ./savedTab.test.ts.

	Deferred (intentionally out of scope for this increment):
	  - "+ Save to My Postings" action on rows — already lives on JobList
	    rich-mode rows; saving from here would duplicate that path.
	  - Provenance toast confirming a save — a later UX increment.
	  - Cross-tab sync animation when something changes elsewhere in the
	    dock — relies on a notification surface we have not designed yet.

	Mock: public_map/mocks/browse/mobile-dock.html, <section class="tab tab-saved">.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from './store.svelte';
	import { jobProfile } from './jobProfile.svelte';
	import { loadJobDetailsIndex } from './data';
	import {
		cloneFilters,
		loadSavedSearches,
		renameSavedSearch,
		saveSavedSearches,
		type SavedSearch
	} from './savedSearches';
	import { relativeTime, summariseSavedSearch } from './savedTab';

	interface Props {
		// Parent passes `() => (tab = 'list')` so Apply on a Job List can
		// switch the dock to the List tab where the restored filters render.
		onViewList?: () => void;
	}

	let { onViewList }: Props = $props();

	type SubTab = 'lists' | 'postings' | 'hidden' | 'viewed';
	let sub = $state<SubTab>('lists');

	// savedSearches lives in localStorage, not in a reactive store. We hold a
	// local $state snapshot and re-read after every mutation we make here.
	let searches = $state<SavedSearch[]>([]);
	let renamingId = $state<string | null>(null);
	let renameValue = $state('');

	// Details index for Hidden + Viewed-closed sub-tabs. Loaded once on mount.
	// Typed to match jobProfile.viewedClosedJobs's contract (`agency?: string`)
	// — narrower than JobDetails. We coerce nullable strings to `undefined` at
	// the load step.
	type DetailRow = {
		title?: string;
		close_date?: string | null;
		url?: string | null;
		agency?: string;
	};
	let details = $state<Record<string, DetailRow>>({});
	let detailsLoaded = $state(false);

	// "now" used by relativeTime; refreshed only on tab switch / mount to
	// avoid an unnecessary re-render storm.
	let now = $state(Date.now());

	onMount(() => {
		if (!browser) return;
		searches = loadSavedSearches();
		loadJobDetailsIndex()
			.then((idx) => {
				// Coerce nullable agency to undefined to match DetailRow.
				const out: Record<string, DetailRow> = {};
				for (const [id, row] of Object.entries(idx)) {
					out[id] = {
						title: row.title,
						close_date: row.close_date,
						url: row.url,
						agency: row.agency ?? undefined
					};
				}
				details = out;
			})
			.catch(() => {
				details = {};
			})
			.finally(() => {
				detailsLoaded = true;
			});
	});

	// --- Job Lists -----------------------------------------------------------

	function applyList(item: SavedSearch) {
		// Single-source-of-truth: assign the whole filters object so consumers
		// (JobList, AgencyPicker, FilterPanel) see one updated reference.
		mapState.filters = cloneFilters(item.filters);
		if (item.metric) mapState.metric = item.metric;
		// Refresh "now" so the relative-time copy stays current after Apply.
		now = Date.now();
		onViewList?.();
	}

	function startRename(item: SavedSearch) {
		renamingId = item.id;
		renameValue = item.name;
	}

	function commitRename(item: SavedSearch) {
		const next = searches.map((candidate) =>
			candidate.id === item.id ? renameSavedSearch(candidate, renameValue) : candidate
		);
		saveSavedSearches(next);
		searches = loadSavedSearches();
		renamingId = null;
		renameValue = '';
	}

	function cancelRename() {
		renamingId = null;
		renameValue = '';
	}

	function deleteList(id: string) {
		const next = searches.filter((candidate) => candidate.id !== id);
		saveSavedSearches(next);
		searches = loadSavedSearches();
		if (renamingId === id) cancelRename();
	}

	// --- My Postings ---------------------------------------------------------

	function openPosting(id: string, url: string | null) {
		jobProfile.markViewed(id);
		// Anchor's default behavior already opens the URL — we just record
		// the view. No action when url is missing.
		if (!url && browser) {
			// Surface the job card via the existing selectedFeature flow used
			// on /map. /browse does not render a selectedFeature, so this is
			// a no-op there, but it keeps the click meaningful if someone
			// embeds SavedTab elsewhere.
			mapState.selectedFeature = {
				source: 'profile',
				label: 'Job card',
				properties: { id }
			};
		}
	}

	function removePosting(id: string) {
		jobProfile.unsaveJob(id);
	}

	// --- Hidden --------------------------------------------------------------

	function unhide(id: string) {
		jobProfile.unhideJob(id);
		// Keep the map's hidden set in sync the same way ProfileDrawer does.
		mapState.hiddenJobIds = jobProfile.hiddenIds;
	}

	// --- Derived sub-tab data -------------------------------------------------

	const savedJobs = $derived(jobProfile.savedJobs);
	const hiddenJobs = $derived(jobProfile.hiddenJobs);
	const viewedClosed = $derived(jobProfile.viewedClosedJobs(details));

	const listsCount = $derived(searches.length);
	const postingsCount = $derived(savedJobs.length);
	const hiddenCount = $derived(hiddenJobs.length);
	const viewedClosedCount = $derived(viewedClosed.length);
</script>

<section class="tab-saved">
	<div class="eyebrow">My jobs</div>
	<h2>Saved &amp; tracked</h2>

	<div class="sub-tabs" role="tablist" aria-label="Saved sections">
		<button
			type="button"
			role="tab"
			aria-selected={sub === 'lists'}
			class="pill-btn"
			class:active={sub === 'lists'}
			onclick={() => (sub = 'lists')}
		>
			Job Lists ({listsCount})
		</button>
		<button
			type="button"
			role="tab"
			aria-selected={sub === 'postings'}
			class="pill-btn"
			class:active={sub === 'postings'}
			onclick={() => (sub = 'postings')}
		>
			My Postings ({postingsCount})
		</button>
		<button
			type="button"
			role="tab"
			aria-selected={sub === 'hidden'}
			class="pill-btn"
			class:active={sub === 'hidden'}
			onclick={() => (sub = 'hidden')}
		>
			Hidden ({hiddenCount})
		</button>
		<button
			type="button"
			role="tab"
			aria-selected={sub === 'viewed'}
			class="pill-btn"
			class:active={sub === 'viewed'}
			onclick={() => (sub = 'viewed')}
		>
			Viewed-closed ({viewedClosedCount})
		</button>
	</div>

	<!-- ===================== Job Lists ===================== -->
	{#if sub === 'lists'}
		{#if listsCount === 0}
			<p class="empty-note">No saved Job Lists yet. Save a filter from the List tab.</p>
		{:else}
			{#each searches as item (item.id)}
				<article class="saved-row">
					{#if renamingId === item.id}
						<div class="rename-row">
							<input
								type="text"
								value={renameValue}
								oninput={(e) => (renameValue = e.currentTarget.value)}
								onkeydown={(e) => {
									if (e.key === 'Enter') commitRename(item);
									else if (e.key === 'Escape') cancelRename();
								}}
								aria-label="Rename saved Job List"
							/>
							<div class="row-mini-actions">
								<button type="button" onclick={() => commitRename(item)}>Save</button>
								<button type="button" onclick={cancelRename}>Cancel</button>
							</div>
						</div>
					{:else}
						<div class="title">
							<span class="joblist-tag">JOB LIST</span>
							{item.name}
						</div>
						<div class="meta">{summariseSavedSearch(item)}</div>
						<div class="row-mini-actions">
							<button type="button" onclick={() => applyList(item)}>Apply</button>
							<button type="button" onclick={() => startRename(item)}>Rename</button>
							<button type="button" class="danger" onclick={() => deleteList(item.id)}>
								Delete
							</button>
						</div>
					{/if}
				</article>
			{/each}
			<p class="empty-note">
				Job Lists persist a whole filtered search. They are separate from the
				dashboard's Application Tracker.
			</p>
		{/if}

	<!-- ===================== My Postings ===================== -->
	{:else if sub === 'postings'}
		{#if postingsCount === 0}
			<p class="empty-note">No saved postings yet. Save one from the List tab.</p>
		{:else}
			{#each savedJobs as job (job.id)}
				<article class="saved-row">
					<div class="title">
						{#if job.url}
							<a
								class="title-link"
								href={job.url}
								target="_blank"
								rel="noreferrer noopener"
								onclick={() => openPosting(job.id, job.url)}
							>
								★ {job.title}
							</a>
						{:else}
							<span>★ {job.title}</span>
						{/if}
					</div>
					<div class="meta">
						{job.agency || '—'} · closes {job.close_date ?? '—'} · saved {relativeTime(job.ts, now)}
					</div>
					<div class="row-mini-actions">
						{#if job.url}
							<a
								class="link-btn"
								href={job.url}
								target="_blank"
								rel="noreferrer noopener"
								onclick={() => openPosting(job.id, job.url)}
							>
								Open ↗
							</a>
						{/if}
						<button type="button" class="danger" onclick={() => removePosting(job.id)}>
							Remove
						</button>
					</div>
				</article>
			{/each}
			<p class="empty-note">
				My Postings persists one posting at a time. It is not an application — use the
				dashboard's Application Tracker for that.
			</p>
		{/if}

	<!-- ===================== Hidden ===================== -->
	{:else if sub === 'hidden'}
		{#if hiddenCount === 0}
			<p class="empty-note">
				No hidden postings. Use Hide on a List row to remove a posting from the map and list.
			</p>
		{:else}
			{#each hiddenJobs as entry (entry.id)}
				{@const d = details[entry.id]}
				<article class="saved-row">
					<div class="title">
						{d?.title ?? `Job #${entry.id}`}
					</div>
					<div class="meta">
						{#if d}
							{d.agency || '—'} · closes {d.close_date ?? '—'} · hidden {relativeTime(entry.ts, now)}
						{:else if detailsLoaded}
							details unavailable · hidden {relativeTime(entry.ts, now)}
						{:else}
							loading… · hidden {relativeTime(entry.ts, now)}
						{/if}
					</div>
					<div class="row-mini-actions">
						<button type="button" onclick={() => unhide(entry.id)}>Unhide</button>
					</div>
				</article>
			{/each}
			<p class="empty-note">
				Hidden postings drop out of the map, the list, and scoped counts until you unhide them.
			</p>
		{/if}

	<!-- ===================== Viewed-closed ===================== -->
	{:else}
		{#if viewedClosedCount === 0}
			<p class="empty-note">No viewed postings have closed yet.</p>
		{:else}
			{#each viewedClosed as entry (entry.id)}
				<article class="saved-row">
					<div class="title">{entry.title}</div>
					<div class="meta">closed {entry.close_date}</div>
				</article>
			{/each}
			<p class="empty-note">Postings you viewed that have since closed — kept for reference.</p>
		{/if}
	{/if}
</section>

<style>
	.tab-saved {
		padding: 0.9rem 1rem 1.2rem;
		max-width: 36rem;
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
		margin: 0.2rem 0 0;
		font-size: 18px;
		line-height: 1.2;
	}

	/* Sub-tab pill row — mirrors the mock's .sub-tabs. */
	.sub-tabs {
		display: flex;
		gap: 0.25rem;
		margin: 0.5rem 0 0.7rem;
		overflow-x: auto;
		-webkit-overflow-scrolling: touch;
	}
	.sub-tabs .pill-btn {
		appearance: none;
		flex-shrink: 0;
		font: inherit;
		font-size: 10px;
		font-weight: 600;
		padding: 0.35rem 0.7rem;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		cursor: pointer;
		white-space: nowrap;
		transition: border-color 100ms ease, color 100ms ease, background 100ms ease;
	}
	.sub-tabs .pill-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.sub-tabs .pill-btn.active {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border-color: var(--c-accent-dim, #4979b3);
		color: var(--c-accent, #7bd0f2);
	}

	/* Rows — match the mock's .saved-row. */
	.saved-row {
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 6px;
		padding: 0.55rem 0.6rem;
		margin-bottom: 0.4rem;
	}
	.saved-row .title {
		font-size: 12px;
		font-weight: 600;
		color: var(--c-text, #e5edf5);
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex-wrap: wrap;
		line-height: 1.35;
	}
	.saved-row .title-link {
		color: inherit;
		text-decoration: none;
	}
	.saved-row .title-link:hover {
		color: var(--c-accent, #7bd0f2);
		text-decoration: underline;
	}
	.saved-row .joblist-tag {
		font-size: 8px;
		font-weight: 700;
		letter-spacing: 0.04em;
		padding: 0.05rem 0.35rem;
		border-radius: 3px;
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
		border: 1px solid var(--c-accent-dim, #4979b3);
	}
	.saved-row .meta {
		font-size: 10px;
		color: var(--c-muted, #94a3b8);
		margin-top: 0.2rem;
		line-height: 1.45;
	}
	.saved-row .row-mini-actions {
		margin-top: 0.4rem;
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
	}
	.saved-row .row-mini-actions button,
	.saved-row .row-mini-actions .link-btn {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-bg, #06111f);
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 9px;
		font-weight: 600;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		cursor: pointer;
		text-decoration: none;
		display: inline-flex;
		align-items: center;
	}
	.saved-row .row-mini-actions button:hover,
	.saved-row .row-mini-actions .link-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.saved-row .row-mini-actions .danger {
		border-color: var(--c-border-input, #2c4870);
		color: var(--c-text-2, #cfd9e6);
	}
	.saved-row .row-mini-actions .danger:hover {
		border-color: #c87c7c;
		color: #c87c7c;
	}

	.rename-row {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.rename-row input {
		width: 100%;
		box-sizing: border-box;
		background: var(--c-bg, #06111f);
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 6px;
		padding: 0.35rem 0.5rem;
		font: inherit;
		font-size: 12px;
	}
	.rename-row input:focus {
		outline: none;
		border-color: var(--c-accent, #7bd0f2);
	}

	.empty-note {
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
		padding: 0.5rem 0.1rem;
		margin: 0.4rem 0 0;
		line-height: 1.55;
	}
</style>
