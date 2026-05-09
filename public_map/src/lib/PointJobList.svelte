<script lang="ts">
	import { loadJobDetailsIndex, type JobDetails } from './data';
	import { gradeRange, propString, salaryRange } from './format';
	import { LAYER_IDS } from './layers';
	import { mapState, type JobStackView } from './store.svelte';

	let { stack }: { stack: JobStackView } = $props();
	let details = $state<Record<string, JobDetails>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		loading = true;
		loadJobDetailsIndex()
			.then((idx) => {
				details = idx;
			})
			.catch((err) => {
				error = (err as Error).message;
			})
			.finally(() => {
				loading = false;
			});
	});

	function detailFor(props: Record<string, unknown>): JobDetails | undefined {
		return details[String(props.id ?? '')];
	}

	function openJob(index: number) {
		const item = stack.items[index];
		if (!item) return;
		mapState.jobStack = { ...stack, selectedIndex: index };
		mapState.selectedFeature = {
			source: LAYER_IDS.markers,
			label: 'Job card',
			properties: item.properties
		};
	}
</script>

<section class="point-list">
	<p class="eyebrow">Postings at this point</p>
	<h2>{stack.label}</h2>
	<p class="count">{stack.items.length.toLocaleString()} posting{stack.items.length === 1 ? '' : 's'} share this map point.</p>

	{#if error}
		<p class="error">{error}</p>
	{:else}
		<ul aria-busy={loading}>
			{#each stack.items as item, i (String(item.properties.id ?? i))}
				{@const props = item.properties}
				{@const detail = detailFor(props)}
				<li>
					<button type="button" class="row" onclick={() => openJob(i)}>
						<span class="title">{detail?.title ?? propString(props, 'title', 'Loading…')}</span>
						<span class="agency">{String(detail?.agency ?? props.agency_code ?? 'Agency unknown')}</span>
						<span class="dept">{String(detail?.department ?? 'Department unknown')}</span>
						<span class="meta">
							{gradeRange(detail?.pay_plan ?? props.pay_plan, detail?.grade_low ?? props.grade_low, detail?.grade_high ?? props.grade_high)}
							<span>Series {String(detail?.series ?? props.series ?? '-')}</span>
						</span>
						<span class="meta">
							{salaryRange(detail?.salary_min ?? props.salary_min, detail?.salary_max ?? props.salary_max, detail?.salary_type)}
							<span>{String(detail?.remote_status ?? props.remote_status ?? 'Remote unknown')}</span>
						</span>
						<span class="meta">
							<span>Closes {String(detail?.close_date ?? props.close_date ?? '-')}</span>
							<span>{propString(props, 'city')} {propString(props, 'state', '')}</span>
							<span>Locality {propString(props, 'locality_code')}</span>
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.point-list {
		display: flex;
		flex-direction: column;
		min-height: 0;
	}
	.eyebrow {
		margin: 0 0 0.25rem;
		color: #7bd0f2;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	h2 {
		margin: 0;
		font-size: 18px;
		line-height: 1.2;
	}
	.count,
	.error {
		margin: 0.35rem 0 0.55rem;
		color: #94a3b8;
		font-size: 11px;
	}
	.error {
		color: #f1bcbc;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.4rem;
	}
	.row {
		appearance: none;
		width: 100%;
		border: 1px solid #22344c;
		border-radius: 6px;
		background: rgba(20, 32, 50, 0.55);
		color: inherit;
		cursor: pointer;
		display: grid;
		gap: 0.2rem;
		padding: 0.55rem 0.65rem;
		text-align: left;
		transition: border-color 120ms ease, background 120ms ease;
	}
	.row:hover {
		border-color: #4979b3;
		background: rgba(28, 42, 64, 0.85);
	}
	.row:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
	}
	.title {
		color: #e5edf5;
		font-size: 12.5px;
		font-weight: 700;
		line-height: 1.3;
	}
	.agency {
		color: #cfd9e6;
		font-size: 11px;
		font-weight: 600;
	}
	.dept {
		color: #94a3b8;
		font-size: 10.5px;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem 0.55rem;
		color: #94a3b8;
		font-size: 10.5px;
	}
</style>
