<script lang="ts">
	import { METRIC_ORDER, METRICS, formatMetricValue } from './metrics';
	import { mapState } from './store.svelte';

	function selectMetric(key: typeof METRIC_ORDER[number]) {
		// Click the already-active metric → toggle shading off.
		// Click any other metric → switch to it AND re-enable shading.
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

	function gradientCss(key: typeof METRIC_ORDER[number]): string {
		return METRICS[key].colorStops.map(([, color]) => color).join(', ');
	}

	function scaleLabels(key: typeof METRIC_ORDER[number]): [string, string, string] {
		const stops = METRICS[key].colorStops;
		const metric = METRICS[key];
		const lo = formatMetricValue(metric, stops[0][0]);
		const mid = formatMetricValue(metric, stops[Math.floor(stops.length / 2)][0]);
		const hi = formatMetricValue(metric, stops[stops.length - 1][0]);
		return [lo, mid, hi];
	}
</script>

<div class="switcher" role="radiogroup" aria-label="Choropleth metric">
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
	</div>
	<div class="buttons">
		{#each METRIC_ORDER as key (key)}
			{@const metric = METRICS[key]}
			{@const active = mapState.metric === key && mapState.choroplethEnabled}
			<button
				type="button"
				role="radio"
				aria-checked={active}
				class="pill"
				class:active
				title={mapState.metric === key && !mapState.choroplethEnabled
					? `${metric.description} (click to turn shading on)`
					: mapState.metric === key
						? `${metric.description} (click again to turn shading off)`
						: metric.description}
				onclick={() => selectMetric(key)}
			>
				{metric.short}
			</button>
		{/each}
	</div>
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
</div>

<style>
	.switcher {
		position: absolute;
		top: 1rem;
		left: 1rem;
		max-width: 26rem;
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
		justify-content: space-between;
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
	.pill:focus-visible {
		outline: 2px solid #7bd0f2;
		outline-offset: 2px;
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
			top: 7.5rem;
			left: 0.5rem;
			right: 0.5rem;
			max-width: none;
		}
		.legend,
		.caption {
			display: none;
		}
	}
</style>
