<script lang="ts">
	import { loadJobDetails, loadPayTables, type JobDetails, type PayTables } from './data';
	import { gradeRange, money, propString, salaryRange } from './format';

	let { properties }: { properties: Record<string, unknown> } = $props();
	let detail = $state<JobDetails | null>(null);
	let payTables = $state<PayTables | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	const isClosed = $derived(String(properties.status ?? detail?.status ?? '').toLowerCase() === 'closed');

	$effect(() => {
		const id = String(properties.id ?? '');
		if (!id) return;
		loading = true;
		error = null;
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
		<dt>Agency</dt><dd>{String(detail?.agency ?? properties.agency_code ?? '—')}</dd>
		<dt>Department</dt><dd>{String(detail?.department ?? '—')}</dd>
		<dt>Series/grade</dt><dd>{gradeRange(detail?.pay_plan ?? properties.pay_plan, detail?.grade_low ?? properties.grade_low, detail?.grade_high ?? properties.grade_high)} · {String(detail?.series ?? properties.series ?? '—')}</dd>
		<dt>Salary</dt><dd>{salaryRange(detail?.salary_min ?? properties.salary_min, detail?.salary_max ?? properties.salary_max, detail?.salary_type)}</dd>
		<dt>Remote</dt><dd>{String(detail?.remote_status ?? properties.remote_status ?? '—')}</dd>
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
	.eyebrow { margin: 0 0 0.25rem; color: #7bd0f2; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
	h2 { margin: 0 0 0.75rem; font-size: 20px; line-height: 1.15; }
	.apply-btn { display: block; text-align: center; color: #06111f; background: #7bd0f2; border-radius: 6px; padding: 0.55rem 0.7rem; font-weight: 700; text-decoration: none; margin-bottom: 0.75rem; transition: background 120ms ease; }
	.apply-btn:hover { background: #a8e0f5; }
	.grid { display: grid; grid-template-columns: max-content 1fr; gap: 0.45rem 0.8rem; margin: 0; }
	dt { color: #94a3b8; }
	dd { margin: 0; font-weight: 600; }
	h3 { margin: 0.9rem 0 0.4rem; font-size: 13px; color: #e5edf5; }
	ul { margin: 0; padding-left: 1.1rem; color: #cfd9e6; }
	table { width: 100%; border-collapse: collapse; font-size: 12px; }
	th, td { padding: 0.35rem 0.2rem; border-bottom: 1px solid #2a3a52; }
	th { text-align: left; color: #94a3b8; font-weight: 500; }
	td { text-align: right; font-weight: 700; }
	.note, .error { margin: 0.8rem 0 0; font-size: 12px; line-height: 1.45; color: #94a3b8; }
	.closed-note { margin: 0 0 0.75rem; padding: 0.55rem 0.65rem; border: 1px solid #3a4556; border-radius: 6px; background: rgba(135, 146, 163, 0.14); color: #cfd9e6; line-height: 1.45; }
	.error { color: #f1bcbc; }
</style>
