<script lang="ts">
	import { METRIC_ORDER, METRICS, formatMetricValue, type MetricKey, type MetricStatus } from './metrics';
	import { LAYOUT_SLOTS, slotAttr } from './layout';
	import { mapState } from './store.svelte';

	function effectiveStatus(key: MetricKey): MetricStatus {
		if (mapState.demotedMetrics.has(key)) return 'wip';
		return METRICS[key].status;
	}

	function isVisible(key: MetricKey): boolean {
		const st = effectiveStatus(key);
		if (st === 'under-construction') return mapState.showExperimentalMetrics;
		return true;
	}

	function selectMetric(key: MetricKey) {
		const st = effectiveStatus(key);
		// wip metrics can be selected (pill clickable) but choropleth stays off.
		if (st === 'wip') {
			mapState.metric = key;
			mapState.choroplethEnabled = false;
			return;
		}
		// Click the already-active ready metric → toggle shading off.
		if (key === mapState.metric && mapState.choroplethEnabled) {
			mapState.choroplethEnabled = false;
			return;
		}
		mapState.metric = key;
		mapState.choroplethEnabled = true;
	}

	function toggleShading() {
		mapState.choroplethEnabled = !mapState.choroplethEnabled;
	}

	function toggleHeat() {
		mapState.postingHeatEnabled = !mapState.postingHeatEnabled;
	}

	function toggleClosedJobs() {
		mapState.closedJobsEnabled = !mapState.closedJobsEnabled;
	}

	function gradientCss(key: MetricKey): string {
		return METRICS[key].colorStops.map(([, color]) => color).join(', ');
	}

	function scaleLabels(key: MetricKey): [string, string, string] {
		const stops = METRICS[key].colorStops;
		const metric = METRICS[key];
		const lo = formatMetricValue(metric, stops[0][0]);
		const mid = formatMetricValue(metric, stops[Math.floor(stops.length / 2)][0]);
		const hi = formatMetricValue(metric, stops[stops.length - 1][0]);
		return [lo, mid, hi];
	}

	const hasExperimentalMetrics = METRIC_ORDER.some((k) => METRICS[k].status === 'under-construction');
	const activeIsWip = $derived(effectiveStatus(mapState.metric) === 'wip');
</script>

<div
	class="switcher"
	role="radiogroup"
	aria-label="Choropleth metric"
	data-layout-slot={slotAttr(LAYOUT_SLOTS.metric)}
>
	<div class="title-row">
		<div class="title">Color states by</div>
		<button
			type="button"
			class="shade-toggle"
			class:on={mapState.choroplethEnabled}
			onclick={toggleShading}
			aria-pressed={mapState.choroplethEnabled}
			title={mapState.choroplethEnabled
				? 'Shading is on — click to turn off'
				: 'Shading is off — click to turn on'}
		>
			Shade {mapState.choroplethEnabled ? 'on' : 'off'}
		</button>
		<button
			type="button"
			class="shade-toggle"
			class:on={mapState.postingHeatEnabled}
			onclick={toggleHeat}
			aria-pressed={mapState.postingHeatEnabled}
			title={mapState.postingHeatEnabled ? 'Posting heat is on' : 'Posting heat is off'}
		>
			Heat {mapState.postingHeatEnabled ? 'on' : 'off'}
		</button>
		<button
			type="button"
			class="shade-toggle"
			class:on={mapState.closedJobsEnabled}
			onclick={toggleClosedJobs}
			aria-pressed={mapState.closedJobsEnabled}
			title={mapState.closedJobsEnabled
				? 'Trailing-90-day closed postings are on'
				: 'Trailing-90-day closed postings are off'}
		>
			Closed {mapState.closedJobsEnabled ? 'on' : 'off'}
		</button>
		{#if hasExperimentalMetrics}
			<button
				type="button"
				class="shade-toggle"
				class:on={mapState.showExperimentalMetrics}
				onclick={() => (mapState.showExperimentalMetrics = !mapState.showExperimentalMetrics)}
				aria-pressed={mapState.showExperimentalMetrics}
				title="Show or hide experimental (under-construction) metrics"
			>
				Experimental {mapState.showExperimentalMetrics ? 'on' : 'off'}
			</button>
		{/if}
	</div>
	<div class="buttons">
		{#each METRIC_ORDER as key (key)}
			{@const metric = METRICS[key]}
			{@const st = effectiveStatus(key)}
			{@const active = mapState.metric === key && mapState.choroplethEnabled && st === 'ready'}
			{#if isVisible(key)}
				<button
					type="button"
					role="radio"
					aria-checked={active}
					class="pill"
					class:active
					class:wip={st === 'wip'}
					class:experimental={st === 'under-construction'}
					title={st === 'wip'
						? `${metric.label} — no data yet (${metric.wipNote ?? 'data not available'})`
						: st === 'under-construction'
							? `${metric.label} — experimental feature`
							: mapState.metric === key && !mapState.choroplethEnabled
								? `${metric.description} (click to turn shading on)`
								: mapState.metric === key
									? `${metric.description} (click again to turn shading off)`
									: metric.description}
					onclick={() => selectMetric(key)}
				>
					{metric.short}
					{#if st === 'wip'}<span class="badge">no data</span>{/if}
					{#if st === 'under-construction'}<span class="badge">beta</span>{/if}
				</button>
			{/if}
		{/each}
	</div>

	{#if activeIsWip}
		<div class="wip-legend" role="status">
			<div class="wip-stripe" aria-hidden="true"></div>
			<p class="wip-note">
				{METRICS[mapState.metric].wipNote ?? 'No comparable data yet for this metric.'}
				Shading is disabled; markers and filters still work.
			</p>
		</div>
	{:else}
		<div class="legend" class:dim={!mapState.choroplethEnabled}>
			<div
				class="gradient"
				style="background: linear-gradient(to right, {gradientCss(mapState.metric)})"
				role="presentation"
			></div>
			<div class="scale">
				{#each scaleLabels(mapState.metric) as label, i (i)}
					<span>{label}</span>
				{/each}
			</div>
		</div>
		<div class="caption">
			{#if mapState.choroplethEnabled}
				{METRICS[mapState.metric].description}
				<span class="src">Source: {METRICS[mapState.metric].source}</span>
			{:else}
				Choropleth shading is off. Markers and polygon outlines still respond to filters; click any pill above to re-enable shading.
			{/if}
		</div>
	{/if}
</div>

<style>
	.switcher {
		position: absolute;
		bottom: 1rem;
		left: 1rem;
		right: 1rem;
		max-width: 26rem;
		margin: 0 auto;
		padding: 0.75rem 0.9rem;
		background: rgba(14, 23, 38, 0.92);
		border: 1px solid #2a3a52;
		border-radius: 8px;
		backdrop-filter: blur(8px);
		box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
		z-index: 5;
	}
	.title-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}
	.title {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #94a3b8;
	}
	.shade-toggle {
		appearance: none;
		border: 1px solid #2c4870;
		background: rgba(28, 42, 64, 0.4);
		color: #94a3b8;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
		cursor: pointer;
		transition: all 120ms ease;
	}
	.shade-toggle.on {
		background: #4979b3;
		border-color: #7bd0f2;
		color: #fff;
	}
	.shade-toggle:hover {
		border-color: #7bd0f2;
	}
	.legend.dim {
		opacity: 0.35;
		filter: grayscale(0.7);
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.pill {
		appearance: none;
		border: 1px solid #2c4870;
		background: rgba(28, 42, 64, 0.6);
		color: #cfd9e6;
		padding: 0.3rem 0.7rem;
		font-size: 12px;
		font-weight: 500;
		border-radius: 999px;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
	}
	.pill:hover {
		border-color: #4979b3;
		color: #e5edf5;
	}
	.pill.active {
		background: #4979b3;
		border-color: #7bd0f2;
		color: #fff;
	}
	.pill.wip {
		border-style: dashed;
		color: #94a3b8;
		cursor: pointer;
	}
	.pill.experimental {
		border-color: #5a3c7a;
		color: #b08de0;
	}
	.pill:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
	}
	.badge {
		font-size: 9px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.1rem 0.35rem;
		border-radius: 999px;
		background: rgba(100, 116, 139, 0.25);
		color: #94a3b8;
	}
	.wip-legend {
		margin-top: 0.6rem;
	}
	.wip-stripe {
		height: 8px;
		border-radius: 4px;
		width: 100%;
		background: repeating-linear-gradient(
			-45deg,
			#2a3a52 0px,
			#2a3a52 4px,
			#1a2535 4px,
			#1a2535 8px
		);
	}
	.wip-note {
		margin: 0.4rem 0 0;
		font-size: 11px;
		line-height: 1.5;
		color: #94a3b8;
	}
	.legend {
		margin-top: 0.6rem;
	}
	.gradient {
		height: 8px;
		border-radius: 4px;
		width: 100%;
	}
	.scale {
		display: flex;
		justify-content: space-between;
		margin-top: 3px;
		font-size: 10px;
		color: #64748b;
	}
	.caption {
		margin-top: 0.45rem;
		font-size: 11px;
		line-height: 1.5;
		color: #94a3b8;
	}
	.src {
		display: block;
		margin-top: 2px;
		color: #64748b;
		font-size: 10px;
	}
	@media (max-width: 640px) {
		.switcher {
			bottom: 0.5rem;
			left: 0.5rem;
			right: 0.5rem;
			max-width: none;
		}
		.legend,
		.caption,
		.wip-legend {
			display: none;
		}
	}
</style>
