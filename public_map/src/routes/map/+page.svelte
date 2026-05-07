<script lang="ts">
	import Map from '$lib/Map.svelte';
	import MetricSwitcher from '$lib/MetricSwitcher.svelte';
	import FeaturePanel from '$lib/FeaturePanel.svelte';
	import { mapState } from '$lib/store.svelte';
</script>

<svelte:head>
	<title>The Grand Pipeline — Federal Job Map</title>
</svelte:head>

<div class="root">
	<header class="masthead">
		<div class="brand">
			<span class="logo" aria-hidden="true"></span>
			<div>
				<h1>The Grand Pipeline</h1>
				<p class="tagline">Federal jobs, by paycheck and place</p>
			</div>
		</div>
		{#if mapState.manifest}
			<div class="manifest">
				<span>Reference year {mapState.manifest.reference_year}</span>
				<span>{mapState.manifest.job_count.toLocaleString()} open postings</span>
				<span>Updated {new Date(mapState.manifest.generated_at).toLocaleDateString()}</span>
			</div>
		{/if}
	</header>

	<Map />
	<MetricSwitcher />
	<FeaturePanel />

	<footer class="attrib">
		<span>Data: USAJOBS · OPM · U.S. Census · BEA</span>
		<span>Not affiliated with the U.S. government</span>
	</footer>
</div>

<style>
	.root {
		position: fixed;
		inset: 0;
		overflow: hidden;
	}
	.masthead {
		position: absolute;
		top: 1rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 4;
		display: flex;
		gap: 1.25rem;
		align-items: center;
		padding: 0.55rem 0.95rem;
		background: rgba(14, 23, 38, 0.85);
		border: 1px solid #2a3a52;
		border-radius: 999px;
		backdrop-filter: blur(8px);
		pointer-events: none;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.logo {
		display: inline-block;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: radial-gradient(circle at 30% 30%, #7bd0f2, #2c5b8a 70%);
		box-shadow: 0 0 12px rgba(123, 208, 242, 0.5);
	}
	h1 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		letter-spacing: 0.01em;
	}
	.tagline {
		margin: 0;
		font-size: 11px;
		color: #94a3b8;
	}
	.manifest {
		display: flex;
		gap: 0.9rem;
		font-size: 11px;
		color: #cfd9e6;
		border-left: 1px solid #2a3a52;
		padding-left: 1rem;
	}
	.manifest span {
		white-space: nowrap;
	}
	.attrib {
		position: absolute;
		bottom: 0.4rem;
		right: 0.6rem;
		display: flex;
		gap: 0.9rem;
		font-size: 10px;
		color: #64748b;
		pointer-events: none;
		z-index: 4;
	}

	@media (max-width: 640px) {
		.masthead {
			flex-direction: column;
			gap: 0.4rem;
			align-items: flex-start;
			border-radius: 8px;
			top: 0.5rem;
		}
		.manifest {
			border-left: none;
			padding-left: 0;
			flex-wrap: wrap;
		}
	}
</style>
