<script lang="ts">
	import { loadJobDetails, loadPayTables, type JobDetails, type PayTables } from './data';
	import { gradeRange, money, propString, salaryRange, urgencyBadge } from './format';
	import { jobProfile } from './jobProfile.svelte';
	import { mapState } from './store.svelte';
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

	// Mark viewed when the card loads.
	$effect(() => {
		if (jobId) jobProfile.markViewed(jobId);
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

	function tableRows(job: JobDetails | null): [string, string][] {
		if (!job || !payTables) return [];
		const plan = String(job.pay_plan ?? properties.pay_plan ?? 'GS');
		const year = Object.keys(payTables[plan] ?? {}).sort().at(-1);
		const locality = String(job.locality_code ?? properties.locality_code ?? 'BASE') || 'BASE';
		const grade = String(job.grade_low ?? properties.grade_low ?? '');
		const byYear = year ? payTables[plan]?.[year] : undefined;
		const localityTable = byYear?.[locality] ?? byYear?.BASE;
		const steps = localityTable?.[grade];
		if (!steps) return [];
		return Object.entries(steps)
			.sort(([a], [b]) => Number(a) - Number(b))
			.map(([step, rate]) => [`Step ${step}`, money(rate)]);
	}
</script>

<section>
	<p class="eyebrow">{isClosed ? 'Closed posting' : 'Open posting'}</p>
	<h2>{propString(properties, 'title')}</h2>
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
		{#if tableRows(detail).length}
			<h3>Locality-adjusted pay table</h3>
			<table>
				<tbody>
					{#each tableRows(detail) as [step, rate] (step)}
						<tr><th>{step}</th><td>{rate}</td></tr>
					{/each}
				</tbody>
			</table>
		{:else}
			<p class="note">No matching static pay-table row is available for this posting's plan/locality/grade.</p>
		{/if}
	{/if}
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
	.closed-note { margin: 0 0 0.75rem; padding: 0.55rem 0.65rem; border: 1px solid var(--c-border, #3a4556); border-radius: 6px; background: var(--c-row-bg, rgba(135,146,163,0.14)); color: var(--c-text-2, #cfd9e6); line-height: 1.45; }
	.error { color: var(--c-danger, #f1bcbc); }
</style>
