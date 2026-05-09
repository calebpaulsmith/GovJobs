<!--
	ScopedAreaActions — compact action widget shown at the top of the FeaturePanel
	when a state or locality polygon is selected. Supports:
	  • "Search only here" — replaces the geographies filter with just this area
	  • "Add to search" — appends this area to existing geography chips (OR logic)
	  • "Remove" — removes this area from the geography filter
	Geography chips have the form "state:IL" or "locality:DC".
-->
<script lang="ts">
	import { mapState } from './store.svelte';
	import { LAYOUT_SLOTS, slotAttr } from './layout';

	let {
		type,
		code,
		label
	}: { type: 'state' | 'locality' | 'county' | 'metro'; code: string; label: string } = $props();

	const geoKey = $derived(`${type}:${code.toUpperCase()}`);
	const isInSearch = $derived(mapState.filters.geographies.includes(geoKey));
	const hasOtherGeos = $derived(
		mapState.filters.geographies.some((g) => g !== geoKey)
	);

	function searchOnlyHere() {
		mapState.filters = { ...mapState.filters, geographies: [geoKey] };
	}

	function addToSearch() {
		if (!isInSearch) {
			mapState.filters = {
				...mapState.filters,
				geographies: [...mapState.filters.geographies, geoKey]
			};
		}
	}

	function removeFromSearch() {
		mapState.filters = {
			...mapState.filters,
			geographies: mapState.filters.geographies.filter((g) => g !== geoKey)
		};
	}

	const typeLabel = $derived(
		type === 'state' ? 'State' :
		type === 'locality' ? 'Locality' :
		type === 'county' ? 'County' :
		'Metro'
	);
</script>

<div class="scoped" data-layout-slot={slotAttr(LAYOUT_SLOTS['scoped-window'])}>
	<div class="header">
		<span class="type-label">{typeLabel} scope</span>
		<span class="area-name">{label}</span>
	</div>
	<div class="actions">
		{#if isInSearch}
			<span class="in-search">✓ In search scope</span>
			{#if hasOtherGeos}
				<span class="geo-count">(+{mapState.filters.geographies.length - 1} other{mapState.filters.geographies.length - 1 === 1 ? '' : 's'})</span>
			{/if}
			<button type="button" class="btn-remove" onclick={removeFromSearch} aria-label="Remove {label} from search scope">
				✕ Remove
			</button>
		{:else}
			<button type="button" class="btn-primary" onclick={searchOnlyHere}>
				Search only here
			</button>
			{#if mapState.filters.geographies.length > 0}
				<button type="button" class="btn-secondary" onclick={addToSearch}>
					+ Add to search
				</button>
			{:else}
				<button type="button" class="btn-secondary" onclick={addToSearch}>
					+ Add to search
				</button>
			{/if}
		{/if}
	</div>
	{#if mapState.filteredJobCount > 0 || mapState.filters.geographies.length > 0}
		<p class="hint">
			{mapState.filteredJobCount.toLocaleString()} posting{mapState.filteredJobCount === 1 ? '' : 's'} match active filters across all scopes.
		</p>
	{/if}
</div>

<style>
	.scoped {
		padding: 0.55rem 0.75rem;
		margin-bottom: 0.65rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 8px;
		background: var(--c-accent-bg, rgba(123, 208, 242, 0.06));
	}
	.header {
		display: flex;
		align-items: baseline;
		gap: 0.45rem;
		margin-bottom: 0.45rem;
	}
	.type-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--c-accent, #7bd0f2);
		font-weight: 600;
	}
	.area-name {
		font-size: 12px;
		font-weight: 700;
		color: var(--c-text, #e5edf5);
	}
	.actions {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		flex-wrap: wrap;
	}
	.btn-primary,
	.btn-secondary,
	.btn-remove {
		appearance: none;
		border-radius: 999px;
		font-size: 11px;
		font-weight: 600;
		padding: 0.22rem 0.65rem;
		cursor: pointer;
		transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
	}
	.btn-primary {
		background: var(--c-accent, #7bd0f2);
		border: 1px solid var(--c-accent, #7bd0f2);
		color: var(--c-apply-text, #06111f);
	}
	.btn-primary:hover {
		background: var(--c-apply-hover, #a8e0f5);
		border-color: var(--c-apply-hover, #a8e0f5);
	}
	.btn-secondary {
		background: transparent;
		border: 1px solid var(--c-accent-dim, #4979b3);
		color: var(--c-text-2, #cfd9e6);
	}
	.btn-secondary:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.btn-remove {
		background: transparent;
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-muted, #94a3b8);
	}
	.btn-remove:hover {
		border-color: var(--c-danger, #f7a0a0);
		color: var(--c-danger, #f7a0a0);
	}
	.in-search {
		font-size: 11px;
		font-weight: 600;
		color: var(--c-accent, #7bd0f2);
	}
	.geo-count {
		font-size: 10px;
		color: var(--c-muted, #94a3b8);
	}
	.hint {
		margin: 0.4rem 0 0;
		font-size: 10px;
		color: var(--c-faint, #64748b);
		line-height: 1.4;
	}
</style>
