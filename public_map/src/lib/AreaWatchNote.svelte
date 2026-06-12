<!--
	AreaWatchNote — D.5.28's "What to watch" note on the Here card, per
	ADR-0036: deterministic and keyless. No LLM, no new Pages Function, no
	secret in the deployment — the note is derived client-side by
	./areaWatch.ts from a 3-year `/api/job-history` payload (the existing
	ADR-0029 edge-cached Function over public, key-less HistoricJoa).

	Same contract as AreaTrendSparkline:
	  • Click-to-load only (invariant #22) — never prefetched.
	  • The caption names the exact slice; approximations (locality→state
	    fallback, ignored extra chips) are listed, never silently dropped.
	  • Claims that fail their evidence bar are shown as "withheld" with the
	    reason — absence of a claim is explained, not papered over.
	  • Upstream failure renders an explicit unavailable message.
	  • Filter drift after load → "filters changed" reload notice, no
	    auto-refetch.

	No $effect reads+writes mapState (WebKit state_unsafe_mutation rule):
	all writes are to component-local $state inside event handlers.
-->
<script lang="ts">
	import { mapState } from './store.svelte';
	import { buildAreaTrendQuery } from './areaTrend';
	import { computeWatchNote, WATCH_WINDOW, type WatchNote } from './areaWatch';
	import type { ResolvedArea } from './areaCard';
	import type { HistoryPayload } from './jobHistory';
	import InfoTooltip from './InfoTooltip.svelte';

	let { area }: { area: ResolvedArea } = $props();

	let opened = $state(false);
	let loading = $state(false);
	let note = $state<WatchNote | null>(null);
	let unavailable = $state<string | null>(null);
	let error = $state<string | null>(null);
	let loadedKey = $state<string | null>(null);
	let loadedDescription = $state('');
	let loadedNotes = $state<string[]>([]);

	const built = $derived(buildAreaTrendQuery(area, mapState.filters, WATCH_WINDOW));
	const stale = $derived(note !== null && loadedKey !== null && loadedKey !== built.key);

	async function load() {
		const snapshot = built;
		loading = true;
		error = null;
		unavailable = null;
		const q = snapshot.query;
		const params = new URLSearchParams();
		if (q.agencyCode) params.set('agency_code', q.agencyCode);
		if (q.series) params.set('series', q.series);
		if (q.grade) params.set('grade', q.grade);
		if (q.state) params.set('state', q.state);
		params.set('window', WATCH_WINDOW);
		try {
			const response = await fetch(`/api/job-history?${params.toString()}`, {
				headers: { Accept: 'application/json' }
			});
			if (!response.ok) throw new Error(`history endpoint returned ${response.status}`);
			const payload = (await response.json()) as HistoryPayload;
			const next = computeWatchNote(payload);
			if (next === null) {
				note = null;
				loadedKey = null;
				unavailable = payload.error ?? 'upstream error';
			} else {
				note = next;
				loadedKey = snapshot.key;
				loadedDescription = snapshot.description;
				loadedNotes = snapshot.notes;
			}
		} catch (err) {
			note = null;
			loadedKey = null;
			error = err instanceof Error ? err.message : 'history endpoint unreachable';
		} finally {
			loading = false;
		}
	}

	function toggle() {
		opened = !opened;
		if (opened && !note && !loading) load();
	}
</script>

<section class="watch">
	<button type="button" class="toggle" onclick={toggle} aria-expanded={opened}>
		<span class="caret" aria-hidden="true">{opened ? '▾' : '▸'}</span>
		<span>What to watch · 3-year context</span>
		<span class="hint">{opened ? 'collapse' : 'click to load'}</span>
	</button>

	{#if opened}
		<div class="body">
			{#if loading}
				<p class="note">Loading HistoricJoa…</p>
			{:else if error}
				<p class="error">What-to-watch unavailable: {error}. Try again in a few minutes.</p>
			{:else if unavailable}
				<p class="error">
					What-to-watch unavailable right now ({unavailable}). Try again after about an hour.
				</p>
			{:else if note}
				<p class="slice">
					Deterministic, auto-generated · <strong>{loadedDescription}</strong>
					<InfoTooltip title="How this note is made" align="end">
						<span>Templated prose computed from a 3-year window of HistoricJoa postings (year-over-year, seasonal averages, median open→close window). No language model is involved; every claim has a minimum-evidence bar and is withheld with a reason when the data is too thin.</span>
						<span class="src">Source: USAJOBS /api/historicjoa via the edge-cached Function (ADR-0029), loaded on demand.</span>
					</InfoTooltip>
				</p>
				{#each loadedNotes as approx (approx)}
					<p class="approx">≈ {approx}</p>
				{/each}

				{#if stale}
					<div class="stale">
						<span>Filters changed since this note loaded.</span>
						<button type="button" onclick={() => load()}>Reload</button>
					</div>
				{/if}

				{#if note.lines.length > 0}
					<ul class="lines">
						{#each note.lines as line (line)}
							<li>{line}</li>
						{/each}
					</ul>
				{:else}
					<p class="note">Not enough history in this slice to say anything defensible yet.</p>
				{/if}
				{#each note.withheld as reason (reason)}
					<p class="withheld">⊘ {reason}</p>
				{/each}
				<p class="basis">{note.basis}</p>
			{/if}
		</div>
	{/if}
</section>

<style>
	.watch {
		margin: 0 0 0.7rem;
		border: 1px solid var(--c-border-subtle, #22344c);
		border-radius: 8px;
		background: var(--c-row-bg, rgba(20, 32, 50, 0.55));
		padding: 0.35rem 0.6rem 0.45rem;
	}
	.toggle {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		width: 100%;
		appearance: none;
		border: none;
		background: transparent;
		color: var(--c-text-2, #cfd9e6);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
		padding: 0.2rem 0;
		text-align: left;
	}
	.toggle:hover {
		color: var(--c-accent, #7bd0f2);
	}
	.caret {
		color: var(--c-accent, #7bd0f2);
		width: 0.8em;
	}
	.hint {
		margin-left: auto;
		color: var(--c-muted, #94a3b8);
		font-size: 10px;
		font-weight: 400;
	}
	.body {
		margin-top: 0.35rem;
	}
	.slice {
		margin: 0 0 0.3rem;
		font-size: 11px;
		line-height: 1.45;
		color: var(--c-muted, #94a3b8);
	}
	.slice strong {
		color: var(--c-text-2, #cfd9e6);
		font-weight: 600;
	}
	.approx {
		margin: 0 0 0.3rem;
		font-size: 10px;
		line-height: 1.45;
		color: var(--c-warn, #f0c878);
	}
	.stale {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		justify-content: space-between;
		font-size: 10.5px;
		color: var(--c-warn, #f0c878);
		border: 1px dashed var(--c-warn, #b48a3a);
		border-radius: 6px;
		padding: 0.3rem 0.5rem;
		margin: 0 0 0.4rem;
	}
	.stale button {
		appearance: none;
		border: 1px solid var(--c-border-input, #2c4870);
		background: var(--c-row-bg, rgba(28, 42, 64, 0.4));
		color: var(--c-accent, #7bd0f2);
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		font: inherit;
		font-size: 10.5px;
		cursor: pointer;
	}
	.stale button:hover {
		border-color: var(--c-accent, #7bd0f2);
	}
	.lines {
		list-style: none;
		margin: 0 0 0.35rem;
		padding: 0;
	}
	.lines li {
		font-size: 11.5px;
		line-height: 1.55;
		color: var(--c-text-2, #cfd9e6);
		padding-left: 0.85rem;
		position: relative;
	}
	.lines li::before {
		content: '▪';
		position: absolute;
		left: 0;
		color: var(--c-accent-dim, #4979b3);
	}
	.withheld {
		margin: 0 0 0.25rem;
		font-size: 10px;
		line-height: 1.45;
		color: var(--c-muted, #94a3b8);
		font-style: italic;
	}
	.basis {
		margin: 0.3rem 0 0;
		font-size: 9.5px;
		color: var(--c-faint, #64748b);
	}
	.note {
		margin: 0.2rem 0 0;
		font-size: 11px;
		color: var(--c-muted, #94a3b8);
	}
	.error {
		margin: 0.2rem 0 0;
		font-size: 11px;
		color: var(--c-danger, #f1bcbc);
	}
	.src {
		display: block;
		margin-top: 0.3rem;
		font-size: 10px;
		color: var(--c-muted, #94a3b8);
	}
</style>
