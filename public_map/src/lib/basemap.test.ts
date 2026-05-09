// D.5.8 — basemap unit test.
//
// Validates the OSM-fallback hardening invariants documented in `basemap.ts`
// and CLAUDE.md public-map V1.5 invariant #11:
//   - Inline OSM styles never declare `glyphs:` (would require Mapbox auth).
//   - Inline OSM styles never declare a `symbol` layer (needs glyphs).
//   - The OSM tile source rotates across at least two subdomains.
//   - `configureMapboxRuntime` always disables `SEND_EVENTS`.
//   - Without a token, `REQUIRE_ACCESS_TOKEN` is also disabled.
//   - With a token, `REQUIRE_ACCESS_TOKEN` is left untouched.

import { describe, expect, it } from 'vitest';
import {
	OSM_FALLBACK_STYLE,
	OSM_LIGHT_FALLBACK_STYLE,
	assertBasemapInvariants,
	configureMapboxRuntime,
	pickStyleForTheme
} from './basemap';

describe('OSM fallback styles', () => {
	it('declare neither glyphs: nor symbol layers', () => {
		for (const style of [OSM_FALLBACK_STYLE, OSM_LIGHT_FALLBACK_STYLE]) {
			expect(() => assertBasemapInvariants(style)).not.toThrow();
		}
	});

	it('rotate across multiple OSM subdomains', () => {
		const dark = OSM_FALLBACK_STYLE as { sources: { osm: { tiles: string[] } } };
		const light = OSM_LIGHT_FALLBACK_STYLE as { sources: { osm: { tiles: string[] } } };
		expect(dark.sources.osm.tiles.length).toBeGreaterThanOrEqual(3);
		expect(light.sources.osm.tiles.length).toBeGreaterThanOrEqual(3);
		// Subdomains must actually differ.
		const hosts = new Set(dark.sources.osm.tiles.map((t) => new URL(t).host));
		expect(hosts.size).toBeGreaterThanOrEqual(3);
	});

	it('rejects styles that reintroduce a glyphs URL', () => {
		const bad = {
			version: 8,
			glyphs: 'mapbox://fonts/mapbox/{fontstack}/{range}.pbf',
			sources: {
				osm: {
					type: 'raster',
					tiles: ['https://a.example/{z}/{x}/{y}.png', 'https://b.example/{z}/{x}/{y}.png']
				}
			},
			layers: []
		};
		expect(() => assertBasemapInvariants(bad)).toThrow(/glyphs/);
	});

	it('rejects styles that reintroduce a symbol layer', () => {
		const bad = {
			version: 8,
			sources: {
				osm: {
					type: 'raster',
					tiles: ['https://a.example/{z}/{x}/{y}.png', 'https://b.example/{z}/{x}/{y}.png']
				}
			},
			layers: [{ id: 'labels', type: 'symbol' }]
		};
		expect(() => assertBasemapInvariants(bad)).toThrow(/symbol/);
	});

	it('rejects styles whose OSM source has only one subdomain', () => {
		const bad = {
			version: 8,
			sources: {
				osm: { type: 'raster', tiles: ['https://only.example/{z}/{x}/{y}.png'] }
			},
			layers: []
		};
		expect(() => assertBasemapInvariants(bad)).toThrow(/subdomain/);
	});
});

describe('configureMapboxRuntime', () => {
	it('disables SEND_EVENTS regardless of token presence', () => {
		const fake = { config: { SEND_EVENTS: true, REQUIRE_ACCESS_TOKEN: true }, accessToken: '' };
		configureMapboxRuntime(fake);
		expect(fake.config.SEND_EVENTS).toBe(false);
		// Placeholder access token must be set so mapbox-gl construction does
		// not throw. The OSM fallback never sends it over the wire.
		expect(fake.accessToken.length).toBeGreaterThan(0);
	});

	it('drops REQUIRE_ACCESS_TOKEN when no Mapbox token is present', () => {
		// `import.meta.env.VITE_MAPBOX_TOKEN` is unset in the test environment,
		// so HAS_MAPBOX_TOKEN is false and the function should disable the
		// access-token guard.
		const fake = { config: { SEND_EVENTS: true, REQUIRE_ACCESS_TOKEN: true } } as {
			config: { SEND_EVENTS: boolean; REQUIRE_ACCESS_TOKEN: boolean };
			accessToken?: string;
		};
		configureMapboxRuntime(fake);
		expect(fake.config.REQUIRE_ACCESS_TOKEN).toBe(false);
	});
});

describe('pickStyleForTheme', () => {
	it('returns inline OSM styles when no token is configured', () => {
		// No VITE_MAPBOX_TOKEN in the test env → both themes resolve to objects,
		// not Mapbox `mapbox://` URL strings.
		expect(typeof pickStyleForTheme('dark')).toBe('object');
		expect(typeof pickStyleForTheme('light')).toBe('object');
	});
});
