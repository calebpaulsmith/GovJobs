<!--
	ActiveFilterStrip — always-visible horizontal pill row at the top of the map.
	Single source of truth for "what's currently filtering the view." Every chip
	is removable; FilterPanel, ScopedAreaActions, and QuickAdd all write to the
	same `mapState.filters`, so this strip reflects whatever those produced.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { mapState } from './store.svelte';
	import { activeFilterCount, DEFAULT_FILTERS, type JobFilters } from './filters';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import { loadAgencyOptions, type AgencyOption } from './data';

	let agencyOptions = $state<AgencyOption[]>([]);

	onMount(() => {
		void loadAgencyOptions().then((opts) => {
			agencyOptions = opts.filter((o) => o.code);
		});
	});

	function agencyName(code: string): string {
		const opt = agencyOptions.find((o) => (o.code ?? '').toUpperCase() === code.toUpperCase());
		return opt?.name ?? code;
	}

	function geographyLabel(geo: string): string {
		const sep = geo.indexOf(':');
		if (sep === -1) return geo;
		const type = geo.slice(0, sep);
		const code = geo.slice(sep + 1);
		const niceType = type === 'state' ? 'State' : type === 'locality' ? 'Locality' : type;
		return `${niceType}: ${code}`;
	}

	function removeAgency(code: string): void {
		mapState.filters = {
			...mapState.filters,
			agencies: mapState.filters.agencies.filter((a) => a !== code)
		};
	}

	function removeGeography(geo: string): void {
		mapState.filters = {
			...mapState.filters,
			geographies: mapState.filters.geographies.filter((g) => g !== geo)
		};
	}

	function clearKey<K extends keyof JobFilters>(key: K): void {
		mapState.filters = { ...mapState.filters, [key]: DEFAULT_FILTERS[key] };
	}

	function clearGradeBand(): void {
		mapState.filters = { ...mapState.filters, gradeMin: '', gradeMax: '' };
	}

	function clearAll(): void {
		mapState.filters = { ...DEFAULT_FILTERS, agencies: [], geographies: [] };
	}

	const hasFilters = $derived(activeFilterCount(mapState.filters) > 0);
</script>

<div
	class="strip"
	class:empty={!hasFilters}
	data-layout-slot={slotAttr(LAYOUT_SLOTS['chip-strip'])}
	role="region"
	aria-label="Active filters"
>
	<span class="label">Filters</span>

	{#if !hasFilters}
		<span class="hint">none active — click <strong>Filters</strong> to add</span>
	{:else}
		<div class="chips" aria-live="polite">
			{#if mapState.filters.keyword}
				<button type="button" class="chip kw" onclick={() => clearKey('keyword')}>
					<span class="chip-label">“{mapState.filters.keyword}”</span>
					<span class="x" aria-hidden="true">×</span>
					<span class="sr">Remove keyword filter</span>
				</button>
			{/if}

			{#each mapState.filters.agencies as code (code)}
				<button type="button" class="chip ag" onclick={() => removeAgency(code)}>
					<span class="chip-tag">Agency</span>
					<span class="chip-label">{agencyName(code)}</span>
					<span class="x" aria-hidden="true">×</span>
					<span class="sr">Remove {agencyName(code)}</span>
				</button>
			{/each}

			{#each mapState.filters.geographies as geo (geo)}
				<button type="button" class="chip geo" onclick={() => removeGeography(geo)}>
					<span class="chip-label">{geographyLabel(geo)}</span>
					<span class="x" aria-hidden="true">×</span>
					<span class="sr">Remove {geographyLabel(geo)}</span>
				</button>
			{/each}

			{#if mapState.filters.series}
				<button type="button" class="chip" onclick={() => clearKey('series')}>
					<span class="chip-tag">Series</span>
					<span class="chip-label">{mapState.filters.series}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/if}

			{#if mapState.filters.payPlan}
				<button type="button" class="chip" onclick={() => clearKey('payPlan')}>
					<span class="chip-tag">Plan</span>
					<span class="chip-label">{mapState.filters.payPlan}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/if}

			{#if mapState.filters.gradeMin || mapState.filters.gradeMax}
				<button type="button" class="chip" onclick={clearGradeBand}>
					<span class="chip-tag">Grade</span>
					<span class="chip-label">
						{mapState.filters.gradeMin || '—'}–{mapState.filters.gradeMax || '—'}
					</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/if}

			{#if mapState.filters.salaryMin}
				<button type="button" class="chip" onclick={() => clearKey('salaryMin')}>
					<span class="chip-tag">Salary ≥</span>
					<span class="chip-label">${Number(mapState.filters.salaryMin).toLocaleString()}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/if}

			{#if mapState.filters.remote !== 'any'}
				<button type="button" class="chip" onclick={() => clearKey('remote')}>
					<span class="chip-tag">Remote</span>
					<span class="chip-label">{mapState.filters.remote}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/if}

			{#if mapState.filters.hiringPath}
				<button type="button" class="chip" onclick={() => clearKey('hiringPath')}>
					<span class="chip-tag">Path</span>
					<span class="chip-label">{mapState.filters.hiringPath}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/if}
		</div>

		<button type="button" class="clear-all" onclick={clearAll} aria-label="Clear all filters">
			Clear all
		</button>
	{/if}
</div>

<style>
	.strip {
		position: absolute;
		top: 4.4rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 5;
		max-width: min(72rem, calc(100vw - 2rem));
		display: flex;
		gap: 0.5rem;
		align-items: center;
		padding: 0.4rem 0.7rem;
		background: var(--c-panel-blur, rgba(14, 23, 38, 0.92));
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 999px;
		backdrop-filter: blur(8px);
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.28);
		pointer-events: all;
	}
	.strip.empty {
		opacity: 0.65;
	}
	.label {
		flex-shrink: 0;
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--c-accent, #7bd0f2);
		padding-right: 0.5rem;
		border-right: 1px solid var(--c-border, #2a3a52);
	}
	.hint {
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.hint strong {
		color: var(--c-text-2, #cfd9e6);
		font-weight: 600;
	}
	.chips {
		display: flex;
		gap: 0.35rem;
		flex-wrap: wrap;
		align-items: center;
		max-width: 100%;
		overflow: hidden;
	}
	.chip {
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
		font-size: 11px;
		font-weight: 500;
		cursor: pointer;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(28, 42, 64, 0.7));
		color: var(--c-text, #e5edf5);
		transition: border-color 120ms ease, background 120ms ease;
		white-space: nowrap;
	}
	.chip:hover {
		border-color: var(--c-danger, #f7a0a0);
		background: var(--c-row-hover, rgba(60, 30, 30, 0.5));
	}
	.chip:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 1px;
	}
	.chip.kw {
		background: rgba(28, 42, 64, 0.85);
	}
	.chip.ag {
		border-color: rgba(123, 208, 242, 0.55);
		background: rgba(28, 60, 90, 0.7);
	}
	.chip.geo {
		border-color: rgba(255, 184, 107, 0.5);
		background: rgba(80, 50, 20, 0.6);
	}
	.chip-tag {
		font-size: 9.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--c-muted, #94a3b8);
		opacity: 0.85;
	}
	.chip-label {
		font-weight: 600;
	}
	.x {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 0.95rem;
		height: 0.95rem;
		border-radius: 999px;
		font-size: 12px;
		font-weight: 700;
		color: var(--c-muted, #94a3b8);
	}
	.chip:hover .x {
		color: var(--c-danger, #f7a0a0);
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		border: 0;
	}
	.clear-all {
		appearance: none;
		flex-shrink: 0;
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
		font-size: 10.5px;
		font-weight: 600;
		cursor: pointer;
		border: 1px solid transparent;
		background: transparent;
		color: var(--c-muted, #94a3b8);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		transition: color 120ms ease, border-color 120ms ease;
	}
	.clear-all:hover {
		color: var(--c-danger, #f7a0a0);
		border-color: var(--c-danger, #f7a0a0);
	}

	@media (max-width: 720px) {
		.strip {
			top: auto;
			bottom: 5.5rem;
			max-width: calc(100vw - 1rem);
			border-radius: 10px;
			padding: 0.4rem 0.55rem;
			overflow-x: auto;
		}
		.label {
			border-right: none;
			padding-right: 0.3rem;
		}
		.chips {
			flex-wrap: nowrap;
			overflow-x: auto;
		}
	}
</style>
