<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	onMount(() => {
		goto('/map', { replaceState: true });
	});
</script>

<main class="redirect">
	<p>Loading the map…</p>
	<p><a href="/map">Continue to the map</a></p>
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
