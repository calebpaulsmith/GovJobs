<!--
	Browse map bottom sheet (mobile / narrow viewports). Sits over the bottom
	of the full-screen map. Browse is the find-jobs surface (ADR-0039), so the
	sheet holds one thing — the Postings list (BrowsePostingsPanel) — plus a
	job-detail view (BrowseJobPanel) layered over it when a job is picked
	(map marker, same-point stack, or list row), with "‹ Back to postings".
	Area metrics that used to live on a "Here" page are on /analysis now; a
	tapped polygon narrows the list and offers "Analyze this area →".

	On desktop (≥ 1024 px) /browse renders the panels in the mosaic grid
	instead of mounting this sheet — the sheet owns only the mobile chrome
	(grabber, detents, peek bar, detail/back).
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import { browser } from '$app/environment';
	import { mapState } from './store.svelte';
	import { LAYER_IDS } from './layers';
	import BrowseJobPanel from './BrowseJobPanel.svelte';
	import BrowsePostingsPanel from './BrowsePostingsPanel.svelte';

	// Auto-expand the sheet when something new is tapped on the map (a job,
	// a stack, or a polygon that narrows the list). Tracks selection identity
	// so collapsing while something stays selected doesn't re-open it.
	let lastSelection: unknown = null;
	$effect(() => {
		const sel = mapState.selectedFeature ?? mapState.jobStack;
		if (sel && sel !== lastSelection) {
			// untrack the write back to mapState so this effect doesn't
			// subscribe to what it mutates — WebKit's Svelte 5 scheduler
			// treats read-then-write of the same proxy as a
			// `state_unsafe_mutation` and freezes the effect tree (the
			// "frozen Here screen" bug, CLAUDE.md).
			untrack(() => {
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

	// A picked job (or same-point stack) shows as a detail view over the
	// list. Polygon selections don't — they narrow the list instead.
	const showDetail = $derived(
		(!!mapState.jobStack && !mapState.selectedFeature) ||
			(!!mapState.selectedFeature &&
				(mapState.selectedFeature.source === LAYER_IDS.markers ||
					(mapState.selectedFeature.source === 'share' && mapState.selectedFeature.label === 'Job card')))
	);
	function backToList() {
		mapState.selectedFeature = null;
		mapState.jobStack = null;
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
	// Mirrors `grabbing` for the template: highlights the grip while held.
	let grabActive = $state(false);

	// Collapsed detent height in px: 44px grabber + 40px peek bar. Must match
	// `.sheet { height }` below.
	const COLLAPSED_PX = 84;

	function detents() {
		// The sheet is position:absolute, so its CSS `%` heights resolve
		// against its offsetParent — not the window. Measure that same box so
		// the drag math lines up exactly with the resting CSS detents (50% /
		// 92%). Falling back to the window only matters before first layout.
		const parentH =
			sheetEl?.offsetParent?.getBoundingClientRect().height ??
			(browser ? window.innerHeight : 800);
		return { collapsed: COLLAPSED_PX, half: parentH * 0.5, full: parentH * 0.92 };
	}

	function onGrabPointerDown(e: PointerEvent) {
		grabbing = true;
		grabActive = true;
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
		grabActive = false;
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
		grabActive = false;
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
	// reveals content immediately instead of an empty growing box). The peek
	// bar stays mounted until the sheet is actually expanded — a drag can
	// start on it, and unmounting the pointer target mid-drag would drop the
	// gesture (no pointerup → sheet stuck at the drag height).
	const showContent = $derived(mapState.browseSheetExpanded || dragH !== null);

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
	aria-label="Postings"
>
	<button
		type="button"
		class="grabber"
		class:held={grabActive}
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

	{#if !mapState.browseSheetExpanded}
		<!-- The peek bar is a second, bigger drag handle: same pointer handlers
		     as the grabber (tap toggles in pointerup, so no onclick — see
		     onGrabPointerUp for the WebKit synthetic-click reason). -->
		<button
			type="button"
			class="peek"
			onpointerdown={onGrabPointerDown}
			onpointermove={onGrabPointerMove}
			onpointerup={onGrabPointerUp}
			onpointercancel={onGrabPointerCancel}
			onkeydown={onGrabKey}
		>
			<span class="peek-label">{peekLabel}</span>
			<span class="peek-hint">tap or drag up ▴</span>
		</button>
	{/if}

	{#if showContent}
		{#if showDetail}
			<div class="detail-head">
				<button type="button" class="back" onclick={backToList}>‹ Back to postings</button>
			</div>
			<div class="panel">
				<BrowseJobPanel />
			</div>
		{:else}
			<div class="panel postings-host">
				<BrowsePostingsPanel />
			</div>
		{/if}
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
		/* Collapsed detent: the 44px grabber plus the peek bar. Keep in sync
		   with COLLAPSED_PX in the script. px, not rem: the root font size is
		   not 16px, so rem here drifted from the drag math. */
		height: 84px;
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
		/* 44px: Apple's minimum comfortable thumb target. The old ~17px strip
		   was hard to catch; the grip stays small visually but the whole band
		   is grabbable. */
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: transparent;
		border: none;
		padding: 0;
		cursor: grab;
		/* Own vertical gestures so dragging the grabber resizes the sheet
		   instead of scrolling the page/panel underneath. */
		touch-action: none;
	}
	.grabber:active,
	.grabber.held {
		cursor: grabbing;
	}
	.grip {
		display: block;
		width: 3rem;
		height: 6px;
		border-radius: 999px;
		/* Muted text colour (not the border colour) so the handle reads
		   clearly against the panel in both themes. */
		background: var(--c-muted, #8aa0b8);
		transition: width 150ms ease, background 150ms ease;
	}
	.grabber.held .grip,
	.grabber:focus-visible .grip {
		width: 4rem;
		background: var(--c-accent, #7bd0f2);
	}
	.detail-head {
		flex-shrink: 0;
		padding: 0 0.75rem 0.3rem;
	}
	.back {
		appearance: none;
		min-height: 2.25rem;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.3rem 0.8rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.back:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.panel {
		flex: 1;
		min-height: 0;
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
		/* Fixed height (84px collapsed − 44px grabber) so it keeps its place
		   above the revealed panels during a drag from collapsed. */
		flex: 0 0 40px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		width: 100%;
		background: transparent;
		border: none;
		padding: 0 0.95rem 0.5rem;
		cursor: grab;
		/* Drags on the peek bar resize the sheet, like the grabber. */
		touch-action: none;
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
