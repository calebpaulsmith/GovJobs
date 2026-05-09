<script lang="ts">
	// D.5.24 — Posting Intelligence tab on JobCard.
	//
	// Click-to-load only (per ADR-0029). Window pills + filtered timeline +
	// drill-in list, all powered by `/api/job-history` (the Cloudflare Pages
	// Function defined in `public_map/functions/api/job-history.ts`). Reads
	// `mapState.filters` plus the host posting's identifying fields as the
	// single source of truth for the upstream query — no parallel filter UI.
	import { mapState } from './store.svelte';
	import {
		WINDOW_KEYS,
		WINDOW_LABELS,
		DEFAULT_WINDOW,
		type HistoryPayload,
		type WindowKey,
		type PostingHistoryQuery,
		type TrimmedRecord
	} from './jobHistory';
	import InfoTooltip from './InfoTooltip.svelte';
	import { money } from './format';

	let { jobProperties }: { jobProperties: Record<string, unknown> } = $props();

	let opened = $state(false);
	let loading = $state(false);
	let payload = $state<HistoryPayload | null>(null);
	let error = $state<string | null>(null);
	let window = $state<WindowKey>(DEFAULT_WINDOW);
	let listOpen = $state(false);
	let listPage = $state(0);
	const pageSize = 25;

	const totalRecords = $derived(payload?.records.length ?? 0);
	const pageCount = $derived(Math.max(1, Math.ceil(totalRecords / pageSize)));
	const visibleRecords = $derived(
		payload?.records.slice(listPage * pageSize, (listPage + 1) * pageSize) ?? []
	);
	const maxMonthlyCount = $derived(
		Math.max(1, ...(payload?.monthly ?? []).map((m) => m.count))
	);

	function buildQuery(): PostingHistoryQuery {
		const filters = mapState.filters;
		const agencyFromFilter = filters.agencies[0];
		const seriesFromFilter = filters.series.trim();
		const gradeFromFilter = filters.gradeMin.trim();
		const stateFromFilter = pickStateFromGeographies(filters.geographies);
		return {
			agencyCode:
				agencyFromFilter ?? (jobProperties.agency_code ? String(jobProperties.agency_code) : undefined),
			series:
				seriesFromFilter || (jobProperties.series ? String(jobProperties.series) : undefined),
			grade:
				gradeFromFilter || (jobProperties.grade_low ? String(jobProperties.grade_low) : undefined),
			state:
				stateFromFilter ?? (jobProperties.state ? String(jobProperties.state) : undefined)
		};
	}

	function pickStateFromGeographies(geos: string[]): string | undefined {
		for (const g of geos) {
			if (g.startsWith('state:')) return g.slice('state:'.length);
		}
		return undefined;
	}

	async function load(nextWindow: WindowKey = window) {
		loading = true;
		error = null;
		const query = buildQuery();
		const params = new URLSearchParams();
		if (query.agencyCode) params.set('agency_code', query.agencyCode);
		if (query.series) params.set('series', query.series);
		if (query.grade) params.set('grade', query.grade);
		if (query.state) params.set('state', query.state);
		if (query.controlNumber) params.set('position_id', query.controlNumber);
		params.set('window', nextWindow);
		try {
			const response = await fetch(`/api/job-history?${params.toString()}`, {
				headers: { Accept: 'application/json' }
			});
			if (!response.ok) {
				throw new Error(`history endpoint returned ${response.status}`);
			}
			const body = (await response.json()) as HistoryPayload;
			payload = body;
			window = body.window;
			listPage = 0;
		} catch (err) {
			payload = null;
			error = err instanceof Error ? err.message : 'history endpoint unreachable';
		} finally {
			loading = false;
		}
	}

	function toggle() {
		opened = !opened;
		if (opened && !payload && !loading) {
			load(window);
		}
	}

	function pickWindow(next: WindowKey) {
		window = next;
		load(next);
	}

	function describeQuery(): string {
		const q = buildQuery();
		const parts: string[] = [];
		if (q.agencyCode) parts.push(`agency ${q.agencyCode}`);
		if (q.series) parts.push(`series ${q.series}`);
		if (q.grade) parts.push(`grade ${q.grade}`);
		if (q.state) parts.push(`state ${q.state}`);
		return parts.length ? parts.join(' · ') : 'all federal';
	}

	function shortMonth(month: string): string {
		// month = YYYY-MM. Render as "Jan '25" so the timeline labels stay
		// narrow even with 10 years of buckets.
		const [y, m] = month.split('-');
		const idx = Number(m);
		if (!Number.isFinite(idx) || idx < 1 || idx > 12) return month;
		const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
		return `${labels[idx - 1]} '${y.slice(-2)}`;
	}

	function rowSalary(r: TrimmedRecord): string {
		if (r.salary_min == null && r.salary_max == null) return '—';
		if (r.salary_min != null && r.salary_max != null && r.salary_min !== r.salary_max) {
			return `${money(r.salary_min)} – ${money(r.salary_max)}`;
		}
		return money(r.salary_min ?? r.salary_max);
	}
</script>

<section class="intel">
	<button type="button" class="toggle" onclick={toggle} aria-expanded={opened}>
		<span class="caret" aria-hidden="true">{opened ? '▾' : '▸'}</span>
		<span>Posting Intelligence</span>
		<span class="hint">{opened ? 'collapse' : 'click to load'}</span>
	</button>

	{#if opened}
		<div class="body">
			<p class="filter-summary">
				Showing the trailing window of HistoricJoa postings matching:
				<strong>{describeQuery()}</strong>.
				<InfoTooltip title="What is Posting Intelligence?" align="end">
					<span>This panel calls a Cloudflare Pages Function (per ADR-0029) that proxies USAJOBS HistoricJoa with a 24-hour edge cache. It is loaded only when you open this section — never prefetched.</span>
					<span class="formula">filters = mapState.filters ∪ this posting's identifying fields</span>
					<span class="src">Source: USAJOBS /api/historicjoa (public, no key required)</span>
				</InfoTooltip>
			</p>

			<div class="window-pills" role="tablist" aria-label="Time window">
				{#each WINDOW_KEYS as key (key)}
					<button
						type="button"
						role="tab"
						aria-selected={window === key}
						class="pill"
						class:active={window === key}
						disabled={loading}
						onclick={() => pickWindow(key)}
					>
						{WINDOW_LABELS[key]}
					</button>
				{/each}
			</div>

			{#if loading}
				<p class="note">Loading HistoricJoa…</p>
			{:else if error}
				<p class="error">History unavailable: {error}. Try again in a few minutes.</p>
			{:else if payload && payload.status !== 'ok'}
				<p class="error">
					History unavailable right now ({payload.error ?? 'upstream error'}).
					Try again after about an hour.
				</p>
			{:else if payload}
				<div class="summary">
					<span><strong>{payload.total.toLocaleString()}</strong> matching postings</span>
					<span class="dim">{payload.start_date} → {payload.end_date}</span>
					{#if payload.truncated}
						<span class="trunc" title="Result was capped at the upstream page limit. Narrow your filters or pick a shorter window for a complete count.">truncated</span>
					{/if}
				</div>

				{#if payload.monthly.length > 0}
					<div class="timeline" role="img" aria-label="Monthly posting counts">
						{#each payload.monthly as bucket (bucket.month)}
							<div
								class="bar"
								style="--h: {Math.round((bucket.count / maxMonthlyCount) * 100)}%"
								title={`${bucket.month}: ${bucket.count.toLocaleString()} postings`}
							>
								<span class="bar-fill"></span>
							</div>
						{/each}
					</div>
					<div class="timeline-axis">
						<span>{shortMonth(payload.monthly[0].month)}</span>
						<span>{shortMonth(payload.monthly[payload.monthly.length - 1].month)}</span>
					</div>
				{:else}
					<p class="note">No postings in this window matched these filters.</p>
				{/if}

				{#if payload.records.length > 0}
					<button type="button" class="drill-toggle" onclick={() => (listOpen = !listOpen)}>
						{listOpen ? 'Hide' : 'See all'} {payload.records.length.toLocaleString()} matching historic postings
					</button>
					{#if listOpen}
						<ul class="drill-list">
							{#each visibleRecords as record, i (`${record.control_number ?? i}`)}
								<li>
									<div class="row-title">{record.title ?? '(untitled posting)'}</div>
									<div class="row-meta">
										<span>{record.agency_code ?? '—'}</span>
										<span>{record.series ?? '—'}</span>
										<span>{record.pay_plan ?? ''}{record.grade_low ?? ''}{record.grade_high && record.grade_high !== record.grade_low ? `–${record.grade_high}` : ''}</span>
										<span>{record.city ?? ''}{record.state ? `, ${record.state}` : ''}</span>
										<span class="dim">{record.open_date ?? ''}{record.close_date ? ` → ${record.close_date}` : ''}</span>
									</div>
									<div class="row-meta">
										<span>{rowSalary(record)}</span>
										<span class="dim">{record.hiring_path ?? ''}</span>
									</div>
								</li>
							{/each}
						</ul>
						{#if pageCount > 1}
							<div class="paginator">
								<button type="button" disabled={listPage === 0} onclick={() => (listPage = Math.max(0, listPage - 1))}>
									Prev
								</button>
								<span>Page {listPage + 1} / {pageCount}</span>
								<button
									type="button"
									disabled={listPage + 1 >= pageCount}
									onclick={() => (listPage = Math.min(pageCount - 1, listPage + 1))}
								>
									Next
								</button>
							</div>
						{/if}
					{/if}
				{/if}
			{/if}
		</div>
	{/if}
</section>

<style>
	.intel { margin-top: 0.9rem; border-top: 1px solid var(--c-border, #2a3a52); padding-top: 0.6rem; }
	.toggle { display: flex; gap: 0.4rem; align-items: center; width: 100%; appearance: none; border: none; background: transparent; color: var(--c-text-2, #cfd9e6); font: inherit; font-size: 13px; cursor: pointer; padding: 0.25rem 0; text-align: left; }
	.toggle:hover { color: var(--c-accent, #7bd0f2); }
	.caret { color: var(--c-accent, #7bd0f2); width: 0.8em; }
	.hint { margin-left: auto; color: var(--c-muted, #94a3b8); font-size: 11px; }
	.body { margin-top: 0.5rem; }
	.filter-summary { margin: 0 0 0.55rem; font-size: 11px; line-height: 1.45; color: var(--c-muted, #94a3b8); }
	.filter-summary strong { color: var(--c-text-2, #cfd9e6); font-weight: 600; }
	.window-pills { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.55rem; }
	.pill { appearance: none; border: 1px solid var(--c-border-input, #2c4870); background: var(--c-row-bg, rgba(28,42,64,0.4)); color: var(--c-text-2, #cfd9e6); padding: 0.2rem 0.55rem; border-radius: 999px; font-size: 11px; cursor: pointer; }
	.pill:hover:not([disabled]) { border-color: var(--c-accent, #7bd0f2); color: var(--c-accent, #7bd0f2); }
	.pill.active { background: var(--c-accent-dim, #4979b3); border-color: var(--c-accent, #7bd0f2); color: #fff; }
	.pill[disabled] { opacity: 0.5; cursor: progress; }
	.summary { display: flex; flex-wrap: wrap; gap: 0.55rem; align-items: baseline; margin: 0.45rem 0; font-size: 12px; color: var(--c-text-2, #cfd9e6); }
	.summary strong { color: var(--c-text, #e5edf5); font-weight: 700; }
	.dim { color: var(--c-muted, #94a3b8); }
	.trunc { color: var(--c-warn, #f0c878); border: 1px solid #b48a3a; padding: 0.05rem 0.35rem; border-radius: 999px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
	.timeline { display: flex; align-items: flex-end; gap: 1px; height: 56px; padding: 0.25rem 0; border-bottom: 1px solid var(--c-border, #2a3a52); }
	.bar { flex: 1 1 0; min-width: 2px; height: 100%; display: flex; align-items: flex-end; }
	.bar-fill { display: block; width: 100%; height: var(--h, 0%); background: var(--c-accent, #7bd0f2); border-radius: 2px 2px 0 0; opacity: 0.85; transition: opacity 120ms ease; }
	.bar:hover .bar-fill { opacity: 1; background: var(--c-accent-strong, #a8e0f5); }
	.timeline-axis { display: flex; justify-content: space-between; font-size: 10px; color: var(--c-muted, #94a3b8); margin-top: 0.2rem; }
	.drill-toggle { margin-top: 0.65rem; appearance: none; border: 1px dashed var(--c-border, #4a5a72); background: transparent; color: var(--c-accent, #7bd0f2); font: inherit; font-size: 12px; padding: 0.4rem 0.6rem; border-radius: 6px; cursor: pointer; width: 100%; text-align: left; }
	.drill-toggle:hover { border-color: var(--c-accent, #7bd0f2); }
	.drill-list { list-style: none; margin: 0.5rem 0 0; padding: 0; max-height: 320px; overflow-y: auto; }
	.drill-list li { padding: 0.45rem 0; border-bottom: 1px solid var(--c-border-subtle, #22344c); }
	.row-title { font-weight: 600; color: var(--c-text, #e5edf5); font-size: 12px; }
	.row-meta { display: flex; flex-wrap: wrap; gap: 0.5rem; font-size: 11px; color: var(--c-text-2, #cfd9e6); margin-top: 0.15rem; }
	.paginator { display: flex; gap: 0.5rem; align-items: center; justify-content: space-between; margin-top: 0.5rem; font-size: 11px; color: var(--c-muted, #94a3b8); }
	.paginator button { appearance: none; border: 1px solid var(--c-border-input, #2c4870); background: var(--c-row-bg, rgba(28,42,64,0.4)); color: var(--c-text-2, #cfd9e6); padding: 0.2rem 0.55rem; border-radius: 6px; font: inherit; font-size: 11px; cursor: pointer; }
	.paginator button[disabled] { opacity: 0.4; cursor: default; }
	.note { margin: 0.5rem 0 0; font-size: 12px; color: var(--c-muted, #94a3b8); }
	.error { margin: 0.5rem 0 0; font-size: 12px; color: var(--c-danger, #f1bcbc); }
	.formula { display: block; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; color: var(--c-text-2, #cfd9e6); margin-top: 0.2rem; }
	.src { display: block; margin-top: 0.3rem; font-size: 10px; color: var(--c-muted, #94a3b8); }
</style>
