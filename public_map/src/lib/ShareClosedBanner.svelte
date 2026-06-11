<!--
	D.5.29 / ADR-0033 — closed-shared-job banner.

	When a shared link's `selected=<jobId>` points at a posting that has since
	closed (no longer in the open jobs_detail index), we don't open a dead card —
	we render the rest of the shared view (filters + viewport) and show this
	dismissable banner so the recipient understands why the highlighted job isn't
	there. Never a 404, never a fabricated card. Controlled by
	mapState.shareClosedJobId.
-->
<script lang="ts">
	import { fly } from 'svelte/transition';
	import { mapState } from './store.svelte';

	function dismiss() {
		mapState.shareClosedJobId = null;
	}
</script>

{#if mapState.shareClosedJobId}
	<div class="closed-banner" role="status" transition:fly={{ y: -12, duration: 180 }}>
		<span class="dot" aria-hidden="true">⚑</span>
		<p>
			The highlighted posting has closed. Here's the same filtered view on
			currently open postings.
		</p>
		<button type="button" class="dismiss" onclick={dismiss} aria-label="Dismiss">✕</button>
	</div>
{/if}

<style>
	.closed-banner {
		position: fixed;
		top: 3.2rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 55;
		display: flex;
		align-items: center;
		gap: 0.55rem;
		max-width: min(34rem, 92vw);
		box-sizing: border-box;
		padding: 0.5rem 0.7rem;
		background: var(--c-panel, #0e1726);
		border: 1px solid var(--c-border, #2a3a52);
		border-left: 3px solid #e0b341;
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
		color: var(--c-text, #e5edf5);
	}
	.dot {
		color: #e0b341;
		font-size: 14px;
		flex-shrink: 0;
	}
	p {
		margin: 0;
		font-size: 12px;
		line-height: 1.45;
		color: var(--c-text-2, #cfd9e6);
	}
	.dismiss {
		appearance: none;
		border: none;
		background: none;
		color: var(--c-muted, #94a3b8);
		font-size: 14px;
		cursor: pointer;
		padding: 0.1rem 0.3rem;
		border-radius: 4px;
		flex-shrink: 0;
	}
	.dismiss:hover {
		color: var(--c-text, #e5edf5);
		background: rgba(255, 255, 255, 0.08);
	}
</style>
