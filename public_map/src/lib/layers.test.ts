import { describe, it, expect } from 'vitest';
import { addAllLayers, LAYER_IDS } from './layers';

// addAllLayers only calls map.addLayer, so a capture stub is enough to assert
// the paint expressions. This guards the Stage 5'.2 overseas styling: markers
// resolved only to a country centroid must render distinctly (amber + lower
// opacity) so they read as approximate, never as a precise US duty station.
function captureLayers() {
	const layers: any[] = [];
	const map = { addLayer: (spec: any) => layers.push(spec) } as any;
	addAllLayers(map, 'postings');
	return layers;
}

describe('addAllLayers job-markers paint (overseas approximate styling)', () => {
	const layers = captureLayers();
	const markers = layers.find((l) => l.id === LAYER_IDS.markers);

	it('defines the individual job-markers layer', () => {
		expect(markers).toBeTruthy();
		expect(markers.type).toBe('circle');
	});

	it('colors country_centroid markers amber and others the default blue', () => {
		const color = markers.paint['circle-color'];
		// ['case', ['==', ['get','geo_quality'],'country_centroid'], '#e0a44d', '#7bd0f2']
		expect(Array.isArray(color)).toBe(true);
		expect(color[0]).toBe('case');
		expect(JSON.stringify(color)).toContain('country_centroid');
		expect(color).toContain('#e0a44d'); // approximate (amber)
		expect(color).toContain('#7bd0f2'); // exact (blue) fallback
	});

	it('makes country_centroid markers translucent to signal approximate', () => {
		const opacity = markers.paint['circle-opacity'];
		expect(Array.isArray(opacity)).toBe(true);
		expect(opacity[0]).toBe('case');
		expect(JSON.stringify(opacity)).toContain('country_centroid');
		expect(opacity).toContain(0.7);
	});
});
