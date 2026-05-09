<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import { mapState } from './store.svelte';
	import {
		createSavedSearch,
		loadSavedSearches,
		renameSavedSearch,
		saveSavedSearches,
		type SavedSearch
	} from './savedSearches';

	let open = $state(false);
	let searches = $state<SavedSearch[]>([]);
	let name = $state('');
	let renamingId = $state<string | null>(null);
	let renameValue = $state('');

	onMount(() => {
		if (!browser) return;
		searches = loadSavedSearches();
	});

	function persist(next: SavedSearch[]) {
		searches = next;
		saveSavedSearches(next);
	}

	function defaultName(): string {
		const bits = [
			mapState.filters.agencies.join('+'),
			mapState.filters.series && `series ${mapState.filters.series}`,
			mapState.filters.gradeMin && `GS ${mapState.filters.gradeMin}+`,
			mapState.filters.remote !== 'any' && mapState.filters.remote,
			mapState.metric !== 'postings' && mapState.metric.replace('_', ' ')
		].filter(Boolean);
		return bits.join(' / ') || 'Current map view';
	}

	function saveCurrent() {
		const item = createSavedSearch({
			name: name || defaultName(),
			filters: mapState.filters,
			metric: mapState.metric,
			viewport: mapState.viewport,
			addressTarget: mapState.lastAddressTarget
		});
		persist([item, ...searches]);
		name = '';
		open = true;
		mapState.savedSearchesOpen = true;
	}

	function applySearch(item: SavedSearch) {
		mapState.filters = item.filters;
		mapState.metric = item.metric;
		mapState.choroplethEnabled = true;
		if (item.addressTarget) {
			mapState.lastAddressTarget = item.addressTarget;
			mapState.addressTarget = item.addressTarget;
		} else if (item.viewport) mapState.pendingViewport = item.viewport;
		open = false;
		mapState.savedSearchesOpen = false;
	}

	function deleteSearch(id: string) {
		persist(searches.filter((item) => item.id !== id));
		if (renamingId === id) renamingId = null;
	}

	function startRename(item: SavedSearch) {
		renamingId = item.id;
		renameValue = item.name;
	}

	function commitRename(item: SavedSearch) {
		persist(searches.map((candidate) => candidate.id === item.id ? renameSavedSearch(candidate, renameValue) : candidate));
		renamingId = null;
		renameValue = '';
	}
</script>

<section
	class="saved-searches"
	class:address-open={mapState.addressSearchOpen}
	data-layout-slot={slotAttr(LAYOUT_SLOTS.search)}
	aria-label="Saved searches"
>
	<button
		type="button"
		class="toggle"
		aria-expanded={open}
		onclick={() => {
			open = !open;
			mapState.savedSearchesOpen = open;
		}}
	>
		<span>Saved searches</span>
		<strong>{searches.length}</strong>
	</button>

	{#if open}
		<div class="menu">
			<div class="save-row">
				<input
					type="text"
					placeholder={defaultName()}
					value={name}
					oninput={(e) => name = e.currentTarget.value}
					onkeydown={(e) => { if (e.key === 'Enter') saveCurrent(); }}
				/>
				<button type="button" onclick={saveCurrent}>Save</button>
			</div>

			{#if searches.length === 0}
				<p class="empty">No saved searches yet.</p>
			{:else}
				<ul>
					{#each searches as item (item.id)}
						<li>
							{#if renamingId === item.id}
								<div class="rename-row">
									<input
										type="text"
										value={renameValue}
										oninput={(e) => renameValue = e.currentTarget.value}
										onkeydown={(e) => { if (e.key === 'Enter') commitRename(item); }}
									/>
									<button type="button" onclick={() => commitRename(item)}>OK</button>
								</div>
							{:else}
								<button type="button" class="saved-item" onclick={() => applySearch(item)}>
									<strong>{item.name}</strong>
									<span>{item.metric.replace('_', ' ')} · {new Date(item.updatedAt).toLocaleDateString()}</span>
								</button>
								<div class="actions">
									<button type="button" onclick={() => startRename(item)}>Rename</button>
									<button type="button" onclick={() => deleteSearch(item.id)}>Delete</button>
								</div>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</section>

<style>
	.saved-searches {
		position: absolute;
		top: 8.85rem;
		left: 1rem;
		z-index: 7;
		width: min(24rem, calc(100vw - 2rem));
		color: #cfd9e6;
		font-size: 12px;
		transition: top 160ms ease;
	}
	.saved-searches.address-open {
		top: 21rem;
	}
	.toggle,
	.menu {
		background: rgba(14, 23, 38, 0.94);
		border: 1px solid #2a3a52;
		backdrop-filter: blur(8px);
		box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
	}
	.toggle {
		appearance: none;
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.65rem 0.8rem;
		border-radius: 8px;
		color: #e5edf5;
		cursor: pointer;
		font-weight: 600;
	}
	.toggle strong {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.35rem;
		height: 1.35rem;
		border-radius: 999px;
		background: #4979b3;
		color: #fff;
		font-size: 11px;
	}
	.menu {
		margin-top: 0.45rem;
		padding: 0.75rem;
		border-radius: 10px;
	}
	.save-row,
	.rename-row {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.4rem;
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
		font: inherit;
	}
	.save-row button,
	.rename-row button,
	.actions button {
		appearance: none;
		border: 1px solid #2c4870;
		border-radius: 6px;
		background: rgba(28, 42, 64, 0.85);
		color: #d8e6f3;
		cursor: pointer;
		padding: 0.35rem 0.55rem;
	}
	ul {
		list-style: none;
		margin: 0.7rem 0 0;
		padding: 0;
		display: grid;
		gap: 0.45rem;
		max-height: 16rem;
		overflow: auto;
	}
	li {
		display: grid;
		gap: 0.35rem;
		padding-bottom: 0.45rem;
		border-bottom: 1px solid #22344c;
	}
	.saved-item {
		appearance: none;
		border: 0;
		background: transparent;
		color: inherit;
		padding: 0;
		text-align: left;
		cursor: pointer;
		display: grid;
		gap: 0.15rem;
	}
	.saved-item strong {
		color: #fff;
	}
	.saved-item span,
	.empty {
		color: #94a3b8;
	}
	.actions {
		display: flex;
		gap: 0.35rem;
	}
	.empty {
		margin: 0.65rem 0 0;
	}
	input:focus,
	button:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
	}
	@media (max-width: 640px) {
		.saved-searches {
			top: 9.4rem;
			left: 0.5rem;
		}
		.saved-searches.address-open {
			top: 21.5rem;
		}
	}
</style>
