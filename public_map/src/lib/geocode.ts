import { HAS_MAPBOX_TOKEN, mapboxToken } from './basemap';
import { loadZipCentroids } from './data';
import type { AddressTarget } from './store.svelte';

export type GeocodeResult = AddressTarget;

interface MapboxFeature {
	place_name?: string;
	center?: [number, number];
	place_type?: string[];
}

interface NominatimResult {
	display_name?: string;
	lat?: string;
	lon?: string;
	type?: string;
	class?: string;
}

export async function geocodeAddress(query: string): Promise<GeocodeResult[]> {
	const trimmed = query.trim();
	if (!trimmed) return [];

	const zipResult = await geocodeZip(trimmed);
	if (zipResult) return [zipResult];

	if (HAS_MAPBOX_TOKEN) {
		const mapboxResults = await geocodeWithMapbox(trimmed);
		if (mapboxResults.length > 0) return mapboxResults;
	}
	return geocodeWithNominatim(trimmed);
}

export function zoomForResult(type: GeocodeResult['resultType']): number {
	if (type === 'region') return 5;
	if (type === 'place') return 7;
	return 9;
}

async function geocodeZip(query: string): Promise<GeocodeResult | null> {
	if (!/^\d{5}$/.test(query)) return null;
	const rows = await loadZipCentroids();
	const match = rows.find((row) => row.zip === query);
	if (!match) return null;
	return {
		label: [match.zip, match.city, match.state].filter(Boolean).join(' · '),
		center: [Number(match.lon), Number(match.lat)],
		zoom: 9,
		resultType: 'postcode',
		provider: 'zip_centroid'
	};
}

async function geocodeWithMapbox(query: string): Promise<GeocodeResult[]> {
	const url = new URL(`https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json`);
	url.searchParams.set('country', 'us');
	url.searchParams.set('types', 'postcode,place,address,region');
	url.searchParams.set('limit', '5');
	url.searchParams.set('access_token', mapboxToken());

	const response = await fetch(url);
	if (!response.ok) return [];
	const payload = await response.json() as { features?: MapboxFeature[] };
	return (payload.features ?? [])
		.filter((feature) => Array.isArray(feature.center))
		.map((feature) => {
			const resultType = mapboxType(feature.place_type ?? []);
			return {
				label: feature.place_name ?? 'Mapbox result',
				center: feature.center as [number, number],
				zoom: zoomForResult(resultType),
				resultType,
				provider: 'mapbox' as const
			};
		});
}

async function geocodeWithNominatim(query: string): Promise<GeocodeResult[]> {
	const url = new URL('https://nominatim.openstreetmap.org/search');
	url.searchParams.set('format', 'jsonv2');
	url.searchParams.set('countrycodes', 'us');
	url.searchParams.set('limit', '5');
	url.searchParams.set('q', query);

	const response = await fetch(url, { headers: { 'Accept-Language': 'en-US,en;q=0.8' } });
	if (!response.ok) return [];
	const rows = await response.json() as NominatimResult[];
	return rows
		.filter((row) => row.lat && row.lon)
		.map((row) => {
			const resultType = nominatimType(row);
			return {
				label: row.display_name ?? 'OpenStreetMap result',
				center: [Number(row.lon), Number(row.lat)] as [number, number],
				zoom: zoomForResult(resultType),
				resultType,
				provider: 'nominatim' as const
			};
		});
}

function mapboxType(types: string[]): GeocodeResult['resultType'] {
	if (types.includes('region')) return 'region';
	if (types.includes('place')) return 'place';
	if (types.includes('postcode')) return 'postcode';
	return 'address';
}

function nominatimType(row: NominatimResult): GeocodeResult['resultType'] {
	const type = `${row.class ?? ''}:${row.type ?? ''}`.toLowerCase();
	if (type.includes('state') || type.includes('administrative')) return 'region';
	if (type.includes('city') || type.includes('town') || type.includes('village')) return 'place';
	if (type.includes('postcode')) return 'postcode';
	return 'address';
}
