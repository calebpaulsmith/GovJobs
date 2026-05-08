<svelte:head>
	<title>About — The Grand Pipeline Federal Job Map</title>
	<meta
		name="description"
		content="About The Grand Pipeline public federal job map, its sources, precision limits, and government-affiliation disclaimer."
	/>
</svelte:head>

<main class="about-shell">
	<a class="back" href="/map">← Back to map</a>

	<section class="hero">
		<p class="eyebrow">About the public map</p>
		<h1>The Grand Pipeline Federal Job Map</h1>
		<p class="lede">
			A read-only, public snapshot of open USAJOBS postings, OPM workforce context,
			locality-adjusted federal pay, and BEA cost-of-living measures. The goal is to
			answer a practical applicant question: where does a federal paycheck go furthest?
		</p>
	</section>

	<section class="card">
		<h2>What the map shows</h2>
		<ul>
			<li><strong>Open postings</strong> from USAJOBS announcement data exported by the local dashboard.</li>
			<li><strong>Federal workforce counts</strong>, accessions, and separations from OPM data, labeled separately from postings.</li>
			<li><strong>Locality pay context</strong> from OPM pay tables and locality definitions.</li>
			<li><strong>Cost-of-living context</strong> from BEA Regional Price Parities.</li>
			<li><strong>State, county, CBSA, and locality boundaries</strong> from Census and OPM-compatible reference data.</li>
		</ul>
	</section>

	<section class="card warning">
		<h2>Precision and limits</h2>
		<p>
			USAJOBS location data usually identifies a city, state, remote status, or broader duty area,
			not a street address. The map is intentionally capped at zoom 9 and should be read as a
			regional planning tool, not a parcel-level duty-station locator.
		</p>
		<p>
			A posting is not a hire. Workforce overlays describe OPM employment, accessions, or
			separations; posting layers describe advertised announcements.
		</p>
	</section>

	<section class="card">
		<h2>Data sources and attributions</h2>
		<ul>
			<li>USAJOBS announcement data for open federal postings.</li>
			<li>U.S. Office of Personnel Management (OPM) data for workforce and pay-table context.</li>
			<li>U.S. Census Bureau TIGER/Line geography for state, county, and CBSA boundaries.</li>
			<li>U.S. Bureau of Economic Analysis (BEA) Regional Price Parities for cost-of-living context.</li>
			<li>OpenStreetMap raster tiles as the no-token fallback basemap.</li>
			<li>SimpleMaps city reference data may be used locally to geocode city-level posting locations.</li>
		</ul>
	</section>

	<section class="card disclaimer">
		<h2>Government affiliation</h2>
		<p>
			The Grand Pipeline is not affiliated with, endorsed by, or sponsored by the U.S. government,
			USAJOBS, OPM, the U.S. Census Bureau, BEA, OpenStreetMap, or SimpleMaps. Always verify
			posting details on the canonical USAJOBS announcement before applying.
		</p>
	</section>
</main>

<style>
	.about-shell {
		min-height: 100vh;
		max-width: 880px;
		margin: 0 auto;
		padding: 2rem 1rem 4rem;
		line-height: 1.6;
	}
	.back {
		display: inline-flex;
		margin-bottom: 1.5rem;
		text-decoration: none;
	}
	.hero,
	.card {
		background: rgba(14, 23, 38, 0.88);
		border: 1px solid #2a3a52;
		border-radius: 16px;
		padding: clamp(1rem, 2.4vw, 1.5rem);
		box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
	}
	.card {
		margin-top: 1rem;
	}
	.eyebrow {
		margin: 0 0 0.25rem;
		color: #7bd0f2;
		font-size: 0.75rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	h1,
	h2,
	p {
		margin-top: 0;
	}
	h1 {
		margin-bottom: 0.75rem;
		font-size: clamp(2rem, 5vw, 3.4rem);
		line-height: 1;
	}
	h2 {
		margin-bottom: 0.55rem;
		font-size: 1.2rem;
	}
	.lede {
		max-width: 64ch;
		margin-bottom: 0;
		color: #cfd9e6;
		font-size: 1.05rem;
	}
	ul {
		margin: 0;
		padding-left: 1.2rem;
	}
	li + li {
		margin-top: 0.4rem;
	}
	.warning {
		border-color: #7b5e2d;
		background: rgba(48, 36, 18, 0.62);
	}
	.disclaimer {
		border-color: #315f78;
	}
	.card p:last-child {
		margin-bottom: 0;
	}
</style>
