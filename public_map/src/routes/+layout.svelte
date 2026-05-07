<script lang="ts">
	let { children } = $props();
</script>

{@render children()}

<style>
	:global(html, body) {
		margin: 0;
		padding: 0;
		height: 100%;
		background: #0a0f1a;
		color: #e5edf5;
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
		color: #7bd0f2;
	}
</style>
