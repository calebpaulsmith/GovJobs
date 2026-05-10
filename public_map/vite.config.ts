import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		strictPort: false
	},
	build: {
		// mapbox-gl is ~1.8 MB before gzip and is dynamically imported in
		// Map.svelte. The default 500 kB warning fires every build but the
		// size is structural — Mapbox GL is core to the product and gzips
		// down to ~492 kB on the wire. Raise the threshold so the warning
		// only fires for genuinely surprising bloat. (We can't put mapbox-gl
		// in manualChunks because SvelteKit's SSR build externalizes it.)
		chunkSizeWarningLimit: 2000
	}
});
