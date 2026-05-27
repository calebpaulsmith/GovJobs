<!--
	Saved drawer for the Browse map. A right slide-in drawer wrapping the existing
	SavedTab (saved Job Lists + saved/hidden/viewed-closed postings), relocated
	from the old dock tab to a masthead button per the map-as-home redesign.
	Controlled by mapState.savedDrawerOpen. "Show jobs" inside SavedTab routes to
	the bottom sheet's Postings page and closes the drawer.
-->
<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { mapState } from './store.svelte';
	import SavedTab from './SavedTab.svelte';

	function close() {
		mapState.savedDrawerOpen = false;
	}

	function viewList() {
		mapState.savedDrawerOpen = false;
		mapState.browseSheetPage = 'list';
		mapState.browseSheetExpanded = true;
	}
</script>

{#if mapState.savedDrawerOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="overlay" onclick={close} transition:fade={{ duration: 150 }}></div>
	<aside class="drawer" aria-label="Saved" transition:fly={{ x: 340, duration: 200 }}>
		<div class="header">
			<h2>Saved</h2>
			<button type="button" class="close" onclick={close} aria-label="Close saved">✕</button>
		</div>
		<div class="body">
			<SavedTab onViewList={viewList} />
		</div>
	</aside>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 29;
		background: rgba(0, 0, 0, 0.4);
	}
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(380px, 94vw);
		z-index: 30;
		background: var(--c-panel, #0e1726);
		border-left: 1px solid var(--c-border, #2a3a52);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1rem 0.6rem;
		border-bottom: 1px solid var(--c-border, #2a3a52);
		flex-shrink: 0;
	}
	h2 {
		margin: 0;
		font-size: 16px;
		font-weight: 600;
		color: var(--c-text, #e5edf5);
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
	}
	.close:hover {
		color: var(--c-text, #e5edf5);
		background: rgba(255, 255, 255, 0.07);
	}
	.body {
		flex: 1;
		overflow-y: auto;
		-webkit-overflow-scrolling: touch;
		padding: 0.5rem 0.6rem calc(0.5rem + env(safe-area-inset-bottom, 0px));
	}
</style>
