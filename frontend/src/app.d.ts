// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	/**
	 * Short git commit hash baked in at build time by Vite (see
	 * `vite.config.ts`). Surfaced in the onderbouwingsrapport (#64)
	 * provenance block as a verifiable WOO Buddy version. Falls back
	 * to `"dev"` when git isn't available at build time.
	 */
	const __WOOBUDDY_BUILD_COMMIT__: string;
}

export {};
