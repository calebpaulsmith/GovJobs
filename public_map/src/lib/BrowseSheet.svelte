<!--
	Browse map bottom sheet (mobile / narrow viewports). Sits over the bottom
	of the full-screen map and holds two swipeable pages:
	  • "Here"     — BrowseHerePanel: the tapped area's card (State / Locality /
	                 County), a job card for a tapped marker, or the smallest
	                 enclosing area for the viewport when nothing is selected.
	  • "Postings" — BrowsePostingsPanel: the shared JobList, i.e. the working
	                 list the filters produce and that can be saved.

	On desktop (≥ 1024 px) /browse renders the same two panels side-by-side in
	the mosaic grid instead of mounting this sheet — the sheet owns only the
	mobile chrome (grabber, detents, swipe pager, peek bar).

	Pages switch by horizontal swipe (page dots show which page + that you can
	swipe) or by tapping the pill labels. The last page is remembered in
	localStorage, defaulting to Postings. Tapping any feature on the map auto-
	opens the sheet to the Here page.

	Swipe vs. scroll: the pager sets `touch-action: pan-y`, so the browser keeps
	handling vertical scroll of the active panel natively while horizontal drags
	are delivered to our handlers — no preventDefault, no scroll hijacking.
-->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from './store.svelte';
	import BrowseHerePanel from './BrowseHerePanel.svelte';
	import BrowsePostingsPanel from './BrowsePostingsPanel.svelte';

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
					<BrowseHerePanel
						onViewList={() => setPage('list')}
						onExploreMap={() => {
							mapState.browseSheetExpanded = false;
							mapState.browseSheetFull = false;
						}}
					/>
				</div>
				<div class="panel postings-host">
					<BrowsePostingsPanel />
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
	.panel.postings-host {
		/* BrowsePostingsPanel owns its own scroll container (shared with the
		   desktop mosaic), so the sheet panel just hosts it edge-to-edge. */
		padding: 0;
		overflow: hidden;
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
</style>
