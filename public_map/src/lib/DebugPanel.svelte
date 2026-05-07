<script lang="ts">
	import { mapState } from './store.svelte';

	function close() {
		mapState.debugFeature = null;
	}
</script>

{#if mapState.debugFeature}
	<aside class="panel" aria-live="polite">
		<header>
			<span class="layer">{mapState.debugFeature.source}</span>
			<button type="button" class="close" onclick={close} aria-label="Close">×</button>
		</header>
		<dl>
			{#each Object.entries(mapState.debugFeature.properties) as [key, value] (key)}
				<dt>{key}</dt>
				<dd>{value === null || value === undefined ? '—' : String(value)}</dd>
			{/each}
		</dl>
		<footer>Debug only — Phase C replaces this with the typed popups.</footer>
	</aside>
{/if}

<style>
	.panel {
		position: absolute;
		right: 1rem;
		top: 1rem;
		width: 22rem;
		max-height: calc(100vh - 6rem);
		overflow: auto;
		background: rgba(14, 23, 38, 0.95);
		border: 1px solid #2a3a52;
		border-radius: 8px;
		padding: 0.75rem 0.9rem;
		font-size: 12px;
		color: #cfd9e6;
		z-index: 5;
		box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.4rem;
	}
	.layer {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		color: #7bd0f2;
		text-transform: lowercase;
	}
	.close {
		appearance: none;
		background: transparent;
		border: none;
		color: #94a3b8;
		font-size: 18px;
		line-height: 1;
		cursor: pointer;
		padding: 0;
	}
	.close:hover {
		color: #e5edf5;
	}
	dl {
		margin: 0;
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 4px 12px;
	}
	dt {
		font-weight: 500;
		color: #94a3b8;
	}
	dd {
		margin: 0;
		word-break: break-word;
	}
	footer {
		margin-top: 0.6rem;
		padding-top: 0.5rem;
		border-top: 1px solid #2a3a52;
		font-size: 11px;
		color: #64748b;
	}
</style>
