<!--
	BrowseJobPanel — the job-detail content for /browse (ADR-0039), shared by
	two hosts:
	  • BrowseSheet (mobile bottom sheet, < 1024 px) — shown as a detail view
	    over the Postings list, with a "Back to postings" control in the sheet
	  • the desktop mosaic's top-right pane (≥ 1024 px)

	Browse is for finding jobs, so this renders only job things: the JobCard
	for a tapped marker / list row / shared `selected=` link, or a
	PointJobList for a tapped same-point stack. A tapped polygon gets a small
	area card whose actions are "Add this area to my list" (the explicit,
	opt-in geography chip — ADR-0033 #5) and "Analyze this area →", which
	opens the Analysis screen for it. Area metrics (the old Here card) now
	live on /analysis.

	`emptyHint` (desktop) renders a prompt when nothing is selected.
-->
<script lang="ts">
	import { mapState } from './store.svelte';
	import { LAYER_IDS } from './layers';
	import { propString, countValue } from './format';
	import JobCard from './JobCard.svelte';
	import PointJobList from './PointJobList.svelte';

	let { emptyHint = false }: { emptyHint?: boolean } = $props();

	const sel = $derived(mapState.selectedFeature);
	const isJob = $derived(
		!!sel && (sel.source === LAYER_IDS.markers || (sel.source === 'share' && sel.label === 'Job card'))
	);

	// Area tapped on the map → level/code for chips and the Analysis link.
	const tappedArea = $derived.by(() => {
		if (!sel) return null;
		const p = sel.properties ?? {};
		switch (sel.source) {
			case LAYER_IDS.statesFill:
				return { level: 'state', code: String(p.state ?? '').toUpperCase(), name: propString(p, 'name') };
			case LAYER_IDS.localitiesFill:
				return { level: 'locality', code: String(p.code ?? '').toUpperCase(), name: propString(p, 'name') };
			case LAYER_IDS.countiesOutline: {
				const st = String(p.state ?? '');
				return { level: 'county', code: String(p.fips ?? ''), name: `${propString(p, 'name')} County${st ? `, ${st}` : ''}` };
			}
			case LAYER_IDS.metrosOutline:
				return { level: 'metro', code: String(p.cbsa_code ?? ''), name: propString(p, 'name') };
			default:
				return null;
		}
	});

	// Explicit, opt-in geography add. Mirrors the chip format ScopedAreaActions
	// uses on /map so the two paths produce identical, deduped chips.
	function addAreaToList(type: string, code: string) {
		const chip = `${type}:${code}`;
		if (!code || mapState.filters.geographies.includes(chip)) return;
		mapState.filters = { ...mapState.filters, geographies: [...mapState.filters.geographies, chip] };
	}
	function isInList(type: string, code: string): boolean {
		return mapState.filters.geographies.includes(`${type}:${code}`);
	}
</script>

{#if mapState.jobStack && !sel}
	<!-- {#key} forces PointJobList to fully remount when the jobStack's items
	     count changes (the cluster path seeds an empty stack synchronously and
	     fills it from an async leaves callback). -->
	{#key mapState.jobStack.items.length}
		<PointJobList stack={mapState.jobStack} />
	{/key}
{:else if sel && isJob}
	<JobCard properties={sel.properties} />
{:else if tappedArea}
	<section class="area-card">
		<p class="eyebrow">{tappedArea.level === 'metro' ? 'Metro area' : tappedArea.level[0].toUpperCase() + tappedArea.level.slice(1)}</p>
		<h2>{tappedArea.name}</h2>
		<p class="sub">{countValue(sel?.properties?.postings)} open postings here · the list below is narrowed to this area.</p>
		<div class="actions">
			<a class="action primary" href={`/analysis?area=${tappedArea.level}:${encodeURIComponent(tappedArea.code)}`}>
				Analyze this area →
			</a>
			{#if tappedArea.level === 'state' || tappedArea.level === 'locality'}
				<button
					type="button"
					class="action"
					disabled={isInList(tappedArea.level, tappedArea.code)}
					onclick={() => addAreaToList(tappedArea.level, tappedArea.code)}
				>
					{isInList(tappedArea.level, tappedArea.code) ? '✓ In your list' : '+ Add to my list'}
				</button>
			{/if}
		</div>
	</section>
{:else if emptyHint}
	<section class="empty">
		<h2>Job details</h2>
		<p>Select a job on the map or in the list below to see its details here.</p>
		<p class="hint">Looking for trends, pay vs. cost of living, or how busy an area is? Open <a href="/analysis">Analysis</a>.</p>
	</section>
{/if}

<style>
	.area-card,
	.empty {
		padding: 0.2rem 0.1rem;
		color: var(--c-text-2, #cfd9e6);
	}
	.eyebrow {
		margin: 0 0 0.15rem;
		color: var(--c-accent, #7bd0f2);
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	h2 {
		margin: 0 0 0.3rem;
		font-size: 17px;
		color: var(--c-text, #e5edf5);
	}
	.sub,
	.empty p {
		margin: 0 0 0.6rem;
		font-size: 12px;
		line-height: 1.45;
	}
	.hint {
		color: var(--c-muted, #94a3b8);
	}
	.empty a {
		color: var(--c-accent, #7bd0f2);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.action {
		appearance: none;
		display: inline-flex;
		align-items: center;
		min-height: 2.25rem;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		color: var(--c-text, #e5edf5);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		padding: 0.35rem 0.8rem;
		border-radius: 8px;
		text-decoration: none;
		cursor: pointer;
	}
	.action.primary {
		border-color: var(--c-accent-dim, #4979b3);
		background: var(--c-accent-bg-strong, rgba(73, 121, 179, 0.2));
	}
	.action:hover:not(:disabled) {
		border-color: var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
	}
	.action:disabled {
		cursor: default;
		opacity: 0.7;
	}
</style>
