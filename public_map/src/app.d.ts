// See https://svelte.dev/docs/kit/types#app
declare global {
	// Build identity injected by Vite `define` (see vite.config.ts).
	const __BUILD_SHA__: string;
	const __BUILD_BRANCH__: string;
	const __BUILD_TIME__: string;

	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
