<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	onMount(() => {
		goto('/browse', { replaceState: true });
	});
</script>

<main class="redirect">
	<p>Loading FedFinder…</p>
	<p><a href="/browse">Continue to Browse</a></p>
</main>

<style>
	.redirect {
		display: grid;
		place-items: center;
		min-height: 100vh;
		gap: 0.5rem;
		text-align: center;
	}
</style>
