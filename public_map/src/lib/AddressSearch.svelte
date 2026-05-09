<script lang="ts">
	import { geocodeAddress, type GeocodeResult } from './geocode';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import { mapState } from './store.svelte';

	let query = $state('');
	let results = $state<GeocodeResult[]>([]);
	let loading = $state(false);
	let message = $state('');

	async function search() {
		const trimmed = query.trim();
		if (!trimmed || loading) return;
		loading = true;
		message = '';
		try {
			results = await geocodeAddress(trimmed);
			mapState.addressSearchOpen = results.length > 0;
			if (results.length === 0) message = 'No U.S. results found.';
		} catch (err) {
			console.warn('[public_map] geocode failed:', err);
			message = 'Search failed. Try a city, state, or ZIP.';
			results = [];
			mapState.addressSearchOpen = false;
		} finally {
			loading = false;
		}
	}

	function choose(result: GeocodeResult) {
		mapState.addressTarget = result;
		mapState.lastAddressTarget = result;
		results = [];
		message = '';
		query = result.label;
		mapState.addressSearchOpen = false;
	}

	function clear() {
		query = '';
		results = [];
		message = '';
		mapState.addressSearchOpen = false;
	}
</script>

<section class="address-search" data-layout-slot={slotAttr(LAYOUT_SLOTS.search)} aria-label="Address and ZIP search">
	<div class="search-row">
		<input
			type="search"
			placeholder="Address, city, or ZIP"
			value={query}
			oninput={(e) => query = e.currentTarget.value}
			onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void search(); } }}
		/>
		<button type="button" onclick={search} disabled={loading || !query.trim()}>
			{loading ? '...' : 'Go'}
		</button>
		{#if query}
			<button type="button" class="icon" aria-label="Clear address search" onclick={clear}>x</button>
		{/if}
	</div>

	{#if results.length > 0}
		<div class="results">
			{#each results as result, i (`${result.provider}-${i}`)}
				<button type="button" onclick={() => choose(result)}>
					<strong>{result.resultType}</strong>
					<span>{result.label}</span>
					<small>{result.provider.replace('_', ' ')}</small>
				</button>
			{/each}
		</div>
	{:else if message}
		<p class="message">{message}</p>
	{/if}
</section>

<style>
	.address-search {
		position: absolute;
		top: 5.15rem;
		left: 1rem;
		z-index: 8;
		width: min(24rem, calc(100vw - 2rem));
		color: #cfd9e6;
		font-size: 12px;
	}
	.search-row,
	.results,
	.message {
		background: rgba(14, 23, 38, 0.94);
		border: 1px solid #2a3a52;
		backdrop-filter: blur(8px);
		box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
	}
	.search-row {
		display: grid;
		grid-template-columns: 1fr auto auto;
		gap: 0.35rem;
		padding: 0.45rem;
		border-radius: 8px;
	}
	input {
		width: 100%;
		box-sizing: border-box;
		border: 1px solid #2c4870;
		border-radius: 6px;
		background: rgba(8, 13, 22, 0.85);
		color: #e5edf5;
		padding: 0.45rem 0.55rem;
		font: inherit;
	}
	button {
		appearance: none;
		border: 1px solid #2c4870;
		border-radius: 6px;
		background: rgba(28, 42, 64, 0.85);
		color: #d8e6f3;
		cursor: pointer;
		font: inherit;
		padding: 0.35rem 0.6rem;
	}
	button:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}
	.icon {
		width: 2rem;
		padding: 0;
	}
	.results {
		display: grid;
		gap: 0.25rem;
		margin-top: 0.45rem;
		padding: 0.45rem;
		border-radius: 10px;
		max-height: 13rem;
		overflow: auto;
	}
	.results button {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.1rem 0.45rem;
		text-align: left;
		padding: 0.45rem 0.55rem;
	}
	.results strong {
		color: #7bd0f2;
		text-transform: uppercase;
		font-size: 10px;
	}
	.results span {
		color: #e5edf5;
	}
	.results small {
		grid-column: 2;
		color: #94a3b8;
	}
	.message {
		margin: 0.45rem 0 0;
		padding: 0.55rem 0.65rem;
		border-radius: 8px;
		color: #fbbf24;
	}
	input:focus,
	button:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
	}
	@media (max-width: 640px) {
		.address-search {
			top: 5.7rem;
			left: 0.5rem;
		}
	}
</style>
