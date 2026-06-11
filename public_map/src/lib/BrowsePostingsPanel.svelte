<!--
	BrowsePostingsPanel — the "Postings" content for /browse, shared by two
	hosts: BrowseSheet (mobile bottom sheet, < 1024 px) and the desktop
	mosaic's bottom pane (≥ 1024 px).

	The D.6.1 task spine: the docked ActiveFilterStrip, an Edit button (opens
	the shared FilterSheet), and a Save-search button sit directly above the
	rich JobList, so criteria and the results they produce share one surface.

	This component owns its scroll container, including the D.5.29 share-link
	scroll capture/restore (mapState.listScroll / pendingListScroll), so the
	behavior is identical in the sheet and in the desktop pane. Capture happens
	in an event handler (no effect); restore runs in an effect that wraps its
	mapState write in untrack (WebKit state_unsafe_mutation rule).
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import { mapState, type ListView } from './store.svelte';
	import { createSavedSearch, loadSavedSearches, saveSavedSearches } from './savedSearches';
	import ActiveFilterStrip from './ActiveFilterStrip.svelte';
	import JobList from './JobList.svelte';

	// Default Postings scope when the user hasn't tapped a polygon or cluster
	// yet. Filters by what's currently visible on the map.
	const DEFAULT_VIEWPORT_SCOPE: ListView = {
		scope: 'viewport',
		code: '',
		label: 'this area'
	};

	let scroller = $state<HTMLElement | null>(null);

	function onScroll() {
		const el = scroller;
		if (!el) return;
		const max = el.scrollHeight - el.clientHeight;
		mapState.listScroll = max > 0 ? Math.min(1, Math.max(0, el.scrollTop / max)) : 0;
	}

	$effect(() => {
		const frac = mapState.pendingListScroll;
		const el = scroller;
		if (frac == null || !el) return;
		// Wait two frames so the list has a chance to render its rows (and grow
		// scrollHeight) before we restore; best-effort, degrades to top-of-list.
		requestAnimationFrame(() =>
			requestAnimationFrame(() => {
				const max = el.scrollHeight - el.clientHeight;
				if (max > 0) el.scrollTop = frac * max;
			})
		);
		untrack(() => {
			mapState.pendingListScroll = null;
		});
	});

	// --- Save current search (D.6.1) -------------------------------------
	// Inline name input → createSavedSearch; lands in SavedTab's Job Lists.
	let savingSearch = $state(false);
	let saveName = $state('');
	let saveConfirmed = $state(false);
	let saveConfirmTimer: ReturnType<typeof setTimeout> | null = null;

	function startSaveSearch() {
		savingSearch = true;
		saveConfirmed = false;
		saveName = `Search ${new Date().toLocaleDateString()}`;
	}

	function commitSaveSearch() {
		const item = createSavedSearch({
			name: saveName,
			filters: mapState.filters,
			metric: mapState.metric,
			viewport: mapState.viewport,
			addressTarget: mapState.lastAddressTarget
		});
		saveSavedSearches([...loadSavedSearches(), item]);
		savingSearch = false;
		saveName = '';
		saveConfirmed = true;
		if (saveConfirmTimer) clearTimeout(saveConfirmTimer);
		saveConfirmTimer = setTimeout(() => (saveConfirmed = false), 2500);
	}

	function cancelSaveSearch() {
		savingSearch = false;
		saveName = '';
	}
</script>

<div class="postings" bind:this={scroller} onscroll={onScroll}>
	<div class="scoped-head">
		<p class="eyebrow">Postings in {mapState.listView?.label ?? 'this area'}</p>
		{#if mapState.listView}
			<button type="button" class="clear-scope" onclick={() => (mapState.listView = null)} aria-label="Clear scope">
				× show this area
			</button>
		{/if}
	</div>
	<!-- D.6.1 task spine: criteria live on the same surface as the results
	     they produce. Same chip component as /map (docked). -->
	<div class="filters-row">
		<div class="strip-wrap"><ActiveFilterStrip docked /></div>
		<button type="button" class="head-btn" onclick={() => (mapState.filterSheetOpen = true)}>
			Edit
		</button>
		{#if saveConfirmed}
			<span class="save-ok" role="status">✓ Saved</span>
		{:else}
			<button type="button" class="head-btn" onclick={startSaveSearch}>Save</button>
		{/if}
	</div>
	{#if savingSearch}
		<div class="save-row">
			<input
				type="text"
				value={saveName}
				oninput={(e) => (saveName = e.currentTarget.value)}
				onkeydown={(e) => {
					if (e.key === 'Enter') commitSaveSearch();
					else if (e.key === 'Escape') cancelSaveSearch();
				}}
				aria-label="Name this search"
			/>
			<button type="button" class="head-btn primary" onclick={commitSaveSearch}>Save</button>
			<button type="button" class="head-btn" onclick={cancelSaveSearch}>Cancel</button>
		</div>
	{/if}
	<JobList listView={mapState.listView ?? DEFAULT_VIEWPORT_SCOPE} />
</div>

<style>
	.postings {
		height: 100%;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		color: var(--c-text-2, #cfd9e6);
		font-size: 12px;
	}
	.scoped-head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0 0.75rem 0.4rem;
	}
	.scoped-head .eyebrow {
		flex: 1;
		margin: 0;
		font-size: 11px;
		color: var(--c-accent, #7bd0f2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.clear-scope {
		appearance: none;
		flex-shrink: 0;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-muted, #94a3b8);
		font: inherit;
		font-size: 11px;
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.clear-scope:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.filters-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0 0.75rem 0.4rem;
	}
	.strip-wrap {
		flex: 1;
		min-width: 0;
	}
	.save-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0 0.75rem 0.4rem;
	}
	.save-row input {
		flex: 1;
		min-width: 0;
		box-sizing: border-box;
		background: var(--c-bg, #06111f);
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-text, #e5edf5);
		border-radius: 6px;
		padding: 0.35rem 0.5rem;
		font: inherit;
		font-size: 12px;
	}
	.save-row input:focus {
		outline: none;
		border-color: var(--c-accent, #7bd0f2);
	}
	.head-btn {
		appearance: none;
		flex-shrink: 0;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 11px;
		font-weight: 600;
		padding: 0.3rem 0.6rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.head-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.head-btn.primary {
		border-color: var(--c-accent-dim, #4979b3);
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
	}
	.save-ok {
		flex-shrink: 0;
		font-size: 11px;
		font-weight: 600;
		color: var(--c-success, #9be0b4);
	}
</style>
