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
	import { payPlanLabel, hiringPathLabel } from './filterFacets';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import { loadAgencyOptions, loadCountryOptions, type AgencyOption, type CountryOption } from './data';
	import { RADIUS_OPTIONS } from './geo';

	// `docked` renders the strip in normal flow (inside a parent surface like
	// the BrowseSheet header) instead of the /map chip-strip layout slot.
	// Per ADR-0035 this is how /map components are reused on /browse.
	let { docked = false }: { docked?: boolean } = $props();

	let agencyOptions = $state<AgencyOption[]>([]);
	let countryOptions = $state<CountryOption[]>([]);

	onMount(() => {
		void loadAgencyOptions().then((opts) => {
			agencyOptions = opts.filter((o) => o.code);
		});
		void loadCountryOptions().then((opts) => {
			countryOptions = opts.filter((o) => o.code);
		});
	});

	function agencyName(code: string): string {
		const opt = agencyOptions.find((o) => (o.code ?? '').toUpperCase() === code.toUpperCase());
		return opt?.name ?? code;
	}

	function countryName(code: string): string {
		const opt = countryOptions.find((o) => o.code.toUpperCase() === code.toUpperCase());
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

	// All chip removals do TWO things on purpose:
	//   1. Mutate the field in place so $state proxy invalidation fires.
	//   2. Reassign mapState.filters to a fresh object so $effect blocks
	//      that captured the old reference re-run.
	// Without (2), Map.svelte's filter effect can hold the prior `filters`
	// reference and skip re-applying the source data — visible as "I removed
	// the chip but the markers are still filtered." Without (1), child reads
	// can still see stale arrays in some Svelte 5 reactivity edge cases.
	function rebuildFilters(): void {
		mapState.filters = {
			...mapState.filters,
			agencies: [...mapState.filters.agencies],
			series: [...mapState.filters.series],
			payPlans: [...mapState.filters.payPlans],
			hiringPaths: [...mapState.filters.hiringPaths],
			countries: [...mapState.filters.countries],
			geographies: [...mapState.filters.geographies],
			radii: [...mapState.filters.radii]
		};
	}

	// --- radius chips (D.5.30) ---
	// Which radius chip's distance popover is open (by index, or null).
	let openRadius = $state<number | null>(null);

	function removeRadius(index: number): void {
		mapState.filters.radii = mapState.filters.radii.filter((_, i) => i !== index);
		openRadius = null;
		rebuildFilters();
	}
	function setRadiusMiles(index: number, miles: number): void {
		mapState.filters.radii = mapState.filters.radii.map((chip, i) =>
			i === index ? { ...chip, miles } : chip
		);
		openRadius = null;
		rebuildFilters();
	}
	function toggleRadiusRemote(index: number): void {
		mapState.filters.radii = mapState.filters.radii.map((chip, i) =>
			i === index ? { ...chip, includeRemote: !chip.includeRemote } : chip
		);
		rebuildFilters();
	}

	function removeAgency(code: string): void {
		mapState.filters.agencies = mapState.filters.agencies.filter((a) => a !== code);
		rebuildFilters();
	}

	type ListKey = 'agencies' | 'series' | 'payPlans' | 'hiringPaths' | 'countries' | 'geographies';
	function removeValue(key: ListKey, value: string): void {
		mapState.filters[key] = mapState.filters[key].filter((v) => v !== value);
		rebuildFilters();
	}

	function removeGeography(geo: string): void {
		removeValue('geographies', geo);
	}

	function clearKey<K extends keyof JobFilters>(key: K): void {
		(mapState.filters as JobFilters)[key] = DEFAULT_FILTERS[key];
		rebuildFilters();
	}

	function clearGradeBand(): void {
		mapState.filters.gradeMin = '';
		mapState.filters.gradeMax = '';
		rebuildFilters();
	}

	function clearAll(): void {
		mapState.filters = { ...DEFAULT_FILTERS, agencies: [], geographies: [], radii: [] };
	}

	const hasFilters = $derived(activeFilterCount(mapState.filters) > 0);
</script>

<div
	class="strip"
	class:empty={!hasFilters}
	class:docked
	data-layout-slot={docked ? undefined : slotAttr(LAYOUT_SLOTS['chip-strip'])}
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

			{#each mapState.filters.countries as code (code)}
				<button type="button" class="chip ctry" onclick={() => removeValue('countries', code)}>
					<span class="chip-tag">Country</span>
					<span class="chip-label">{countryName(code)}</span>
					<span class="x" aria-hidden="true">×</span>
					<span class="sr">Remove {countryName(code)}</span>
				</button>
			{/each}

			{#each mapState.filters.geographies as geo (geo)}
				<button type="button" class="chip geo" onclick={() => removeGeography(geo)}>
					<span class="chip-label">{geographyLabel(geo)}</span>
					<span class="x" aria-hidden="true">×</span>
					<span class="sr">Remove {geographyLabel(geo)}</span>
				</button>
			{/each}

			{#each mapState.filters.radii as chip, i (chip.center[0] + ',' + chip.center[1] + ',' + i)}
				<span class="chip radius" class:remote-off={!chip.includeRemote}>
					<span class="chip-tag">Within</span>
					<button
						type="button"
						class="radius-dist"
						aria-haspopup="listbox"
						aria-expanded={openRadius === i}
						onclick={() => (openRadius = openRadius === i ? null : i)}
						title="Change radius"
					>
						{chip.miles} mi ▾
					</button>
					<span class="chip-label">of {chip.label}</span>
					<button
						type="button"
						class="radius-remote"
						class:on={chip.includeRemote}
						onclick={() => toggleRadiusRemote(i)}
						title={chip.includeRemote ? 'Anywhere-remote postings included — click to exclude' : 'Anywhere-remote postings excluded — click to include'}
					>
						{chip.includeRemote ? '+ remote' : 'no remote'}
					</button>
					<button type="button" class="radius-x" onclick={() => removeRadius(i)} aria-label="Remove radius near {chip.label}">×</button>
					{#if openRadius === i}
						<span class="radius-pop" role="listbox" aria-label="Radius in miles">
							{#each RADIUS_OPTIONS as opt (opt)}
								<button
									type="button"
									role="option"
									aria-selected={chip.miles === opt}
									class:sel={chip.miles === opt}
									onclick={() => setRadiusMiles(i, opt)}
								>
									{opt} mi
								</button>
							{/each}
						</span>
					{/if}
				</span>
			{/each}

			{#each mapState.filters.series as code (code)}
				<button type="button" class="chip" onclick={() => removeValue('series', code)}>
					<span class="chip-tag">Series</span>
					<span class="chip-label">{code}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/each}

			{#each mapState.filters.payPlans as code (code)}
				<button type="button" class="chip" onclick={() => removeValue('payPlans', code)}>
					<span class="chip-tag">Plan</span>
					<span class="chip-label">{payPlanLabel(code)}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/each}

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

			{#each mapState.filters.hiringPaths as code (code)}
				<button type="button" class="chip" onclick={() => removeValue('hiringPaths', code)}>
					<span class="chip-tag">Path</span>
					<span class="chip-label">{hiringPathLabel(code)}</span>
					<span class="x" aria-hidden="true">×</span>
				</button>
			{/each}
		</div>

		<button type="button" class="clear-all" onclick={clearAll} aria-label="Clear all filters">
			Clear all
		</button>
	{/if}
</div>

<style>
	.strip {
		/* Position from public_map/src/lib/layout.ts (slot 'chip-strip'). */
		position: absolute;
		top: var(--slot-chip-strip-top);
		bottom: var(--slot-chip-strip-bottom);
		left: var(--slot-chip-strip-left);
		right: var(--slot-chip-strip-right);
		transform: var(--slot-chip-strip-transform);
		z-index: 5;
		max-width: var(--slot-chip-strip-max-width);
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
	.strip.docked {
		/* In-flow inside a parent surface (BrowseSheet header): no slot
		   positioning, no floating-panel chrome of its own. */
		position: static;
		max-width: none;
		border-radius: 10px;
		box-shadow: none;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
	}
	.strip.docked .chips {
		flex-wrap: nowrap;
		overflow-x: auto;
		-webkit-overflow-scrolling: touch;
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
	.chip.radius {
		position: relative;
		gap: 0.25rem;
		border-color: rgba(255, 184, 107, 0.5);
		background: rgba(80, 50, 20, 0.6);
		cursor: default;
	}
	.chip.radius:hover {
		/* The chip itself isn't the remove target (the × is), so don't flip
		   it to the danger color the way single-action chips do. */
		border-color: rgba(255, 184, 107, 0.5);
		background: rgba(80, 50, 20, 0.6);
	}
	.radius-dist,
	.radius-remote,
	.radius-x {
		appearance: none;
		border: none;
		background: transparent;
		color: inherit;
		font: inherit;
		cursor: pointer;
		padding: 0;
	}
	.radius-dist {
		font-weight: 700;
		color: var(--c-accent, #7bd0f2);
	}
	.radius-remote {
		font-size: 9.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		padding: 0.05rem 0.35rem;
		border-radius: 999px;
		border: 1px solid var(--c-border-input, #2c4870);
		color: var(--c-muted, #94a3b8);
	}
	.radius-remote.on {
		border-color: rgba(123, 208, 242, 0.55);
		color: var(--c-accent, #7bd0f2);
	}
	.radius-x {
		width: 0.95rem;
		height: 0.95rem;
		font-size: 13px;
		font-weight: 700;
		color: var(--c-muted, #94a3b8);
		border-radius: 999px;
	}
	.radius-x:hover {
		color: var(--c-danger, #f7a0a0);
	}
	.radius-pop {
		position: absolute;
		top: calc(100% + 0.3rem);
		left: 0;
		z-index: 12;
		display: flex;
		gap: 0.2rem;
		padding: 0.3rem;
		border-radius: 8px;
		background: var(--c-panel, rgba(14, 23, 38, 0.98));
		border: 1px solid var(--c-border, #2a3a52);
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
	}
	.radius-pop button {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 10.5px;
		font-weight: 600;
		padding: 0.2rem 0.45rem;
		border-radius: 999px;
		cursor: pointer;
		white-space: nowrap;
	}
	.radius-pop button:hover {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.radius-pop button.sel {
		background: var(--c-accent-bg-strong, rgba(123, 208, 242, 0.18));
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
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

	/* Position at every breakpoint comes from --slot-chip-strip-* in layout.ts. */
	@media (max-width: 719px) {
		.strip {
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
