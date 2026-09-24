<!--
	/localities was renamed /analysis (ADR-0039). Kept as a redirect so old
	links and bookmarks keep working; the query string is carried over.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	onMount(() => {
		void goto(`/analysis${window.location.search}`, { replaceState: true });
	});
</script>

<svelte:head><title>Analysis · FedFinder</title></svelte:head>
