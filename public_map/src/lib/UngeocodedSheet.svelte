<!--
	Ungeocoded postings sheet.

	A swipe-away bottom sheet that lists the open USAJOBS postings the map could
	not place — postings present in jobs_detail.json but with no marker in
	jobs.geojson because no duty station geocoded (usually overseas or
	non-standard location strings). Without this, those jobs are invisible on the
	public site; here they stay reachable (each row links straight to USAJOBS and
	can be saved/hidden).

	Opened from the "N postings have no map location" button at the bottom of the
	filter fields (mapState.ungeocodedOpen). Dismissed by swiping the sheet down,
	tapping the dimmed backdrop, the ✕, or Escape.

	Reuses JobList in rich mode with `ungeocodedOnly` so the row rendering, sort,
	in-list search, facets, and Save/Hide actions are the same as the Browse list
	— no second list implementation (CLAUDE.md invariant #29).
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import { mapState } from './store.svelte';
	import { ungeocodedJobIds } from './geo';
	import JobList from './JobList.svelte';

	// Live count for the header. Derived from the same two bundle sources the
	// list itself uses, so the number and the rows can never disagree.
	const count = $derived(ungeocodedJobIds(mapState.allJobDetails, mapState.allJobs).length);

	let sheetEl = $state<HTMLElement | null>(null);

	// --- swipe-to-dismiss gesture (drag the grabber/header down) -------------
	// dragY is the live downward offset in px while a drag is in flight; null
	// when idle. We never write to mapState during the drag — only on release —
	// so there's no $effect read/write loop to worry about (CLAUDE.md WebKit
	// state_unsafe_mutation rule).
	let dragY = $state<number | null>(null);
	let startY = 0;
	let lastY = 0;
	let lastT = 0;
	let velocity = 0; // px/ms, positive = downward
	let grabMoved = false;
	const DISMISS_PX = 110; // drag this far down → dismiss
	const FLICK_V = 0.5; // …or flick faster than this (px/ms) downward

	function close() {
		mapState.ungeocodedOpen = false;
	}

	function onGrabPointerDown(e: PointerEvent) {
		startY = e.clientY;
		lastY = e.clientY;
		lastT = e.timeStamp;
		velocity = 0;
		grabMoved = false;
		dragY = 0;
		(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
	}

	function onGrabPointerMove(e: PointerEvent) {
		if (dragY === null) return;
		const dy = e.clientY - startY;
		if (Math.abs(dy) > 4) grabMoved = true;
		// Only track downward drag; a slight upward pull just snaps to 0.
		dragY = Math.max(0, dy);
		const dt = e.timeStamp - lastT;
		if (dt > 0) velocity = (e.clientY - lastY) / dt;
		lastY = e.clientY;
		lastT = e.timeStamp;
	}

	function onGrabPointerUp() {
		if (dragY === null) return;
		const shouldDismiss = dragY > DISMISS_PX || velocity > FLICK_V;
		dragY = null;
		if (shouldDismiss) close();
	}

	function onGrabPointerCancel() {
		dragY = null;
	}

	// Keyboard affordance on the grabber (drag is pointer-only). Enter/Space and
	// Escape all dismiss; a sheet with no other grabber action keeps this simple.
	function onGrabKey(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
			e.preventDefault();
			close();
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
	}

	// Translate while dragging; spring back to 0 with a transition when idle.
	const transform = $derived(dragY !== null ? `translateY(${dragY}px)` : 'translateY(0)');
</script>

<svelte:window onkeydown={onKeydown} />

{#if mapState.ungeocodedOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="overlay" onclick={close} transition:fade={{ duration: 150 }}></div>
	<aside
		class="sheet"
		class:dragging={dragY !== null}
		style="transform: {transform}"
		bind:this={sheetEl}
		aria-label="Postings not on the map"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="grab"
			role="button"
			tabindex="0"
			aria-label="Swipe down to dismiss"
			onpointerdown={onGrabPointerDown}
			onpointermove={onGrabPointerMove}
			onpointerup={onGrabPointerUp}
			onpointercancel={onGrabPointerCancel}
			onkeydown={onGrabKey}
		>
			<span class="grab-bar" aria-hidden="true"></span>
		</div>
		<div class="head">
			<div class="title-wrap">
				<h2>Not on the map</h2>
				<p class="sub">
					{count.toLocaleString()} open posting{count === 1 ? '' : 's'} couldn't be placed — usually
					overseas or non-standard locations. They're still open; tap a title to apply.
				</p>
			</div>
			<button type="button" class="close" onclick={close} aria-label="Close">✕</button>
		</div>
		<div class="body">
			{#if count === 0}
				<p class="empty">Every open posting has a map location right now. Nothing to show here.</p>
			{:else}
				<JobList richMode ungeocodedOnly />
			{/if}
		</div>
	</aside>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 45;
		background: rgba(0, 0, 0, 0.45);
	}
	.sheet {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 46;
		height: min(82vh, 720px);
		display: flex;
		flex-direction: column;
		background: var(--c-panel, #0e1726);
		border-top: 1px solid var(--c-border, #2a3a52);
		border-top-left-radius: 16px;
		border-top-right-radius: 16px;
		box-shadow: 0 -8px 30px rgba(0, 0, 0, 0.4);
		overflow: hidden;
		touch-action: none;
		will-change: transform;
	}
	/* Snap back smoothly when a drag is released without dismissing; no
	   transition while the finger is down so the sheet tracks 1:1. */
	.sheet:not(.dragging) {
		transition: transform 200ms cubic-bezier(0.22, 0.61, 0.36, 1);
	}
	.grab {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.55rem 0 0.4rem;
		cursor: grab;
		touch-action: none;
	}
	.grab:active {
		cursor: grabbing;
	}
	.grab-bar {
		width: 38px;
		height: 4px;
		border-radius: 999px;
		background: var(--c-muted, #94a3b8);
		opacity: 0.6;
	}
	.head {
		flex-shrink: 0;
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.1rem 1rem 0.7rem;
		border-bottom: 1px solid var(--c-border, #2a3a52);
	}
	h2 {
		margin: 0;
		font-size: 15px;
		font-weight: 600;
		color: var(--c-text, #e5edf5);
	}
	.sub {
		margin: 0.25rem 0 0;
		font-size: 11px;
		line-height: 1.45;
		color: var(--c-muted, #94a3b8);
	}
	.close {
		appearance: none;
		border: none;
		background: none;
		color: var(--c-muted, #94a3b8);
		font-size: 16px;
		cursor: pointer;
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
		flex-shrink: 0;
	}
	.close:hover {
		color: var(--c-text, #e5edf5);
		background: rgba(255, 255, 255, 0.07);
	}
	.body {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		padding: 0.6rem 0.75rem calc(0.6rem + env(safe-area-inset-bottom, 0px));
	}
	.empty {
		margin: 1.2rem 0.4rem;
		font-size: 12px;
		color: var(--c-muted, #94a3b8);
		line-height: 1.5;
	}
</style>
