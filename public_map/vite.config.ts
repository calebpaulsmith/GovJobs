import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Build identity, surfaced in the UI so you can tell which deploy you're on.
// Cloudflare Pages sets CF_PAGES_* during the build (preview deploys get the
// PR's head branch; production gets `master`). Falls back to local/dev so
// `npm run dev` and `npm run build` work without those vars.
const buildSha = (process.env.CF_PAGES_COMMIT_SHA ?? '').slice(0, 7) || 'dev';
const buildBranch = process.env.CF_PAGES_BRANCH ?? 'local';
const buildTime = new Date().toISOString();

export default defineConfig({
	plugins: [sveltekit()],
	define: {
		__BUILD_SHA__: JSON.stringify(buildSha),
		__BUILD_BRANCH__: JSON.stringify(buildBranch),
		__BUILD_TIME__: JSON.stringify(buildTime)
	},
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
