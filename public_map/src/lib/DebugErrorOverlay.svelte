<!--
	On-screen error console for mobile debugging. Inert by default — it only
	installs listeners when the URL has ?debug (e.g. /browse?debug=1), so normal
	visitors never see it. When enabled, uncaught errors, unhandled promise
	rejections, and console.error calls surface as a red bar at the top of the
	screen with a Copy button. Built into the bundle so no CSP / bookmarklet can
	block it. Temporary diagnostic — remove once the Browse-map freeze is fixed.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	let enabled = $state(false);
	let errors = $state<string[]>([]);
	let open = $state(true);

	function add(msg: string) {
		const m = msg.slice(0, 800);
		if (errors[errors.length - 1] === m) return;
		errors = [...errors.slice(-19), m];
		open = true;
	}

	function safeStr(v: unknown): string {
		try {
			return JSON.stringify(v);
		} catch {
			return String(v);
		}
	}

	onMount(() => {
		if (!browser) return;
		if (!new URLSearchParams(location.search).has('debug')) return;
		enabled = true;

		const onError = (e: ErrorEvent) =>
			add(`ERROR: ${e.message}  (${(e.filename || '').split('/').pop()}:${e.lineno}:${e.colno})`);
		const onRej = (e: PromiseRejectionEvent) => {
			const r = e.reason;
			add(`PROMISE: ${r instanceof Error ? `${r.message}\n${r.stack ?? ''}` : String(r)}`);
		};
		window.addEventListener('error', onError);
		window.addEventListener('unhandledrejection', onRej);

		// Tap target logging — reveals which element actually receives a tap, so
		// we can tell whether a control receives the event or something else
		// (e.g. the map canvas) is intercepting it.
		const onTap = (e: Event) => {
			const t = e.target as Element | null;
			if (!t) return;
			const tag = t.tagName ? t.tagName.toLowerCase() : '?';
			const clsAttr = t.getAttribute ? t.getAttribute('class') : '';
			const cls = clsAttr ? '.' + clsAttr.trim().split(/\s+/).slice(0, 2).join('.') : '';
			add(`tap → ${tag}${cls}`);
		};
		document.addEventListener('pointerdown', onTap, true);

		const orig = console.error.bind(console);
		console.error = (...args: unknown[]) => {
			try {
				add(
					'console.error: ' +
						args
							.map((a) =>
								a instanceof Error
									? `${a.message}\n${a.stack ?? ''}`
									: typeof a === 'string'
										? a
										: safeStr(a)
							)
							.join(' ')
				);
			} catch {
				/* never let the logger throw */
			}
			orig(...args);
		};

		return () => {
			window.removeEventListener('error', onError);
			window.removeEventListener('unhandledrejection', onRej);
			document.removeEventListener('pointerdown', onTap, true);
			console.error = orig;
		};
	});

	function copy() {
		if (browser && navigator.clipboard) void navigator.clipboard.writeText(errors.join('\n\n'));
	}
</script>

{#if enabled && errors.length > 0}
	<div class="dbg">
		<div class="bar">
			<strong>⚠ {errors.length} error{errors.length > 1 ? 's' : ''}</strong>
			<span class="spacer"></span>
			<button type="button" onclick={copy}>Copy</button>
			<button type="button" onclick={() => (errors = [])}>Clear</button>
			<button type="button" onclick={() => (open = !open)}>{open ? 'Hide' : 'Show'}</button>
		</div>
		{#if open}
			<div class="log">
				{#each errors as e, i (i)}<pre>{e}</pre>{/each}
			</div>
		{/if}
	</div>
{/if}

<style>
	.dbg {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: 99999;
		background: #2a0d0d;
		color: #ffd9d9;
		border-bottom: 2px solid #f7a0a0;
		font: 11px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.6rem;
	}
	.bar strong {
		color: #ff8a8a;
	}
	.spacer {
		flex: 1;
	}
	.bar button {
		appearance: none;
		border: 1px solid #f7a0a0;
		background: transparent;
		color: #ffd9d9;
		border-radius: 4px;
		padding: 0.15rem 0.45rem;
		font: inherit;
		cursor: pointer;
	}
	.log {
		max-height: 45vh;
		overflow: auto;
		padding: 0 0.6rem 0.5rem;
	}
	pre {
		white-space: pre-wrap;
		word-break: break-word;
		margin: 0 0 0.5rem;
		padding: 0.4rem;
		background: rgba(0, 0, 0, 0.3);
		border-radius: 4px;
	}
</style>
