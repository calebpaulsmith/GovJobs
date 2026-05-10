import { defineConfig } from 'vitest/config';

// Vitest runs on plain Vite (no SvelteKit plugin) to keep the test loader
// lightweight and to avoid touching `$app/*` SvelteKit modules from unit
// tests. If/when we need to test Svelte components, add `svelte` plugin
// here separately.
//
// `envFile: false` keeps the operator's local `.env` (which ships a real
// `VITE_MAPBOX_TOKEN`) from leaking into tests that exercise the no-token
// fallback path. Tests that need a token should set it explicitly with
// `vi.stubEnv(...)`.
export default defineConfig({
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node',
		globals: false,
		env: {
			VITE_MAPBOX_TOKEN: ''
		}
	},
	envPrefix: ['VITE_'],
	envDir: false as unknown as string
});
