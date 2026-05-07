<script lang="ts">
	import { METRIC_ORDER, METRICS } from './metrics';
	import { mapState } from './store.svelte';

	function selectMetric(key: typeof METRIC_ORDER[number]) {
		mapState.metric = key;
	}
</script>

<div class="switcher" role="radiogroup" aria-label="Choropleth metric">
	<div class="title">Color states by</div>
	<div class="buttons">
		{#each METRIC_ORDER as key (key)}
			{@const metric = METRICS[key]}
			{@const active = mapState.metric === key}
			<button
				type="button"
				role="radio"
				aria-checked={active}
				class="pill"
				class:active
				title={metric.description}
				onclick={() => selectMetric(key)}
			>
				{metric.short}
			</button>
		{/each}
	</div>
	<div class="caption">
		{METRICS[mapState.metric].description}
		<span class="src">Source: {METRICS[mapState.metric].source}</span>
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
	.title {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #94a3b8;
		margin-bottom: 0.5rem;
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
	.caption {
		margin-top: 0.55rem;
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
</style>
