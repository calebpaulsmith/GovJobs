<!--
	On-screen error console for mobile debugging. Inert by default — it only
	installs listeners when the URL has ?debug (e.g. /browse?debug=1), so normal
	visitors never see it. When enabled, uncaught errors, unhandled promise
	rejections, console.error calls, and tap targets are captured. The overlay
	renders a slim bar at the top and is pointer-events: none everywhere except
	that bar, so it never blocks the underlying app's controls. Temporary
	diagnostic — remove once the Browse-map freeze is fixed.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	let enabled = $state(false);
	let errs = $state<string[]>([]);
	let taps = $state<string[]>([]);
	let open = $state(false);
	let dbgEl = $state<HTMLDivElement | null>(null);

	function pushErr(msg: string) {
		const m = msg.slice(0, 800);
		if (errs[errs.length - 1] === m) return;
		errs = [...errs.slice(-19), m];
	}
	function pushTap(msg: string) {
		const m = msg.slice(0, 200);
		if (taps[taps.length - 1] === m) return;
		taps = [...taps.slice(-19), m];
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
			pushErr(`ERROR: ${e.message}  (${(e.filename || '').split('/').pop()}:${e.lineno}:${e.colno})`);
		const onRej = (e: PromiseRejectionEvent) => {
			const r = e.reason;
			pushErr(`PROMISE: ${r instanceof Error ? `${r.message}\n${r.stack ?? ''}` : String(r)}`);
		};
		window.addEventListener('error', onError);
		window.addEventListener('unhandledrejection', onRej);

		const onTap = (e: Event) => {
			const t = e.target as Element | null;
			if (!t) return;
			// Ignore taps on the overlay's own UI so the log doesn't fill with
			// noise from interacting with Copy / Clear / Show.
			if (dbgEl && dbgEl.contains(t)) return;
			const tag = t.tagName ? t.tagName.toLowerCase() : '?';
			const clsAttr = t.getAttribute ? t.getAttribute('class') : '';
			const cls = clsAttr ? '.' + clsAttr.trim().split(/\s+/).slice(0, 2).join('.') : '';
			pushTap(`tap → ${tag}${cls}`);
		};
		document.addEventListener('pointerdown', onTap, true);

		const orig = console.error.bind(console);
		console.error = (...args: unknown[]) => {
			try {
				pushErr(
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

	function copyAll() {
		if (browser && navigator.clipboard) {
			const body = [
				errs.length ? 'ERRORS:\n' + errs.join('\n\n') : '',
				taps.length ? 'TAPS:\n' + taps.join('\n') : ''
			]
				.filter(Boolean)
				.join('\n\n');
			void navigator.clipboard.writeText(body);
		}
	}

	function clearAll() {
		errs = [];
		taps = [];
	}
</script>

{#if enabled}
	<div class="dbg" bind:this={dbgEl}>
		<div class="bar">
			<strong class:err={errs.length > 0}>
				{errs.length === 0 ? '✓' : '⚠'}
				{errs.length} err · {taps.length} tap{taps.length === 1 ? '' : 's'}
			</strong>
			<span class="spacer"></span>
			<button type="button" onclick={copyAll}>Copy</button>
			<button type="button" onclick={clearAll}>Clear</button>
			<button type="button" onclick={() => (open = !open)}>{open ? 'Hide' : 'Show'}</button>
		</div>
		{#if open}
			<div class="log">
				{#if errs.length}
					<h4>Errors ({errs.length})</h4>
					{#each errs as e, i (i)}<pre>{e}</pre>{/each}
				{/if}
				{#if taps.length}
					<h4>Taps ({taps.length})</h4>
					{#each taps as t, i (i)}<pre class="tap">{t}</pre>{/each}
				{/if}
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
		/* Container does not capture taps; only the bar and (optional) log do.
		   Keeps the overlay from blocking the underlying app's controls. */
		pointer-events: none;
		font: 11px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
	}
	.bar {
		pointer-events: auto;
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.6rem;
		background: #2a0d0d;
		color: #ffd9d9;
		border-bottom: 2px solid #f7a0a0;
	}
	.bar strong {
		color: #cfd6df;
	}
	.bar strong.err {
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
		pointer-events: auto;
		max-height: 45vh;
		overflow: auto;
		padding: 0 0.6rem 0.5rem;
		background: #2a0d0d;
		color: #ffd9d9;
		border-bottom: 2px solid #f7a0a0;
	}
	.log h4 {
		margin: 0.4rem 0 0.2rem;
		font-size: 11px;
		color: #f7a0a0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	pre {
		white-space: pre-wrap;
		word-break: break-word;
		margin: 0 0 0.3rem;
		padding: 0.3rem 0.4rem;
		background: rgba(0, 0, 0, 0.3);
		border-radius: 4px;
	}
	pre.tap {
		opacity: 0.85;
	}
</style>
