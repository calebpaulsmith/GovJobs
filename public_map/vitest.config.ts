import { defineConfig } from 'vitest/config';

// Vitest runs on plain Vite (no SvelteKit plugin) to keep the test loader
// lightweight and to avoid touching `$app/*` SvelteKit modules from unit
// tests. If/when we need to test Svelte components, add `svelte` plugin
// here separately.
export default defineConfig({
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node',
		globals: false
	}
});
