<script lang="ts">
	import { untrack } from 'svelte';
	import { loadJobDetails, loadPayTables, type JobDetails, type PayGrid, type PayTables } from './data';
	import { gradeRange, money, propString, salaryRange, urgencyBadge } from './format';
	import InfoTooltip from './InfoTooltip.svelte';
	import { jobProfile } from './jobProfile.svelte';
	import { mapState } from './store.svelte';
	import PostingIntelligence from './PostingIntelligence.svelte';
	import QuickAdd from './QuickAdd.svelte';

	let { properties }: { properties: Record<string, unknown> } = $props();
	let detail = $state<JobDetails | null>(null);
	let payTables = $state<PayTables | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	const isClosed = $derived(String(properties.status ?? detail?.status ?? '').toLowerCase() === 'closed');
	const urgency = $derived(isClosed ? { text: '', level: null } : urgencyBadge(String(detail?.close_date ?? properties.close_date ?? '')));
	const jobId = $derived(String(properties.id ?? ''));
	const saved = $derived(jobProfile.isSaved(jobId));
	const hidden = $derived(jobProfile.isHidden(jobId));

	// Mark viewed when the card mounts AND every time `jobId` changes
	// (e.g. user taps a different marker while a card is already open).
	// `markViewed` writes to `jobProfile.data.viewed` and `saveToStorage`
	// then JSON.stringifies the whole proxy, so any read of `data` from
	// within the effect would be tracked — producing a `state_unsafe_mutation`
	// bailout that freezes the component and makes it stop re-rendering
	// on the next `properties` prop change. That bailout is the most
	// plausible cause of the operator's "tap a different feature, sheet
	// stays on the first one" report on iOS Safari. `untrack` keeps the
	// write side-effect outside the effect's dependency graph.
	$effect(() => {
		const id = jobId;
		if (id) untrack(() => jobProfile.markViewed(id));
	});

	function toggleSave() {
		if (!jobId) return;
		if (saved) {
			jobProfile.unsaveJob(jobId);
		} else {
			jobProfile.saveJob(jobId, {
				title: String(detail?.title ?? properties.title ?? jobId),
				agency: String(detail?.agency ?? properties.agency_code ?? ''),
				close_date: String(detail?.close_date ?? properties.close_date ?? '') || null,
				url: String(detail?.url ?? properties.url ?? '') || null
			});
		}
		mapState.savedJobIds = jobProfile.savedJobs.reduce((s, j) => { s.add(j.id); return s; }, new Set<string>());
	}

	function toggleHide() {
		if (!jobId) return;
		if (hidden) {
			jobProfile.unhideJob(jobId);
		} else {
			jobProfile.hideJob(jobId);
			// Close the card after hiding.
			mapState.selectedFeature = null;
			mapState.jobStack = null;
		}
		mapState.hiddenJobIds = jobProfile.hiddenIds;
	}

	$effect(() => {
		const id = String(properties.id ?? '');
		if (!id) return;
		loading = true;
		error = null;
		detail = null;
		Promise.all([loadJobDetails(id), loadPayTables()])
			.then(([job, tables]) => {
				detail = job;
				payTables = tables;
			})
			.catch((err) => {
				error = (err as Error).message;
			})
			.finally(() => {
				loading = false;
			});
	});

	// Per D.5.11 the exporter pre-computes a per-job pay_grid with a status
	// flag (exact / approximated / unavailable). The local payTables.json
	// snapshot is used only as a backstop when the snapshot was produced
	// before D.5.11 shipped (older bundles have no detail.pay_grid).
	type PayLookup = {
		plan: string;
		year: string | undefined;
		locality: string;
		fallbackToBase: boolean;
		grade: string;
	};

	function payLookup(job: JobDetails | null): PayLookup {
		const plan = String(job?.pay_plan ?? properties.pay_plan ?? 'GS');
		const year = job?.pay_grid?.year
			? String(job.pay_grid.year)
			: payTables
				? Object.keys(payTables[plan] ?? {}).sort().at(-1)
				: undefined;
		const locality = String(
			job?.pay_grid?.locality?.code ?? job?.locality_code ?? properties.locality_code ?? 'BASE'
		) || 'BASE';
		const grade = String(job?.grade_low ?? properties.grade_low ?? '');
		const byYear = year && payTables ? payTables[plan]?.[year] : undefined;
		const fallbackToBase = locality !== 'BASE' && !byYear?.[locality] && Boolean(byYear?.BASE);
		return { plan, year, locality, fallbackToBase, grade };
	}

	function gridFromDetail(grid: PayGrid | null | undefined, gradeKey: string): [string, string][] {
		if (!grid?.grades) return [];
		const padded = gradeKey.padStart(2, '0');
		const steps = grid.grades[padded] ?? grid.grades[gradeKey];
		if (!steps) return [];
		return Object.entries(steps)
			.sort(([a], [b]) => Number(a) - Number(b))
			.map(([step, rate]) => [`Step ${Number(step)}`, money(rate)]);
	}

	function fallbackTableRows(job: JobDetails | null): [string, string][] {
		const { plan, year, locality, grade } = payLookup(job);
		if (!payTables || !year) return [];
		const byYear = payTables[plan]?.[year];
		const localityTable = byYear?.[locality] ?? byYear?.BASE;
		const steps = localityTable?.[grade.padStart(2, '0')] ?? localityTable?.[grade];
		if (!steps) return [];
		return Object.entries(steps)
			.sort(([a], [b]) => Number(a) - Number(b))
			.map(([step, rate]) => [`Step ${Number(step)}`, money(rate)]);
	}

	function tableRows(job: JobDetails | null): [string, string][] {
		const grade = String(job?.grade_low ?? properties.grade_low ?? '');
		const fromGrid = gridFromDetail(job?.pay_grid, grade);
		if (fromGrid.length) return fromGrid;
		return fallbackTableRows(job);
	}

	function payStatus(job: JobDetails | null): 'exact' | 'approximated' | 'unavailable' | 'snapshot' {
		const status = job?.pay_grid?.status;
		if (status === 'exact' || status === 'approximated' || status === 'unavailable') {
			return status;
		}
		// Older bundle without pay_grid; treat as snapshot-driven (no provenance).
		return fallbackTableRows(job).length ? 'snapshot' : 'unavailable';
	}
</script>

<section>
	<p class="eyebrow">{isClosed ? 'Closed posting' : 'Open posting'}</p>
	<h2>{detail?.title ?? propString(properties, 'title', 'Loading…')}</h2>
	{#if urgency.level}
		<div class="urgency-badge urgency-{urgency.level}" role="status">{urgency.text}</div>
	{/if}
	<div class="profile-actions">
		<button type="button" class="profile-btn" class:active={saved} onclick={toggleSave}>
			{saved ? '★ Saved' : '☆ Save'}
		</button>
		<button type="button" class="profile-btn danger" onclick={toggleHide}>
			{hidden ? 'Unhide' : 'Hide'}
		</button>
	</div>
	{#if !isClosed && (detail?.url ?? properties.url)}
		<a class="apply-btn" href={String(detail?.url ?? properties.url)} target="_blank" rel="noreferrer noopener">
			Apply on USAJOBS &rarr;
		</a>
	{:else if isClosed}
		<p class="closed-note">
			Closed on {String(detail?.close_date ?? properties.close_date ?? 'unknown date')} — shown for trailing-90-day context, not an active application.
		</p>
	{/if}
	<dl class="grid">
		<dt>Agency</dt>
		<dd>
			<QuickAdd
				type="agency"
				value={String(detail?.agency_code ?? properties.agency_code ?? '')}
				label={String(detail?.agency ?? properties.agency_code ?? '—')}
			/>
		</dd>
		<dt>Department</dt><dd>{String(detail?.department ?? '—')}</dd>
		<dt>Pay plan</dt>
		<dd>
			<QuickAdd type="payPlan" value={String(detail?.pay_plan ?? properties.pay_plan ?? '')} />
		</dd>
		<dt>Series</dt>
		<dd>
			<QuickAdd type="series" value={String(detail?.series ?? properties.series ?? '')} />
		</dd>
		<dt>Grade</dt>
		<dd>
			<QuickAdd
				type="grade"
				value={String(detail?.grade_low ?? properties.grade_low ?? '')}
				label={gradeRange(detail?.pay_plan ?? properties.pay_plan, detail?.grade_low ?? properties.grade_low, detail?.grade_high ?? properties.grade_high)}
			/>
		</dd>
		<dt>Salary</dt><dd>{salaryRange(detail?.salary_min ?? properties.salary_min, detail?.salary_max ?? properties.salary_max, detail?.salary_type)}</dd>
		<dt>Remote</dt><dd>{String(detail?.remote_status ?? properties.remote_status ?? '—')}</dd>
		{#if detail?.hiring_paths}
			<dt>Hiring path</dt>
			<dd>
				<QuickAdd type="hiringPath" value={String(detail.hiring_paths)} />
			</dd>
		{/if}
		<dt>Close date</dt><dd>{String(detail?.close_date ?? properties.close_date ?? '—')}</dd>
		<dt>Clicked location</dt><dd>{propString(properties, 'city')} {propString(properties, 'state', '')}</dd>
		<dt>Locality code</dt><dd>{propString(properties, 'locality_code')}</dd>
	</dl>

	{#if loading}
		<p class="note">Loading job detail and pay table…</p>
	{:else if error}
		<p class="error">{error}</p>
	{:else if detail}
		{#if detail.locations?.length}
			<h3>All source locations</h3>
			<ul>
				{#each detail.locations as loc, i (i)}
					<li>{loc.location_text ?? [loc.city, loc.state].filter(Boolean).join(', ')}</li>
				{/each}
			</ul>
		{/if}
		{@const lookup = payLookup(detail)}
		{@const status = payStatus(detail)}
		{@const rows = tableRows(detail)}
		{#if rows.length && status !== 'unavailable'}
			<h3>
				Locality-adjusted pay table
				{#if status === 'exact'}
					<span class="pay-status pay-status-exact" title="Exact: locality-specific OPM rows used.">exact</span>
				{:else if status === 'approximated'}
					<span class="pay-status pay-status-approx" title="Approximated: derived from base × locality % because no locality-specific row exists for this combination.">approximated</span>
				{:else if status === 'snapshot'}
					<span class="pay-status pay-status-snap" title="Older bundle without per-job provenance — verify in admin.">snapshot</span>
				{/if}
				<InfoTooltip title="How this table was built" align="end">
					<span>Step rates for this posting's pay plan, grade, and locality. Source year is the most recent year present in the bundled pay scale.</span>
					<span class="formula">step_rate = base_step × (1 + locality_pct ÷ 100)</span>
					<span class="formula">plan = {lookup.plan} • year = {detail?.pay_grid?.year ?? lookup.year ?? '—'} • locality = {detail?.pay_grid?.locality?.code ?? lookup.locality}{lookup.fallbackToBase ? ' (fell back to BASE)' : ''} • grade = {lookup.grade || '—'}{detail?.pay_grid?.locality?.adjustment_pct != null ? ` • locality_pct = ${detail.pay_grid.locality.adjustment_pct}%` : ''}</span>
					<span class="src">Source: pay_scales × locality_pay_areas (pre-computed at export time per D.5.11)</span>
				</InfoTooltip>
			</h3>
			<table>
				<tbody>
					{#each rows as [step, rate] (step)}
						<tr><th>{step}</th><td>{rate}</td></tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<h3>Pay table</h3>
			<p class="note pay-missing" role="status">
				Pay scale not yet ingested for plan {lookup.plan} / locality {detail?.pay_grid?.locality?.code ?? lookup.locality} / grade {lookup.grade || '—'} (year {detail?.pay_grid?.year ?? lookup.year ?? '—'}).
				{#if detail?.pay_grid?.missing_reason}<br /><span class="missing-reason">{detail.pay_grid.missing_reason}</span>{/if}
				<br />
				<a class="admin-link" href="/?admin=pay" target="_blank" rel="noreferrer noopener" title="Opens the local Streamlit admin page if you have it running.">Refresh pay scales in Public Map Admin →</a>
				<InfoTooltip title="Why no pay table?" align="end">
					<span>The bundled snapshot does not contain rows for this (plan, year, grade). The Public Map Admin page (pages/11_Public_Map_Admin.py) refreshes OPM pay scales for the active reference year, then re-runs the export.</span>
					<span class="src">Source: pay_scales (last refreshed via scripts/ingest_gs_pay.py / ingest_locality_pay.py)</span>
				</InfoTooltip>
			</p>
		{/if}
	{/if}

	<PostingIntelligence jobProperties={properties} />
</section>

<style>
	.eyebrow { margin: 0 0 0.25rem; color: var(--c-accent, #7bd0f2); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	h2 { margin: 0 0 0.5rem; font-size: 20px; line-height: 1.15; color: var(--c-text, #e5edf5); }
	.urgency-badge { display: inline-block; margin: 0 0 0.5rem; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
	.urgency-critical { background: rgba(220, 80, 80, 0.18); border: 1px solid #dc5050; color: var(--c-danger, #f7a0a0); }
	.urgency-soon { background: rgba(220, 160, 50, 0.18); border: 1px solid #e0a030; color: var(--c-warn, #f0c878); }
	.profile-actions { display: flex; gap: 0.4rem; margin: 0 0 0.6rem; flex-wrap: wrap; }
	.profile-btn { appearance: none; border: 1px solid var(--c-border-input, #2c4870); background: var(--c-row-bg, rgba(28,42,64,0.4)); color: var(--c-text-2, #cfd9e6); padding: 0.22rem 0.65rem; border-radius: 999px; font-size: 12px; cursor: pointer; transition: all 120ms ease; }
	.profile-btn:hover { border-color: var(--c-accent, #7bd0f2); color: var(--c-accent, #7bd0f2); }
	.profile-btn.active { background: var(--c-accent-dim, #4979b3); border-color: var(--c-accent, #7bd0f2); color: #fff; }
	.profile-btn.danger { border-color: var(--c-danger-border, #6b2020); color: var(--c-danger, #f7a0a0); }
	.profile-btn.danger:hover { border-color: var(--c-danger, #dc5050); }
	.apply-btn { display: block; text-align: center; color: var(--c-apply-text, #06111f); background: var(--c-apply-bg, #7bd0f2); border-radius: 6px; padding: 0.55rem 0.7rem; font-weight: 700; text-decoration: none; margin-bottom: 0.75rem; transition: background 120ms ease; }
	.apply-btn:hover { background: var(--c-apply-hover, #a8e0f5); }
	.grid { display: grid; grid-template-columns: max-content 1fr; gap: 0.45rem 0.8rem; margin: 0; }
	dt { color: var(--c-muted, #94a3b8); }
	dd { margin: 0; font-weight: 600; color: var(--c-text-2, #cfd9e6); }
	h3 { margin: 0.9rem 0 0.4rem; font-size: 13px; color: var(--c-text, #e5edf5); }
	ul { margin: 0; padding-left: 1.1rem; color: var(--c-text-2, #cfd9e6); }
	table { width: 100%; border-collapse: collapse; font-size: 12px; }
	th, td { padding: 0.35rem 0.2rem; border-bottom: 1px solid var(--c-border, #2a3a52); }
	th { text-align: left; color: var(--c-muted, #94a3b8); font-weight: 500; }
	td { text-align: right; font-weight: 700; color: var(--c-text, #e5edf5); }
	.note, .error { margin: 0.8rem 0 0; font-size: 12px; line-height: 1.45; color: var(--c-muted, #94a3b8); }
	.pay-status { display: inline-block; margin-left: 0.4rem; padding: 0.05rem 0.45rem; border-radius: 999px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; vertical-align: middle; }
	.pay-status-exact { background: rgba(80, 180, 120, 0.18); border: 1px solid #4f9f6a; color: var(--c-success, #9be0b4); }
	.pay-status-approx { background: rgba(220, 160, 50, 0.18); border: 1px solid #b48a3a; color: var(--c-warn, #f0c878); }
	.pay-status-snap { background: rgba(140, 140, 160, 0.16); border: 1px solid #6a6a82; color: var(--c-muted, #94a3b8); }
	.pay-missing { padding: 0.55rem 0.65rem; border: 1px dashed var(--c-border, #4a5a72); border-radius: 6px; }
	.missing-reason { display: inline-block; margin-top: 0.15rem; color: var(--c-muted, #94a3b8); font-style: italic; }
	.admin-link { display: inline-block; margin-top: 0.3rem; color: var(--c-accent, #7bd0f2); text-decoration: none; font-weight: 600; }
	.admin-link:hover { text-decoration: underline; }
	.closed-note { margin: 0 0 0.75rem; padding: 0.55rem 0.65rem; border: 1px solid var(--c-border, #3a4556); border-radius: 6px; background: var(--c-row-bg, rgba(135,146,163,0.14)); color: var(--c-text-2, #cfd9e6); line-height: 1.45; }
	.error { color: var(--c-danger, #f1bcbc); }
</style>
