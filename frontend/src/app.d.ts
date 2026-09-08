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

	/**
	 * The release version (`0.2.0`), baked in at build time from
	 * `package.json`, which release-please keeps in step with `VERSION` in
	 * the repository root. Shown in the site footer so it is visible which
	 * version an install is actually running. See
	 * `docs/reference/versioning.md`.
	 */
	const __WOOBUDDY_VERSION__: string;
}

export {};
