// Basemap selection.
//
// If VITE_MAPBOX_TOKEN is set, use Mapbox's hosted style for the active theme.
// Otherwise fall back to an inline style with OpenStreetMap raster tiles so
// the dev server works out of the box without sign-up.
//
// Invariants enforced here (D.5.8 OSM-fallback hardening, per CLAUDE.md
// public-map V1.5 invariant #11):
// - The OSM fallback styles must NOT reference Mapbox `glyphs:` URLs (which
//   require an access token to fetch fonts). All glyph-dependent layers
//   (symbol/text) are omitted from the fallback styles.
// - Mapbox telemetry (`mapboxgl.config.SEND_EVENTS`) is forced off in both
//   token and no-token modes — the public map does not relay user events to
//   Mapbox. Privacy is the default.
// - OSM raster tiles are served from rotating subdomains (a/b/c) so the
//   browser opens parallel HTTP/2 connections and a single hung subdomain
//   cannot starve the basemap.
//
// `assertBasemapInvariants()` re-checks these at runtime and is exported for
// the unit test (`basemap.test.ts`) and the dev-mode self-check in
// `Map.svelte`.

const MAPBOX_TOKEN = (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined) ?? '';

export const HAS_MAPBOX_TOKEN = MAPBOX_TOKEN.length > 0;

export const MAPBOX_DARK_STYLE = 'mapbox://styles/mapbox/dark-v11';
export const MAPBOX_LIGHT_STYLE = 'mapbox://styles/mapbox/light-v11';

const OSM_TILE_URLS = [
	'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
	'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
	'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'
];

const OSM_ATTRIBUTION = '© OpenStreetMap contributors';

export const OSM_FALLBACK_STYLE: object = {
	version: 8,
	name: 'osm-fallback',
	// No `glyphs:` key — this style intentionally has zero text/symbol layers
	// so it never tries to fetch Mapbox-hosted fonts.
	sources: {
		osm: {
			type: 'raster',
			tiles: OSM_TILE_URLS,
			tileSize: 256,
			attribution: OSM_ATTRIBUTION,
			maxzoom: 19
		}
	},
	layers: [
		{
			id: 'background',
			type: 'background',
			paint: { 'background-color': '#0a0f1a' }
		},
		{
			id: 'osm',
			type: 'raster',
			source: 'osm',
			paint: {
				'raster-opacity': 0.45,
				'raster-saturation': -0.6,
				'raster-contrast': -0.1,
				'raster-brightness-max': 0.8
			}
		}
	]
};

export const OSM_LIGHT_FALLBACK_STYLE: object = {
	version: 8,
	name: 'osm-light-fallback',
	sources: {
		osm: {
			type: 'raster',
			tiles: OSM_TILE_URLS,
			tileSize: 256,
			attribution: OSM_ATTRIBUTION,
			maxzoom: 19
		}
	},
	layers: [
		{
			id: 'background',
			type: 'background',
			paint: { 'background-color': '#e8ecf1' }
		},
		{
			id: 'osm',
			type: 'raster',
			source: 'osm',
			paint: {
				'raster-opacity': 0.75,
				'raster-saturation': -0.2,
				'raster-contrast': 0.05
			}
		}
	]
};

export function pickStyle(): string | object {
	return HAS_MAPBOX_TOKEN ? MAPBOX_DARK_STYLE : OSM_FALLBACK_STYLE;
}

export function pickStyleForTheme(theme: 'light' | 'dark'): string | object {
	if (theme === 'light') {
		return HAS_MAPBOX_TOKEN ? MAPBOX_LIGHT_STYLE : OSM_LIGHT_FALLBACK_STYLE;
	}
	return HAS_MAPBOX_TOKEN ? MAPBOX_DARK_STYLE : OSM_FALLBACK_STYLE;
}

export function mapboxToken(): string {
	return MAPBOX_TOKEN;
}

export function configureMapboxRuntime(mapboxgl: unknown): void {
	const runtime = mapboxgl as {
		accessToken?: string;
		config?: {
			SEND_EVENTS?: boolean;
			REQUIRE_ACCESS_TOKEN?: boolean;
		};
	};

	// A non-empty placeholder is required even on the OSM path because
	// mapbox-gl will throw `An API access token is required` during construction
	// otherwise. The OSM fallback style itself never hits Mapbox's API so the
	// placeholder is never sent over the wire.
	runtime.accessToken = HAS_MAPBOX_TOKEN ? MAPBOX_TOKEN : 'pk.placeholder';

	if (runtime.config) {
		// Telemetry off in both modes. We do not want to relay user events to
		// Mapbox even when the operator has supplied their own token.
		runtime.config.SEND_EVENTS = false;

		if (!HAS_MAPBOX_TOKEN) {
			// Lets mapbox-gl proceed past the access-token guard so the OSM
			// fallback can render without sign-up.
			runtime.config.REQUIRE_ACCESS_TOKEN = false;
		}
	}
}

/**
 * Walks an inline style object and asserts the OSM-fallback hardening
 * invariants. Throws on the first violation. Used by the unit test and the
 * dev-mode self-check; callers in production should not throw at runtime, so
 * Map.svelte only invokes this in dev.
 */
export function assertBasemapInvariants(style: unknown): void {
	if (typeof style === 'string') {
		// Mapbox-hosted styles are opaque from our side; nothing to assert.
		return;
	}
	const s = style as {
		glyphs?: unknown;
		sources?: Record<string, { tiles?: unknown; type?: unknown }>;
		layers?: Array<{ type?: unknown }>;
	};
	if (s.glyphs !== undefined) {
		throw new Error(
			'basemap invariant violated: OSM fallback style declares `glyphs:` — would require Mapbox auth.'
		);
	}
	const layers = Array.isArray(s.layers) ? s.layers : [];
	for (const layer of layers) {
		if (layer?.type === 'symbol') {
			throw new Error(
				'basemap invariant violated: OSM fallback style declares a `symbol` layer; symbol layers need glyphs and would require Mapbox auth.'
			);
		}
	}
	const osm = s.sources?.osm;
	if (!osm || osm.type !== 'raster' || !Array.isArray(osm.tiles)) {
		throw new Error('basemap invariant violated: missing raster osm source with tile URL list.');
	}
	const tiles = osm.tiles as string[];
	if (tiles.length < 2) {
		throw new Error(
			'basemap invariant violated: OSM source must rotate across at least two tile subdomains.'
		);
	}
}
