<!--
	Mobile filter sheet for the Browse map. A left slide-in drawer that wraps the
	shared FilterFields component, so it presents the exact same inputs as the
	/map FilterPanel and writes the one mapState.filters store. Opened via the
	left-edge "Filters" button on the Browse map; closed by the overlay, the ×,
	or the "Done" button. Controlled by mapState.filterSheetOpen.
-->
<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { mapState } from './store.svelte';
	import { activeFilterCount } from './filters';
	import FilterFields from './FilterFields.svelte';

	function close() {
		mapState.filterSheetOpen = false;
	}
</script>

{#if mapState.filterSheetOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="overlay" onclick={close} transition:fade={{ duration: 150 }}></div>
	<aside class="sheet" aria-label="Filters" transition:fly={{ x: -340, duration: 200 }}>
		<div class="header">
			<h2>
				Filters
				{#if activeFilterCount(mapState.filters) > 0}
					<span class="count">{activeFilterCount(mapState.filters)}</span>
				{/if}
			</h2>
			<button type="button" class="close" onclick={close} aria-label="Close filters">✕</button>
		</div>
		<div class="body">
			<FilterFields />
		</div>
		<div class="foot">
			<button type="button" class="done" onclick={close}>Done</button>
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
	.sheet {
		position: fixed;
		top: 0;
		left: 0;
		bottom: 0;
		width: min(340px, 92vw);
		z-index: 30;
		background: var(--c-panel, #0e1726);
		border-right: 1px solid var(--c-border, #2a3a52);
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
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.count {
		background: var(--c-accent-dim, #4979b3);
		color: #fff;
		font-size: 11px;
		padding: 0.05rem 0.45rem;
		border-radius: 999px;
		font-weight: 700;
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
		padding: 0.85rem;
		color: var(--c-text-2, #cfd9e6);
		font-size: 12px;
	}
	.foot {
		flex-shrink: 0;
		padding: 0.6rem 0.85rem calc(0.6rem + env(safe-area-inset-bottom, 0px));
		border-top: 1px solid var(--c-border, #2a3a52);
	}
	.done {
		appearance: none;
		width: 100%;
		border: none;
		border-radius: 8px;
		background: var(--c-apply-bg, #7bd0f2);
		color: var(--c-apply-text, #06111f);
		font: inherit;
		font-weight: 600;
		padding: 0.6rem;
		cursor: pointer;
	}
	.done:hover {
		background: var(--c-apply-hover, #a8e0f5);
	}
	.done:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
</style>
