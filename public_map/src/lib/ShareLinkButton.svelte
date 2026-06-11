<!--
	D.5.29 / ADR-0033 — "Copy share link" button.

	Snapshots the current view (filters, metric, viewport, theme, selected job,
	list scroll) into a query string, asks /api/share to mint a 7-char short
	link, and copies it to the clipboard. If the Function is unavailable (no KV
	binding, preview deploy, network blip) it copies the full long URL instead
	with a "short link unavailable" note — the clipboard copy must always succeed
	(invariant #28). A transient toast confirms what was copied.
-->
<script lang="ts">
	import { readCurrentView } from './viewSync';
	import { viewToParamString, shareUrlFromView } from './viewState';

	let toast = $state<{ text: string; tone: 'ok' | 'warn' } | null>(null);
	let toastTimer: ReturnType<typeof setTimeout> | null = null;
	let busy = $state(false);

	function flash(text: string, tone: 'ok' | 'warn') {
		toast = { text, tone };
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (toast = null), 2600);
	}

	async function copy(text: string): Promise<boolean> {
		try {
			if (navigator.clipboard?.writeText) {
				await navigator.clipboard.writeText(text);
				return true;
			}
		} catch {
			/* fall through to the legacy path */
		}
		// Legacy fallback for browsers / contexts without the async clipboard.
		try {
			const ta = document.createElement('textarea');
			ta.value = text;
			ta.style.position = 'fixed';
			ta.style.opacity = '0';
			document.body.appendChild(ta);
			ta.select();
			const ok = document.execCommand('copy');
			document.body.removeChild(ta);
			return ok;
		} catch {
			return false;
		}
	}

	async function share() {
		if (busy) return;
		busy = true;
		const view = readCurrentView();
		const params = viewToParamString(view);
		const longUrl = shareUrlFromView(view, { origin: window.location.origin, path: '/browse' });
		try {
			const res = await fetch('/api/share', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ params })
			});
			if (res.ok) {
				const body = (await res.json()) as { url?: string };
				const shortUrl = body.url || longUrl;
				const ok = await copy(shortUrl);
				flash(ok ? 'Share link copied' : shortUrl, ok ? 'ok' : 'warn');
				return;
			}
			throw new Error(`share ${res.status}`);
		} catch {
			// Short-link service unavailable — copy the full URL so sharing works.
			const ok = await copy(longUrl);
			flash(ok ? 'Full link copied (short link unavailable)' : longUrl, 'warn');
		} finally {
			busy = false;
		}
	}
</script>

<div class="share-wrap">
	<button type="button" class="share-btn" onclick={share} disabled={busy} aria-label="Copy a shareable link to this view">
		<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M18 16a3 3 0 0 0-2.4 1.2l-7-3.5a3 3 0 0 0 0-1.4l7-3.5A3 3 0 1 0 15 6c0 .2 0 .5.1.7l-7 3.5a3 3 0 1 0 0 4.6l7 3.5c-.1.2-.1.5-.1.7a3 3 0 1 0 3-3z" /></svg>
		Share
	</button>
	{#if toast}
		<span class="toast" class:warn={toast.tone === 'warn'} role="status">{toast.text}</span>
	{/if}
</div>

<style>
	.share-wrap {
		position: relative;
		display: inline-flex;
		align-items: center;
	}
	.share-btn {
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 999px;
		background: var(--c-row-bg, rgba(8, 13, 22, 0.6));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		padding: 0.3rem 0.65rem;
		cursor: pointer;
		white-space: nowrap;
	}
	.share-btn:hover:not(:disabled) {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-text, #e5edf5);
	}
	.share-btn:disabled {
		opacity: 0.6;
		cursor: progress;
	}
	.share-btn:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.toast {
		position: absolute;
		top: calc(100% + 0.4rem);
		right: 0;
		z-index: 60;
		max-width: 16rem;
		background: var(--c-panel, #0e1726);
		border: 1px solid var(--c-border, #2a3a52);
		border-left: 3px solid var(--c-accent, #7bd0f2);
		border-radius: 6px;
		color: var(--c-text, #e5edf5);
		font-size: 11px;
		line-height: 1.4;
		padding: 0.4rem 0.6rem;
		box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
		word-break: break-all;
	}
	.toast.warn {
		border-left-color: #e0b341;
	}
</style>
