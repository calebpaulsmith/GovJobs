<!--
	Lightweight info-tooltip used to show how a calculated value was derived.
	Hover or focus the (i) icon to reveal a small popover with the formula,
	the actual inputs, and the data source. Click toggles the popover so it
	also works on touch devices.

	Slot pattern (preferred when content is rich) OR pass `title` / `body`
	props for a quick text-only tooltip.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title?: string;
		body?: string;
		children?: Snippet;
		// 'top' | 'bottom' | 'auto' — auto picks based on viewport room.
		placement?: 'top' | 'bottom';
		// Adjust where the popover anchors horizontally — useful for icons
		// that appear at the right edge of a parent.
		align?: 'start' | 'end';
	}

	let {
		title,
		body,
		children,
		placement = 'top',
		align = 'start'
	}: Props = $props();

	let open = $state(false);

	function show() {
		open = true;
	}
	function hide() {
		open = false;
	}
	function toggle(e: Event) {
		e.preventDefault();
		e.stopPropagation();
		open = !open;
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') open = false;
	}
</script>

<span
	class="wrap"
	onmouseenter={show}
	onmouseleave={hide}
	onfocusin={show}
	onfocusout={hide}
	onkeydown={onKey}
	role="presentation"
>
	<button
		type="button"
		class="icon"
		aria-expanded={open}
		aria-label={title ?? 'How this value is calculated'}
		onclick={toggle}
	>
		ⓘ
	</button>
	{#if open}
		<span class="popover" class:bottom={placement === 'bottom'} class:end={align === 'end'} role="tooltip">
			{#if title}
				<strong>{title}</strong>
			{/if}
			{#if children}
				{@render children()}
			{:else if body}
				<span>{body}</span>
			{/if}
		</span>
	{/if}
</span>

<style>
	.wrap {
		position: relative;
		display: inline-flex;
		align-items: center;
		margin-left: 0.3rem;
		vertical-align: middle;
	}
	.icon {
		appearance: none;
		border: 1px solid #2c4870;
		background: rgba(28, 42, 64, 0.4);
		color: #94a3b8;
		font-size: 11px;
		line-height: 1;
		width: 16px;
		height: 16px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		cursor: help;
		padding: 0;
	}
	.icon:hover,
	.icon:focus-visible {
		border-color: #7bd0f2;
		color: #7bd0f2;
		outline: none;
	}
	.popover {
		position: absolute;
		z-index: 8;
		bottom: calc(100% + 6px);
		left: 0;
		min-width: 14rem;
		max-width: 22rem;
		padding: 0.55rem 0.7rem;
		background: rgba(8, 14, 26, 0.98);
		border: 1px solid #2a3a52;
		border-radius: 6px;
		font-size: 11px;
		line-height: 1.45;
		color: #e5edf5;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
		text-align: left;
		font-weight: 400;
		white-space: normal;
		pointer-events: auto;
	}
	.popover.bottom {
		bottom: auto;
		top: calc(100% + 6px);
	}
	.popover.end {
		left: auto;
		right: 0;
	}
	.popover strong {
		display: block;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #7bd0f2;
		margin-bottom: 0.25rem;
		font-weight: 600;
	}
	.popover :global(code) {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 10.5px;
		background: rgba(255, 255, 255, 0.06);
		padding: 0 4px;
		border-radius: 2px;
	}
	.popover :global(.formula) {
		display: block;
		margin-top: 0.25rem;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 10.5px;
		color: #cfd9e6;
		background: rgba(255, 255, 255, 0.04);
		padding: 0.3rem 0.4rem;
		border-radius: 4px;
		border-left: 2px solid #4979b3;
	}
	.popover :global(.src) {
		display: block;
		margin-top: 0.4rem;
		color: #94a3b8;
		font-size: 10px;
	}
</style>
