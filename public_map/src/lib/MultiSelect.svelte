<!--
	MultiSelect — one searchable, chip-based multi-select used for every
	code-backed filter facet (agency, pay plan, hiring path, series). Selected
	values render as removable chips; a search box opens a dropdown of the
	available options (each with a posting count) and clicking one adds it.

	The component is presentational: it owns only its local search/open state and
	calls `onAdd` / `onRemove` so the parent stays the single writer of
	`mapState.filters`. `chipLabel` resolves a value's display name independently
	of `options`, so a selected chip still labels correctly even after the
	narrowed option list no longer contains it.
-->
<script lang="ts">
	import type { FacetOption } from './filterFacets';

	let {
		label,
		selected,
		options,
		chipLabel,
		onAdd,
		onRemove,
		placeholder = 'Search…',
		emptyHint = 'No matching options in the current results.',
		maxResults = 60
	}: {
		label: string;
		selected: string[];
		options: FacetOption[];
		chipLabel: (value: string) => string;
		onAdd: (value: string) => void;
		onRemove: (value: string) => void;
		placeholder?: string;
		emptyHint?: string;
		maxResults?: number;
	} = $props();

	let query = $state('');
	let open = $state(false);
	let blurTimer: ReturnType<typeof setTimeout> | null = null;

	const selectedSet = $derived(new Set(selected));

	const visible = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return options
			.filter((o) => !selectedSet.has(o.value))
			.filter((o) =>
				!q || `${o.label} ${o.sub ?? ''} ${o.value} ${o.keywords ?? ''}`.toLowerCase().includes(q)
			)
			.slice(0, maxResults);
	});

	function choose(value: string) {
		onAdd(value);
		query = '';
		open = true;
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			if (visible.length > 0) choose(visible[0].value);
		} else if (e.key === 'Escape') {
			open = false;
		}
	}

	function onFocus() {
		if (blurTimer) clearTimeout(blurTimer);
		open = true;
	}
	function onBlur() {
		// Delay so a click on an option (which blurs the input) still registers.
		blurTimer = setTimeout(() => (open = false), 150);
	}
</script>

<div class="ms">
	<span class="field-label">{label}</span>

	{#if selected.length > 0}
		<div class="chips" aria-label="Selected {label}">
			{#each selected as value (value)}
				<button type="button" class="chip" onclick={() => onRemove(value)} title="Remove {chipLabel(value)}">
					<span class="chip-text">{chipLabel(value)}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/each}
		</div>
	{/if}

	<div class="search-wrap">
		<input
			class="search"
			type="search"
			{placeholder}
			bind:value={query}
			onfocus={onFocus}
			onblur={onBlur}
			onkeydown={onKeydown}
			autocomplete="off"
			aria-label="{label} search"
		/>
	</div>

	{#if open}
		<div class="dropdown" role="listbox">
			{#if visible.length > 0}
				{#each visible as o (o.value)}
					<!-- pointerdown fires before the input's blur so the option commits. -->
					<button type="button" class="option" onpointerdown={(e) => { e.preventDefault(); choose(o.value); }}>
						<span class="o-label">{o.label}</span>
						<span class="o-meta">
							{#if o.sub && o.sub !== o.label}<span class="o-sub">{o.sub}</span>{/if}
							<span class="o-count">{o.count.toLocaleString()}</span>
						</span>
					</button>
				{/each}
			{:else}
				<p class="empty">{query.trim() ? `No match for “${query.trim()}”.` : emptyHint}</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.ms {
		display: grid;
		gap: 0.4rem;
		position: relative;
	}
	.field-label {
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
	}
	.chip {
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border: 1px solid var(--c-accent-dim, #4979b3);
		border-radius: 999px;
		background: var(--c-accent-bg-strong, rgba(73, 121, 179, 0.2));
		color: var(--c-text, #e5edf5);
		padding: 0.28rem 0.55rem;
		cursor: pointer;
		font: inherit;
		font-size: 11px;
		max-width: 100%;
	}
	.chip:hover {
		border-color: var(--c-danger, #f7a0a0);
	}
	.chip-text {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chip .x {
		color: var(--c-text, #fff);
		font-weight: 700;
	}
	.chip:hover .x {
		color: var(--c-danger, #f7a0a0);
	}
	.search {
		width: 100%;
		box-sizing: border-box;
		border: 1px solid var(--c-border-input, #2c4870);
		border-radius: 6px;
		background: var(--c-row-bg, rgba(8, 13, 22, 0.85));
		color: var(--c-text, #e5edf5);
		padding: 0.45rem 0.55rem;
		font: inherit;
	}
	.search:focus,
	.chip:focus-visible,
	.option:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.dropdown {
		display: grid;
		gap: 0.15rem;
		max-height: 13rem;
		overflow-y: auto;
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		background: var(--c-panel, rgba(14, 23, 38, 0.98));
		padding: 0.25rem;
		box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
	}
	.option {
		appearance: none;
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.6rem;
		text-align: left;
		width: 100%;
		border: none;
		border-radius: 5px;
		background: transparent;
		color: var(--c-text, #e5edf5);
		padding: 0.4rem 0.5rem;
		cursor: pointer;
		font: inherit;
	}
	.option:hover {
		background: var(--c-row-hover, rgba(28, 42, 64, 0.85));
	}
	.o-label {
		font-size: 12px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.o-meta {
		display: inline-flex;
		align-items: baseline;
		gap: 0.45rem;
		flex-shrink: 0;
	}
	.o-sub {
		color: var(--c-muted, #94a3b8);
		font-size: 10px;
	}
	.o-count {
		color: var(--c-accent, #7bd0f2);
		font-size: 10px;
		font-variant-numeric: tabular-nums;
	}
	.empty {
		margin: 0;
		padding: 0.4rem 0.5rem;
		color: var(--c-muted, #94a3b8);
		font-size: 11px;
		line-height: 1.4;
	}
</style>
