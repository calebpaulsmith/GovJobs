<!--
	Browse map bottom sheet. Sits over the bottom of the full-screen map and
	holds two swipeable pages:
	  • "Here"     — the tapped area's card (State / Locality / County), a job
	                 card for a tapped marker, or the smallest enclosing area for
	                 the viewport when nothing is selected.
	  • "Postings" — the shared JobList (rich mode), i.e. the working list the
	                 filters produce and that can be saved.

	Pages switch by horizontal swipe (page dots show which page + that you can
	swipe) or by tapping the pill labels. The last page is remembered in
	localStorage, defaulting to Postings. Tapping any feature on the map auto-
	opens the sheet to the Here page. "Add this area to my list" is the explicit,
	opt-in way to narrow the working list by geography (no auto-chips on tap).

	Swipe vs. scroll: the pager sets `touch-action: pan-y`, so the browser keeps
	handling vertical scroll of the active panel natively while horizontal drags
	are delivered to our handlers — no preventDefault, no scroll hijacking.
-->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState, type ListView } from './store.svelte';

	// Default Postings-tab scope when the user hasn't tapped a polygon
	// or cluster yet. Filters by what's currently visible on the map.
	const DEFAULT_VIEWPORT_SCOPE: ListView = {
		scope: 'viewport',
		code: '',
		label: 'this area'
	};
	import { LAYER_IDS } from './layers';
	import { propString, countValue } from './format';
	import { createSavedSearch, loadSavedSearches, saveSavedSearches } from './savedSearches';
	import ActiveFilterStrip from './ActiveFilterStrip.svelte';
	import AddressSearch from './AddressSearch.svelte';
	import StateRoundup from './StateRoundup.svelte';
	import LocalityDetail from './LocalityDetail.svelte';
	import CountyDetail from './CountyDetail.svelte';
	import SmallestAreaCard from './SmallestAreaCard.svelte';
	import JobCard from './JobCard.svelte';
	import JobList from './JobList.svelte';
	import PointJobList from './PointJobList.svelte';

	const PAGE_KEY = 'fedfinder.public_map.browse_sheet_page.v1';
	const WELCOME_KEY = 'fedfinder.public_map.browse_welcome.v1';

	// D.6.4 (ADR-0035): first-run welcome card in the Here panel. Defaults to
	// dismissed so it never flashes before onMount reads the flag.
	let welcomeDismissed = $state(true);

	function dismissWelcome() {
		welcomeDismissed = true;
		if (browser) localStorage.setItem(WELCOME_KEY, '1');
	}

	// Restore the last page (Postings by default), then persist on change.
	onMount(() => {
		if (!browser) return;
		welcomeDismissed = localStorage.getItem(WELCOME_KEY) === '1';
		const stored = localStorage.getItem(PAGE_KEY);
		if (stored === 'here' || stored === 'list') mapState.browseSheetPage = stored;
	});
	$effect(() => {
		if (!browser) return;
		localStorage.setItem(PAGE_KEY, mapState.browseSheetPage);
	});

	// D.5.29: capture/restore the Postings list scroll for shareable URLs. The
	// `.panel` is the scroll container; the fraction (0..1) round-trips through
	// the share link. Capture happens in an event handler (no effect); restore
	// runs in an effect that wraps its mapState write in untrack.
	let postingsPanel = $state<HTMLElement | null>(null);
	function onPostingsScroll() {
		const el = postingsPanel;
		if (!el) return;
		const max = el.scrollHeight - el.clientHeight;
		mapState.listScroll = max > 0 ? Math.min(1, Math.max(0, el.scrollTop / max)) : 0;
	}
	$effect(() => {
		const frac = mapState.pendingListScroll;
		const el = postingsPanel;
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

	// Auto-open the Here page (expanded) when a new feature/point is tapped.
	// Tracks selection identity so switching to Postings while a feature stays
	// selected doesn't get yanked back to Here.
	let lastSelection: unknown = null;
	$effect(() => {
		const sel = mapState.selectedFeature ?? mapState.jobStack;
		if (sel && sel !== lastSelection) {
			// untrack the writes back to mapState so this effect doesn't
			// subscribe to the very same properties it mutates. Without
			// untrack, WebKit's Svelte 5 scheduler treats the read-then-
			// write of mapState as a `state_unsafe_mutation` and bails the
			// effect tree out, which produces the operator-reported "tap a
			// locality, then the Filters FAB and sheet stop responding"
			// freeze. Chromium's scheduler is more lenient here, so the
			// dev harness didn't catch this.
			untrack(() => {
				mapState.browseSheetPage = 'here';
				mapState.browseSheetExpanded = true;
			});
		}
		lastSelection = sel;
	});

	function toggleExpanded() {
		if (mapState.browseSheetExpanded) {
			// Collapsing also drops the full detent so the next open starts
			// partway again.
			mapState.browseSheetExpanded = false;
			mapState.browseSheetFull = false;
		} else {
			mapState.browseSheetExpanded = true;
		}
	}

	function setPage(page: 'here' | 'list') {
		mapState.browseSheetPage = page;
		mapState.browseSheetExpanded = true;
	}

	// --- vertical drag-to-resize on the grabber ---
	// Three detents: collapsed (peek), half (partway — taps still reach the
	// map), and full (near-full height so the user can scroll the whole list).
	// Tap (no movement) keeps toggling collapsed↔open via the button's onclick;
	// a drag snaps to the nearest detent. Live height drives an inline style so
	// the sheet follows the finger; on release we clear it and let the CSS class
	// transition to the snapped detent.
	let sheetEl = $state<HTMLElement | null>(null);
	let dragH = $state<number | null>(null);
	let grabbing = false;
	let grabStartY = 0;
	let grabStartH = 0;
	let grabMoved = false;

	function detents() {
		// The sheet is position:absolute, so its CSS `%` heights resolve
		// against its offsetParent — not the window. Measure that same box so
		// the drag math lines up exactly with the resting CSS detents (50% /
		// 92%). Falling back to the window only matters before first layout.
		const parentH =
			sheetEl?.offsetParent?.getBoundingClientRect().height ??
			(browser ? window.innerHeight : 800);
		return { collapsed: 3.6 * 16, half: parentH * 0.5, full: parentH * 0.92 };
	}

	function onGrabPointerDown(e: PointerEvent) {
		grabbing = true;
		grabMoved = false;
		grabStartY = e.clientY;
		grabStartH = sheetEl?.getBoundingClientRect().height ?? detents().collapsed;
		(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
	}
	function onGrabPointerMove(e: PointerEvent) {
		if (!grabbing) return;
		const dy = grabStartY - e.clientY; // drag up → taller
		if (Math.abs(dy) > 4) grabMoved = true;
		const d = detents();
		dragH = Math.max(d.collapsed, Math.min(d.full, grabStartH + dy));
	}
	function onGrabPointerUp(e: PointerEvent) {
		if (!grabbing) return;
		grabbing = false;
		(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
		const moved = grabMoved;
		const h = dragH ?? grabStartH;
		dragH = null;
		if (!moved) {
			// A tap (no drag): toggle collapsed↔open. We handle this here in
			// pointerup rather than via the button's click, because on WebKit
			// the synthetic click still fires after a drag and would undo the
			// snap below — so the grabber has no onclick at all.
			toggleExpanded();
			return;
		}
		const d = detents();
		const opts: [string, number][] = [
			['collapsed', d.collapsed],
			['half', d.half],
			['full', d.full]
		];
		let best = opts[0];
		for (const o of opts) {
			if (Math.abs(o[1] - h) < Math.abs(best[1] - h)) best = o;
		}
		if (best[0] === 'collapsed') {
			mapState.browseSheetExpanded = false;
			mapState.browseSheetFull = false;
		} else if (best[0] === 'half') {
			mapState.browseSheetExpanded = true;
			mapState.browseSheetFull = false;
		} else {
			mapState.browseSheetExpanded = true;
			mapState.browseSheetFull = true;
		}
	}
	function onGrabPointerCancel() {
		grabbing = false;
		dragH = null;
	}
	// Keyboard a11y: the grabber has no onclick (see onGrabPointerUp), so wire
	// Enter/Space to the same collapsed↔open toggle.
	function onGrabKey(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			toggleExpanded();
		}
	}

	// Render the panels while open OR mid-drag (so dragging up from collapsed
	// reveals content immediately instead of an empty growing box).
	const showContent = $derived(mapState.browseSheetExpanded || dragH !== null);

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

	// Explicit, opt-in geography add. Mirrors the chip format ScopedAreaActions
	// uses on /map so the two paths produce identical, deduped chips.
	function addAreaToList(type: 'state' | 'locality', code: string) {
		const value = String(code ?? '').trim().toUpperCase();
		if (!value) return;
		const chip = `${type}:${value}`;
		if (mapState.filters.geographies.includes(chip)) return;
		mapState.filters = {
			...mapState.filters,
			geographies: [...mapState.filters.geographies, chip]
		};
	}

	function isInList(type: 'state' | 'locality', code: string): boolean {
		return mapState.filters.geographies.includes(`${type}:${String(code ?? '').trim().toUpperCase()}`);
	}

	// --- horizontal swipe between the two pages ---
	let pagerEl = $state<HTMLDivElement | null>(null);
	let dragging = $state(false);
	let dragPx = $state(0);
	let startX = 0;
	let startY = 0;
	let axis: 'h' | 'v' | null = null;

	const pageIndex = $derived(mapState.browseSheetPage === 'here' ? 0 : 1);

	function onTouchStart(e: TouchEvent) {
		if (e.touches.length !== 1) return;
		startX = e.touches[0].clientX;
		startY = e.touches[0].clientY;
		axis = null;
		dragPx = 0;
	}
	function onTouchMove(e: TouchEvent) {
		if (e.touches.length !== 1) return;
		const dx = e.touches[0].clientX - startX;
		const dy = e.touches[0].clientY - startY;
		if (axis === null) {
			if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
			axis = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v';
		}
		if (axis !== 'h') return;
		dragging = true;
		// Only allow dragging toward the page that exists in that direction.
		dragPx = pageIndex === 0 ? Math.min(0, dx) : Math.max(0, dx);
	}
	function onTouchEnd() {
		if (axis === 'h' && pagerEl) {
			const w = pagerEl.clientWidth || 1;
			const ratio = dragPx / w;
			if (pageIndex === 0 && ratio < -0.2) setPage('list');
			else if (pageIndex === 1 && ratio > 0.2) setPage('here');
		}
		dragging = false;
		dragPx = 0;
		axis = null;
	}

	const sel = $derived(mapState.selectedFeature);
	const peekLabel = $derived.by(() => {
		if (mapState.jobStack && !sel) return mapState.jobStack.label;
		if (sel) {
			const p = sel.properties;
			return String(p.name ?? p.title ?? p.state ?? p.code ?? sel.label);
		}
		return `${mapState.filteredJobCount.toLocaleString()} postings`;
	});
</script>

<aside
	class="sheet"
	class:expanded={mapState.browseSheetExpanded}
	class:full={mapState.browseSheetFull}
	style={dragH !== null ? `height: ${dragH}px; transition: none;` : undefined}
	bind:this={sheetEl}
	aria-label="Area and postings"
>
	<button
		type="button"
		class="grabber"
		onpointerdown={onGrabPointerDown}
		onpointermove={onGrabPointerMove}
		onpointerup={onGrabPointerUp}
		onpointercancel={onGrabPointerCancel}
		onkeydown={onGrabKey}
		aria-expanded={mapState.browseSheetExpanded}
		aria-label={mapState.browseSheetExpanded ? 'Collapse panel' : 'Expand panel'}
	>
		<span class="grip" aria-hidden="true"></span>
	</button>

	{#if showContent}
		<div class="pager-head">
			<div class="seg" role="tablist" aria-label="Panel view">
				<button type="button" role="tab" aria-selected={mapState.browseSheetPage === 'here'} class:active={mapState.browseSheetPage === 'here'} onclick={() => setPage('here')}>
					Here
				</button>
				<button type="button" role="tab" aria-selected={mapState.browseSheetPage === 'list'} class:active={mapState.browseSheetPage === 'list'} onclick={() => setPage('list')}>
					Postings
				</button>
			</div>
			<div class="dots" aria-hidden="true" title="Swipe to switch">
				<span class="dot" class:on={mapState.browseSheetPage === 'here'}></span>
				<span class="dot" class:on={mapState.browseSheetPage === 'list'}></span>
			</div>
		</div>

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="pager"
			bind:this={pagerEl}
			ontouchstart={onTouchStart}
			ontouchmove={onTouchMove}
			ontouchend={onTouchEnd}
			ontouchcancel={onTouchEnd}
		>
			<div
				class="track"
				class:dragging
				style="transform: translateX(calc({pageIndex * -100}% + {dragPx}px));"
			>
				<div class="panel">
					{#if mapState.jobStack && !sel}
						<!-- {#key} forces PointJobList to fully remount when the
						     jobStack's items count changes. The cluster path
						     seeds an empty stack synchronously from the click
						     handler (so this branch is selected immediately) and
						     then the async leaves callback fills in the items.
						     Without the key, PointJobList's `stack` prop doesn't
						     re-evaluate when mapState.jobStack is replaced from
						     the actor callback. Keying on items.length triggers
						     a clean remount once the leaves arrive. -->
						{#key mapState.jobStack.items.length}
							<PointJobList stack={mapState.jobStack} />
						{/key}
					{:else if sel}
						{#if sel.source === LAYER_IDS.markers}
							<JobCard properties={sel.properties} />
						{:else if sel.source === LAYER_IDS.statesFill}
							<button
								type="button"
								class="add-area"
								disabled={isInList('state', String(sel.properties.state ?? ''))}
								onclick={() => addAreaToList('state', String(sel.properties.state ?? ''))}
							>
								{isInList('state', String(sel.properties.state ?? '')) ? '✓ In your list' : '+ Add this area to my list'}
							</button>
							<StateRoundup properties={sel.properties} />
						{:else if sel.source === LAYER_IDS.localitiesFill}
							<button
								type="button"
								class="add-area"
								disabled={isInList('locality', String(sel.properties.code ?? ''))}
								onclick={() => addAreaToList('locality', String(sel.properties.code ?? ''))}
							>
								{isInList('locality', String(sel.properties.code ?? '')) ? '✓ In your list' : '+ Add this area to my list'}
							</button>
							<LocalityDetail properties={sel.properties} />
						{:else if sel.source === LAYER_IDS.countiesOutline}
							<CountyDetail properties={sel.properties} />
						{:else}
							<section class="generic">
								<h2>{propString(sel.properties, 'name')}</h2>
								<dl>
									<dt>Open postings</dt><dd>{countValue(sel.properties.postings)}</dd>
									{#if sel.properties.cbsa_code}<dt>CBSA</dt><dd>{propString(sel.properties, 'cbsa_code')}</dd>{/if}
									{#if sel.properties.agency}<dt>Agency</dt><dd>{propString(sel.properties, 'agency')}</dd>{/if}
								</dl>
							</section>
						{/if}
					{:else}
						{#if !welcomeDismissed}
							<div class="welcome" role="region" aria-label="Getting started">
								<div class="welcome-head">
									<h2>Find your federal job</h2>
									<button type="button" class="welcome-close" onclick={dismissWelcome} aria-label="Dismiss welcome">✕</button>
								</div>
								<p class="welcome-sub">Jump to where you'd work, or browse everything that's open.</p>
								<AddressSearch docked onChoose={dismissWelcome} />
								<div class="welcome-actions">
									<button
										type="button"
										class="welcome-btn"
										onclick={() => {
											dismissWelcome();
											setPage('list');
										}}
									>
										See postings list
									</button>
									<button
										type="button"
										class="welcome-btn"
										onclick={() => {
											dismissWelcome();
											mapState.browseSheetExpanded = false;
											mapState.browseSheetFull = false;
										}}
									>
										Explore the map
									</button>
								</div>
							</div>
						{/if}
						<SmallestAreaCard onViewList={() => setPage('list')} />
					{/if}
				</div>
				<div class="panel" bind:this={postingsPanel} onscroll={onPostingsScroll}>
					<div class="scoped-head">
						<p class="eyebrow">Postings in {mapState.listView?.label ?? 'this area'}</p>
						{#if mapState.listView}
							<button type="button" class="clear-scope" onclick={() => (mapState.listView = null)} aria-label="Clear scope">
								× show this area
							</button>
						{/if}
					</div>
					<!-- D.6.1 task spine: criteria live on the same surface as the
					     results they produce. Same chip component as /map (docked). -->
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
			</div>
		</div>
	{:else}
		<button type="button" class="peek" onclick={toggleExpanded}>
			<span class="peek-label">{peekLabel}</span>
			<span class="peek-hint">tap to browse ▴</span>
		</button>
	{/if}
</aside>

<style>
	.sheet {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		/* Above the embedded map AND its overlays (the map's "back to national"
		   pill is z-index 8 and appears on selection); below the filter/saved
		   drawers (z-index 29/30). pointer-events:auto guarantees the sheet
		   captures taps even while sitting over the interactive map canvas. */
		z-index: 20;
		pointer-events: auto;
		height: 3.6rem;
		display: flex;
		flex-direction: column;
		background: var(--c-panel, rgba(14, 23, 38, 0.98));
		border-top: 1px solid var(--c-border, #2a3a52);
		border-top-left-radius: 14px;
		border-top-right-radius: 14px;
		box-shadow: 0 -8px 28px rgba(0, 0, 0, 0.35);
		transition: height 220ms ease;
		overflow: hidden;
	}
	.sheet.expanded {
		/* Auto-expanded on selection. Keep this short enough that the user
		   can still see and tap the map underneath to pick a different
		   feature — otherwise the panel "gets stuck" on the first tap, since
		   the sheet absorbs taps and there's no map left to click. The
		   grabber can be dragged further by users who want more detail.
		   On wide screens the sheet is centered with max-width and the rest
		   of the page is map, so 50% is fine. */
		height: 50%;
	}
	.sheet.expanded.full {
		/* Second detent: drag the grabber all the way up to scroll through the
		   whole list. Stops short of the very top so the masthead/controls and
		   a sliver of map stay reachable. */
		height: 92%;
	}
	.grabber {
		appearance: none;
		flex-shrink: 0;
		width: 100%;
		background: transparent;
		border: none;
		padding: 0.5rem 0 0.3rem;
		cursor: grab;
		/* Own vertical gestures so dragging the grabber resizes the sheet
		   instead of scrolling the page/panel underneath. */
		touch-action: none;
	}
	.grabber:active {
		cursor: grabbing;
	}
	.grip {
		display: block;
		width: 2.5rem;
		height: 4px;
		margin: 0 auto;
		border-radius: 999px;
		background: var(--c-border-input, #2c4870);
	}
	.pager-head {
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 0.35rem;
		padding: 0 0.75rem 0.4rem;
	}
	.seg {
		display: flex;
		gap: 0.25rem;
	}
	.seg button {
		appearance: none;
		flex: 1;
		border: 1px solid var(--c-border, #2a3a52);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.4rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.seg button.active {
		border-color: var(--c-accent, #7bd0f2);
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		color: var(--c-accent, #7bd0f2);
	}
	.dots {
		display: flex;
		justify-content: center;
		gap: 0.35rem;
	}
	.dot {
		width: 6px;
		height: 6px;
		border-radius: 999px;
		background: var(--c-border-input, #2c4870);
		transition: background 150ms ease, width 150ms ease;
	}
	.dot.on {
		width: 16px;
		background: var(--c-accent, #7bd0f2);
	}
	.pager {
		flex: 1;
		overflow: hidden;
		touch-action: pan-y;
	}
	.track {
		display: flex;
		height: 100%;
		transition: transform 250ms ease;
	}
	.track.dragging {
		transition: none;
	}
	.panel {
		flex: 0 0 100%;
		height: 100%;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		padding: 0.25rem 0.75rem 1rem;
		color: var(--c-text-2, #cfd9e6);
		font-size: 12px;
	}
	.panel:last-child {
		padding: 0;
	}
	.peek {
		appearance: none;
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		width: 100%;
		background: transparent;
		border: none;
		padding: 0 0.95rem 0.5rem;
		cursor: pointer;
		color: var(--c-text, #e5edf5);
	}
	.peek-label {
		font-size: 13px;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.peek-hint {
		flex-shrink: 0;
		font-size: 11px;
		font-weight: 600;
		color: var(--c-accent, #7bd0f2);
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
	.add-area {
		appearance: none;
		width: 100%;
		margin-bottom: 0.6rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 8px;
		background: var(--c-accent-bg-strong, rgba(73, 121, 179, 0.2));
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.55rem;
		cursor: pointer;
	}
	.add-area:hover:not(:disabled) {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.add-area:disabled {
		cursor: default;
		opacity: 0.7;
		border-color: #5e9a4a;
		background: rgba(94, 154, 74, 0.15);
	}
	.welcome {
		margin-bottom: 0.7rem;
		padding: 0.7rem 0.75rem 0.8rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 10px;
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.1));
	}
	.welcome-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.welcome-head h2 {
		margin: 0;
		font-size: 16px;
		color: var(--c-text, #e5edf5);
	}
	.welcome-close {
		appearance: none;
		border: none;
		background: none;
		color: var(--c-muted, #94a3b8);
		font-size: 14px;
		cursor: pointer;
		padding: 0.15rem 0.35rem;
		border-radius: 4px;
	}
	.welcome-close:hover {
		color: var(--c-text, #e5edf5);
		background: rgba(255, 255, 255, 0.07);
	}
	.welcome-sub {
		margin: 0.25rem 0 0.6rem;
		font-size: 12px;
		color: var(--c-text-2, #cfd9e6);
		line-height: 1.45;
	}
	.welcome-actions {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.6rem;
	}
	.welcome-btn {
		appearance: none;
		flex: 1;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.45rem;
		border-radius: 8px;
		cursor: pointer;
	}
	.welcome-btn:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.generic h2 {
		margin: 0 0 0.6rem;
		font-size: 18px;
		color: var(--c-text, #e5edf5);
	}
	.generic dl {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.4rem 0.8rem;
		margin: 0;
	}
	.generic dt {
		color: var(--c-muted, #94a3b8);
	}
	.generic dd {
		margin: 0;
		font-weight: 600;
		text-align: right;
		color: var(--c-text-2, #cfd9e6);
	}
</style>
