<!--
	Filtered list of job postings inside a polygon scope (state, locality,
	county, CBSA). Honors the active filter chips (mapState.filters) so what
	the user sees here matches what's plotted on the map. Clicking a row
	switches the FeaturePanel into JobCard mode for that posting.
-->
<script lang="ts">
	import { mapState, type ListView } from './store.svelte';
	import { loadJobs, loadJobDetailsIndex, type Feature, type JobDetails } from './data';
	import { filterJobs } from './filters';
	import { LAYER_IDS } from './layers';
	import { gradeRange, money, propString, salaryRange } from './format';

	let { listView }: { listView: ListView } = $props();
	let allJobs = $state<{ type: 'FeatureCollection'; features: Feature[] } | null>(null);
	let details = $state<Record<string, JobDetails>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		loading = true;
		Promise.all([loadJobs(), loadJobDetailsIndex()])
			.then(([jobs, idx]) => {
				allJobs = jobs;
				details = idx;
			})
			.catch((err) => (error = (err as Error).message))
			.finally(() => (loading = false));
	});

	function inScope(feature: Feature): boolean {
		const props = feature.properties ?? {};
		switch (listView.scope) {
			case 'state':
				return String(props.state ?? '').toUpperCase() === listView.code.toUpperCase();
			case 'locality':
				return String(props.locality_code ?? '').toUpperCase() === listView.code.toUpperCase();
			case 'county':
				return String(details[String(props.id ?? '')]?.locations?.[0]?.state ?? '') === listView.code;
			case 'cbsa':
				// No CBSA tag on markers yet — fall back to "no match" until D.5 wires it.
				return false;
			default:
				return false;
		}
	}

	const visible = $derived.by(() => {
		if (!allJobs) return [] as Feature[];
		const filtered = filterJobs(allJobs, mapState.filters, details);
		return filtered.features.filter(inScope);
	});

	function pickJob(feature: Feature) {
		// Promote the clicked row to a JobCard view in the same panel.
		mapState.selectedFeature = {
			source: LAYER_IDS.markers,
			label: 'Job card',
			properties: feature.properties ?? {}
		};
		mapState.listView = null;
	}

	function backToRoundup() {
		mapState.listView = null;
	}
</script>

<section class="job-list">
	<div class="header">
		<button type="button" class="back" onclick={backToRoundup} aria-label="Back to roundup">
			← Back
		</button>
		<div>
			<p class="eyebrow">Postings in scope</p>
			<h3>{listView.label}</h3>
		</div>
	</div>

	{#if loading}
		<p class="note">Loading postings…</p>
	{:else if error}
		<p class="error">{error}</p>
	{:else if visible.length === 0}
		<p class="note">No postings match the current filters in {listView.label}. Adjust your filter chips and try again.</p>
	{:else}
		<p class="count">{visible.length.toLocaleString()} posting{visible.length === 1 ? '' : 's'} match the current filters.</p>
		<ul>
			{#each visible as feature, i (feature.properties?.id ?? i)}
				{@const props = feature.properties ?? {}}
				<li>
					<button type="button" class="row" onclick={() => pickJob(feature)}>
						<div class="row-title">{propString(props, 'title')}</div>
						<div class="row-meta">
							<span>{gradeRange(props.pay_plan, props.grade_low, props.grade_high)}</span>
							<span>·</span>
							<span>{propString(props, 'agency_code')}</span>
							<span>·</span>
							<span>{propString(props, 'city')}, {propString(props, 'state', '')}</span>
						</div>
						<div class="row-salary">{salaryRange(props.salary_min, props.salary_max, undefined)}</div>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.job-list {
		display: flex;
		flex-direction: column;
		min-height: 0;
	}
	.header {
		display: flex;
		gap: 0.6rem;
		align-items: flex-start;
		margin-bottom: 0.6rem;
	}
	.back {
		appearance: none;
		border: 1px solid #2c4870;
		background: rgba(28, 42, 64, 0.4);
		color: #cfd9e6;
		padding: 0.25rem 0.55rem;
		border-radius: 999px;
		cursor: pointer;
		font-size: 11px;
	}
	.back:hover {
		border-color: #7bd0f2;
		color: #7bd0f2;
	}
	.eyebrow {
		margin: 0;
		color: #7bd0f2;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	h3 {
		margin: 0.1rem 0 0;
		font-size: 14px;
		line-height: 1.2;
	}
	.note,
	.error {
		margin: 0.5rem 0;
		font-size: 12px;
		line-height: 1.45;
		color: #94a3b8;
	}
	.error {
		color: #f1bcbc;
	}
	.count {
		margin: 0 0 0.5rem;
		font-size: 11px;
		color: #94a3b8;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.row {
		display: block;
		width: 100%;
		text-align: left;
		appearance: none;
		background: rgba(20, 32, 50, 0.55);
		border: 1px solid #22344c;
		border-radius: 6px;
		padding: 0.5rem 0.65rem;
		color: inherit;
		cursor: pointer;
		transition: border-color 120ms ease, background 120ms ease;
	}
	.row:hover {
		border-color: #4979b3;
		background: rgba(28, 42, 64, 0.85);
	}
	.row-title {
		font-weight: 600;
		font-size: 12.5px;
		color: #e5edf5;
		line-height: 1.3;
	}
	.row-meta {
		margin-top: 0.2rem;
		display: flex;
		gap: 0.35rem;
		flex-wrap: wrap;
		color: #94a3b8;
		font-size: 11px;
	}
	.row-salary {
		margin-top: 0.2rem;
		color: #7bd0f2;
		font-size: 11px;
		font-weight: 600;
	}
</style>
