<script lang="ts">
	let { children } = $props();
</script>

{@render children()}

<style>
	/* ── Theme tokens (dark default, light override) ─────────────────── */
	:global(:root),
	:global([data-theme='dark']) {
		--c-bg: #06111f;
		--c-panel: rgba(14, 23, 38, 0.96);
		--c-panel-blur: rgba(14, 23, 38, 0.85);
		--c-row-bg: rgba(20, 32, 50, 0.55);
		--c-row-hover: rgba(28, 42, 64, 0.85);
		--c-border: #2a3a52;
		--c-border-subtle: #22344c;
		--c-border-input: #2c4870;
		--c-text: #e5edf5;
		--c-text-2: #cfd9e6;
		--c-muted: #94a3b8;
		--c-faint: #64748b;
		--c-accent: #7bd0f2;
		--c-accent-dim: #4979b3;
		--c-accent-bg: rgba(123, 208, 242, 0.08);
		--c-accent-bg-strong: rgba(123, 208, 242, 0.18);
		--c-danger: #f7a0a0;
		--c-danger-border: #6b2020;
		--c-warn: #f0c878;
		--c-warn-border: #e0a030;
		--c-apply-bg: #7bd0f2;
		--c-apply-text: #06111f;
		--c-apply-hover: #a8e0f5;
	}
	:global([data-theme='light']) {
		--c-bg: #e8ecf1;
		--c-panel: rgba(248, 250, 252, 0.97);
		--c-panel-blur: rgba(240, 244, 248, 0.93);
		--c-row-bg: rgba(241, 245, 249, 0.9);
		--c-row-hover: rgba(226, 232, 240, 0.95);
		--c-border: #cbd5e1;
		--c-border-subtle: #e2e8f0;
		--c-border-input: #94a3b8;
		--c-text: #1e293b;
		--c-text-2: #334155;
		--c-muted: #64748b;
		--c-faint: #94a3b8;
		--c-accent: #1760a8;
		--c-accent-dim: #2563eb;
		--c-accent-bg: rgba(23, 96, 168, 0.08);
		--c-accent-bg-strong: rgba(23, 96, 168, 0.15);
		--c-danger: #b91c1c;
		--c-danger-border: #fca5a5;
		--c-warn: #92400e;
		--c-warn-border: #fcd34d;
		--c-apply-bg: #1760a8;
		--c-apply-text: #fff;
		--c-apply-hover: #1d4ed8;
	}

	:global(html, body) {
		margin: 0;
		padding: 0;
		height: 100%;
		background: var(--c-bg, #0a0f1a);
		color: var(--c-text, #e5edf5);
		font-family:
			-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial,
			sans-serif;
		font-size: 14px;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}
	:global(*, *::before, *::after) {
		box-sizing: border-box;
	}
	:global(a) {
		color: var(--c-accent, #7bd0f2);
	}
</style>
