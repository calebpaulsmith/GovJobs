// Basemap selection.
//
// If VITE_MAPBOX_TOKEN is set, use Mapbox's hosted dark style. Otherwise fall
// back to an inline style with OpenStreetMap raster tiles so the dev server
// works out of the box without sign-up.

const MAPBOX_TOKEN = (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined) ?? '';

export const HAS_MAPBOX_TOKEN = MAPBOX_TOKEN.length > 0;

export const MAPBOX_DARK_STYLE = 'mapbox://styles/mapbox/dark-v11';

export const OSM_FALLBACK_STYLE: object = {
	version: 8,
	name: 'osm-fallback',
	sources: {
		osm: {
			type: 'raster',
			tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
			tileSize: 256,
			attribution: '© OpenStreetMap contributors',
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
	],
	glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf'
};

export function pickStyle(): string | object {
	return HAS_MAPBOX_TOKEN ? MAPBOX_DARK_STYLE : OSM_FALLBACK_STYLE;
}

export function mapboxToken(): string {
	return MAPBOX_TOKEN;
}
