<!--
	AreaTrendSparkline — D.5.28's 12-month posting volume trend on the Here
	card (SmallestAreaCard).

	Click-to-load only, per ADR-0029 / invariant #22: the data comes from the
	existing `/api/job-history` Pages Function (24-hour edge cache over
	USAJOBS HistoricJoa) — never prefetched, never bundled. Query mapping and
	month filling are pure helpers in ./areaTrend.ts (unit-tested there).

	Honesty contract:
	  • The caption states exactly which slice the bars reflect, and every
	    approximation (locality→primary-state fallback, ignored extra chips)
	    is listed — never silently dropped.
	  • Upstream failure renders an explicit "trend unavailable" message,
	    never fabricated bars.
	  • When the live area/filters drift from the loaded slice, the component
	    shows a "filters changed" notice with a reload button instead of
	    auto-refetching (load stays proportional to user intent) or silently
	    presenting a stale slice as current.

	No $effect reads+writes mapState here (WebKit state_unsafe_mutation rule):
	all writes are to component-local $state inside event handlers.
-->
<script lang="ts">
	import { mapState } from './store.svelte';
	import { buildAreaTrendQuery, fillMonths, TREND_WINDOW } from './areaTrend';
	import type { ResolvedArea } from './areaCard';
	import type { HistoryPayload } from './jobHistory';
	import InfoTooltip from './InfoTooltip.svelte';

	let { area }: { area: ResolvedArea } = $props();

	let opened = $state(false);
	let loading = $state(false);
	let payload = $state<HistoryPayload | null>(null);
	let error = $state<string | null>(null);
	// Snapshot of the slice the current payload was loaded for — compared
	// against the live `built.key` to detect staleness.
	let loadedKey = $state<string | null>(null);
	let loadedDescription = $state('');
	let loadedNotes = $state<string[]>([]);

	const built = $derived(buildAreaTrendQuery(area, mapState.filters));
	const stale = $derived(payload !== null && loadedKey !== null && loadedKey !== built.key);

	const bars = $derived(
		payload && payload.status === 'ok'
			? fillMonths(payload.monthly, payload.start_date, payload.end_date)
			: []
	);
	const maxCount = $derived(Math.max(1, ...bars.map((b) => b.count)));

	async function load() {
		// Capture the slice up front so a filter edit mid-flight can't mislabel
		// the payload that lands.
		const snapshot = built;
		loading = true;
		error = null;
		const q = snapshot.query;
		const params = new URLSearchParams();
		if (q.agencyCode) params.set('agency_code', q.agencyCode);
		if (q.series) params.set('series', q.series);
		if (q.grade) params.set('grade', q.grade);
		if (q.state) params.set('state', q.state);
		params.set('window', TREND_WINDOW);
		try {
			const response = await fetch(`/api/job-history?${params.toString()}`, {
				headers: { Accept: 'application/json' }
			});
			if (!response.ok) throw new Error(`history endpoint returned ${response.status}`);
			payload = (await response.json()) as HistoryPayload;
			loadedKey = snapshot.key;
			loadedDescription = snapshot.description;
			loadedNotes = snapshot.notes;
		} catch (err) {
			payload = null;
			loadedKey = null;
			error = err instanceof Error ? err.message : 'history endpoint unreachable';
		} finally {
			loading = false;
		}
	}

	function toggle() {
		opened = !opened;
		if (opened && !payload && !loading) load();
	}

	function shortMonth(month: string): string {
		const [y, m] = month.split('-');
		const idx = Number(m);
		if (!Number.isFinite(idx) || idx < 1 || idx > 12) return month;
		const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
		return `${labels[idx - 1]} '${y.slice(-2)}`;
	}
</script>

<section class="trend">
	<button type="button" class="toggle" onclick={toggle} aria-expanded={opened}>
		<span class="caret" aria-hidden="true">{opened ? '▾' : '▸'}</span>
		<span>12-month posting trend</span>
		<span class="hint">{opened ? 'collapse' : 'click to load'}</span>
	</button>

	{#if opened}
		<div class="body">
			{#if loading}
				<p class="note">Loading HistoricJoa…</p>
			{:else if error}
				<p class="error">Trend unavailable: {error}. Try again in a few minutes.</p>
			{:else if payload && payload.status !== 'ok'}
				<p class="error">
					Trend unavailable right now ({payload.error ?? 'upstream error'}).
					Try again after about an hour.
				</p>
			{:else if payload}
				<p class="slice">
					Postings opened per month · <strong>{loadedDescription}</strong>
					<InfoTooltip title="Where this trend comes from" align="end">
						<span>Monthly counts of HistoricJoa postings opened in the trailing year, loaded on demand through an edge-cached Pages Function (ADR-0029). Never prefetched; cached 24 h.</span>
						<span class="src">Source: USAJOBS /api/historicjoa (public, no key required)</span>
					</InfoTooltip>
				</p>
				{#each loadedNotes as note (note)}
					<p class="approx">≈ {note}</p>
				{/each}

				{#if stale}
					<div class="stale">
						<span>Filters changed since this trend loaded.</span>
						<button type="button" onclick={() => load()}>Reload</button>
					</div>
				{/if}

				<div class="summary">
					<span><strong>{payload.total.toLocaleString()}</strong> postings</span>
					<span class="dim">{payload.start_date} → {payload.end_date}</span>
					{#if payload.truncated}
						<span class="trunc" title="Result was capped at the upstream page limit; monthly counts are a floor, not an exact total.">truncated</span>
					{/if}
				</div>

				{#if bars.length > 0 && payload.total > 0}
					<div class="spark" role="img" aria-label="Monthly posting counts, trailing 12 months">
						{#each bars as bucket (bucket.month)}
							<div
								class="bar"
								style="--h: {Math.round((bucket.count / maxCount) * 100)}%"
								title={`${bucket.month}: ${bucket.count.toLocaleString()} postings`}
							>
								<span class="bar-fill"></span>
							</div>
						{/each}
					</div>
					<div class="axis">
						<span>{shortMonth(bars[0].month)}</span>
						<span>{shortMonth(bars[bars.length - 1].month)}</span>
					</div>
				{:else}
					<p class="note">No postings in the trailing year matched this slice.</p>
				{/if}
			{/if}
		</div>
	{/if}
</section>

<style>
	.trend {
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
	.summary {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: baseline;
		margin: 0 0 0.25rem;
		font-size: 11px;
		color: var(--c-text-2, #cfd9e6);
	}
	.summary strong {
		color: var(--c-text, #e5edf5);
		font-weight: 700;
	}
	.dim {
		color: var(--c-muted, #94a3b8);
	}
	.trunc {
		color: var(--c-warn, #f0c878);
		border: 1px solid #b48a3a;
		padding: 0.02rem 0.3rem;
		border-radius: 999px;
		font-size: 9px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.spark {
		display: flex;
		align-items: flex-end;
		gap: 2px;
		height: 38px;
		padding: 0.2rem 0;
		border-bottom: 1px solid var(--c-border, #2a3a52);
	}
	.bar {
		flex: 1 1 0;
		min-width: 3px;
		height: 100%;
		display: flex;
		align-items: flex-end;
	}
	.bar-fill {
		display: block;
		width: 100%;
		height: var(--h, 0%);
		min-height: 1px;
		background: var(--c-accent, #7bd0f2);
		border-radius: 2px 2px 0 0;
		opacity: 0.85;
		transition: opacity 120ms ease;
	}
	.bar:hover .bar-fill {
		opacity: 1;
		background: var(--c-accent-strong, #a8e0f5);
	}
	.axis {
		display: flex;
		justify-content: space-between;
		font-size: 9.5px;
		color: var(--c-muted, #94a3b8);
		margin-top: 0.15rem;
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
