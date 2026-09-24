<!--
	BrowseWelcome — first-run welcome card (D.6.4 / ADR-0035), shown at the
	top of the Browse Postings list until dismissed. Moved here from the
	retired Here panel (ADR-0039). Dismissal persists under
	`fedfinder.public_map.browse_welcome.v1`.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import AddressSearch from './AddressSearch.svelte';

	const WELCOME_KEY = 'fedfinder.public_map.browse_welcome.v1';

	// Defaults to dismissed so it never flashes before onMount reads the flag.
	let dismissed = $state(true);

	onMount(() => {
		if (!browser) return;
		dismissed = localStorage.getItem(WELCOME_KEY) === '1';
	});

	function dismiss() {
		dismissed = true;
		if (browser) localStorage.setItem(WELCOME_KEY, '1');
	}
</script>

{#if !dismissed}
	<div class="welcome" role="region" aria-label="Getting started">
		<div class="welcome-head">
			<h2>Find your federal job</h2>
			<button type="button" class="welcome-close" onclick={dismiss} aria-label="Dismiss welcome">✕</button>
		</div>
		<p class="welcome-sub">
			Jump to where you'd work, or scroll the postings below. For trends and pay vs. cost of living, open
			<a href="/analysis">Analysis</a>.
		</p>
		<AddressSearch docked onChoose={dismiss} />
	</div>
{/if}

<style>
	.welcome {
		margin: 0.6rem 0.75rem 0.2rem;
		padding: 0.7rem 0.75rem 0.8rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 10px;
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.1));
	}
	.welcome-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.welcome-head h2 {
		margin: 0;
		font-size: 16px;
		color: var(--c-text, #e5edf5);
	}
	.welcome-close {
		appearance: none;
		border: none;
		background: none;
		color: var(--c-muted, #94a3b8);
		font-size: 14px;
		cursor: pointer;
		padding: 0.15rem 0.35rem;
		border-radius: 4px;
	}
	.welcome-close:hover {
		color: var(--c-text, #e5edf5);
		background: rgba(255, 255, 255, 0.07);
	}
	.welcome-sub {
		margin: 0.25rem 0 0.6rem;
		font-size: 12px;
		color: var(--c-text-2, #cfd9e6);
		line-height: 1.45;
	}
	.welcome-sub a {
		color: var(--c-accent, #7bd0f2);
	}
</style>
