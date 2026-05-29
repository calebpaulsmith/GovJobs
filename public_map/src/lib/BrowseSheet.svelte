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
	import { mapState } from './store.svelte';
	import { LAYER_IDS } from './layers';
	import { propString, countValue } from './format';
	import StateRoundup from './StateRoundup.svelte';
	import LocalityDetail from './LocalityDetail.svelte';
	import CountyDetail from './CountyDetail.svelte';
	import SmallestAreaCard from './SmallestAreaCard.svelte';
	import JobCard from './JobCard.svelte';
	import JobList from './JobList.svelte';
	import PointJobList from './PointJobList.svelte';

	const PAGE_KEY = 'fedfinder.public_map.browse_sheet_page.v1';

	// Restore the last page (Postings by default), then persist on change.
	onMount(() => {
		if (!browser) return;
		const stored = localStorage.getItem(PAGE_KEY);
		if (stored === 'here' || stored === 'list') mapState.browseSheetPage = stored;
	});
	$effect(() => {
		if (!browser) return;
		localStorage.setItem(PAGE_KEY, mapState.browseSheetPage);
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
		mapState.browseSheetExpanded = !mapState.browseSheetExpanded;
	}

	function setPage(page: 'here' | 'list') {
		mapState.browseSheetPage = page;
		mapState.browseSheetExpanded = true;
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

<aside class="sheet" class:expanded={mapState.browseSheetExpanded} aria-label="Area and postings">
	<button
		type="button"
		class="grabber"
		onclick={toggleExpanded}
		aria-expanded={mapState.browseSheetExpanded}
		aria-label={mapState.browseSheetExpanded ? 'Collapse panel' : 'Expand panel'}
	>
		<span class="grip" aria-hidden="true"></span>
	</button>

	{#if mapState.browseSheetExpanded}
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
						<PointJobList stack={mapState.jobStack} />
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
						<SmallestAreaCard onViewList={() => setPage('list')} />
					{/if}
				</div>
				<div class="panel">
					<JobList richMode />
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
	.grabber {
		appearance: none;
		flex-shrink: 0;
		width: 100%;
		background: transparent;
		border: none;
		padding: 0.5rem 0 0.3rem;
		cursor: pointer;
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
