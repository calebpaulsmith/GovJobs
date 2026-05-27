<svelte:head>
	<title>About — FedFinder Federal Job Map</title>
	<meta
		name="description"
		content="About FedFinder: a free, read-only map of open USAJOBS postings, OPM workforce data, locality-adjusted federal pay, and cost of living. Its data sources, precision limits, privacy posture, and government-affiliation disclaimer."
	/>
	<link rel="canonical" href="https://map.thegrandpipeline.com/about" />
	<meta property="og:title" content="About FedFinder — Federal Job Map" />
	<meta property="og:url" content="https://map.thegrandpipeline.com/about" />
</svelte:head>

<main class="about-shell">
	<a class="back" href="/browse">← Back to FedFinder</a>

	<section class="hero">
		<p class="eyebrow">About the map</p>
		<h1>FedFinder</h1>
		<p class="lede">
			A free, read-only map of open USAJOBS postings, federal workforce context, locality-adjusted
			federal pay, and cost-of-living measures. It exists to answer one practical question for
			federal job seekers: <em>where does a federal paycheck go furthest?</em>
		</p>
	</section>

	<section class="card">
		<h2>What the map shows</h2>
		<ul>
			<li><strong>Open postings</strong> from USAJOBS announcement data.</li>
			<li>
				<strong>Federal workforce counts, accessions, and separations</strong> from OPM data —
				always labeled separately from postings, because a posting is not a hire.
			</li>
			<li><strong>Locality-adjusted pay</strong> from OPM GS pay tables and locality definitions.</li>
			<li><strong>Cost of living</strong> from BEA Regional Price Parities and Census ACS rents.</li>
			<li><strong>Federal buildings</strong> from the GSA Federal Real Property Profile (FRPP).</li>
			<li>
				<strong>State, county, metro (CBSA), and locality boundaries</strong> from Census and
				OPM-compatible reference data.
			</li>
		</ul>
	</section>

	<section class="card warning">
		<h2>Precision and limits</h2>
		<p>
			<strong>A posting is not a hire.</strong> Posting layers describe advertised announcements;
			workforce overlays describe OPM employment, accessions, or separations. The two are never
			combined into a single count.
		</p>
		<p>
			<strong>Marker positions reflect the posting's stated location, not a verified address.</strong>
			USAJOBS usually identifies a city, state, remote status, or broader duty area rather than a
			street address. Markers can be panned to street level for orientation, but a pin marks the
			location the announcement gave — not a confirmed building or desk.
		</p>
		<p>
			<strong>Pay accuracy varies by pay system.</strong> GS-family postings get a full
			locality-adjusted grade-and-step table; other pay plans (Federal Wage System, Title 38, SES,
			broadband demos, and others) show the posting's own salary range instead. The pay-vs-cost-of-living
			shading uses a GS-13 step 1 reference and applies to GS-family jobs only — it is labeled as such
			in the legend.
		</p>
		<p>
			<strong>Always verify on the canonical USAJOBS announcement before applying.</strong> The bundle
			is refreshed on a schedule, so a posting may have closed since the last export.
		</p>
	</section>

	<section class="card">
		<h2>Your data stays in your browser</h2>
		<p>
			FedFinder has no accounts and no server-side profile. Jobs you view, save, or hide, plus your
			saved searches and light/dark preference, are stored only in your own browser (local storage)
			and never sent anywhere. Clearing your browser data resets them.
		</p>
	</section>

	<section class="card">
		<h2>Data sources and attributions</h2>
		<ul>
			<li><strong>USAJOBS</strong> — open federal job announcement data.</li>
			<li>
				<strong>U.S. Office of Personnel Management (OPM)</strong> — GS pay tables, locality
				definitions, and workforce/accessions/separations data.
			</li>
			<li>
				<strong>U.S. Census Bureau</strong> — TIGER/Line state, county, and CBSA geography; ACS
				median-rent estimates; ZCTA centroids for ZIP search.
			</li>
			<li>
				<strong>U.S. Bureau of Economic Analysis (BEA)</strong> — Regional Price Parities for
				cost-of-living context.
			</li>
			<li><strong>U.S. General Services Administration (GSA)</strong> — Federal Real Property Profile.</li>
			<li>
				<strong>Mapbox</strong> (when a token is configured) or <strong>OpenStreetMap</strong> raster
				tiles as the no-token fallback basemap.
			</li>
		</ul>
	</section>

	<section class="card disclaimer">
		<h2>Government affiliation</h2>
		<p>
			FedFinder is an independent project. It is <strong>not</strong> affiliated with, endorsed by, or
			sponsored by the U.S. government, USAJOBS, OPM, the U.S. Census Bureau, BEA, GSA, Mapbox, or
			OpenStreetMap. All federal data is reproduced from public sources; verify posting details on the
			official USAJOBS announcement before relying on them.
		</p>
	</section>

	<footer class="about-foot">
		<a class="back" href="/browse">← Back to FedFinder</a>
	</footer>
</main>

<style>
	.about-shell {
		min-height: 100vh;
		max-width: 880px;
		margin: 0 auto;
		padding: 2rem 1rem 4rem;
		line-height: 1.6;
		color: var(--c-text, #e5edf5);
	}
	.back {
		display: inline-flex;
		align-items: center;
		font-size: 13px;
		font-weight: 600;
		text-decoration: none;
		color: var(--c-accent, #7bd0f2);
	}
	.back:hover {
		text-decoration: underline;
	}
	.hero {
		margin-top: 1.5rem;
	}
	.hero,
	.card {
		background: var(--c-panel, rgba(14, 23, 38, 0.88));
		border: 1px solid var(--c-border, #2a3a52);
		border-radius: 16px;
		padding: clamp(1rem, 2.4vw, 1.5rem);
		box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
	}
	.card {
		margin-top: 1rem;
	}
	.eyebrow {
		margin: 0 0 0.25rem;
		color: var(--c-accent, #7bd0f2);
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
		font-size: clamp(2rem, 5vw, 3.2rem);
		line-height: 1;
	}
	h2 {
		margin-bottom: 0.55rem;
		font-size: 1.2rem;
		color: var(--c-text, #e5edf5);
	}
	.lede {
		max-width: 64ch;
		margin-bottom: 0;
		color: var(--c-text-2, #cfd9e6);
		font-size: 1.05rem;
	}
	ul {
		margin: 0;
		padding-left: 1.2rem;
		color: var(--c-text-2, #cfd9e6);
	}
	li + li {
		margin-top: 0.4rem;
	}
	.card p {
		color: var(--c-text-2, #cfd9e6);
	}
	.card p + p {
		margin-top: 0.7rem;
	}
	.card p:last-child {
		margin-bottom: 0;
	}
	.warning {
		border-color: var(--c-warn-border, #e0a030);
	}
	.disclaimer {
		border-color: var(--c-accent-dim, #4979b3);
	}
	.about-foot {
		margin-top: 1.5rem;
	}
</style>
