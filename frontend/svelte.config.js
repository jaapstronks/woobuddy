import adapter from '@sveltejs/adapter-node';

// Shoelace web components (<sl-*>) don't declare ARIA roles that Svelte's
// a11y checker recognizes, so it flags every <sl-button onclick={...}> as a
// "static element with click handler". The components themselves are
// keyboard-accessible — suppress those two rules when the offending element
// is a Shoelace custom element.
const SHOELACE_A11Y_WARNINGS = new Set([
	'a11y_click_events_have_key_events',
	'a11y_no_static_element_interactions'
]);

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true),
		warningFilter: (warning) => {
			if (SHOELACE_A11Y_WARNINGS.has(warning.code) && warning.frame?.includes('<sl-')) {
				return false;
			}
			return true;
		}
	},
	kit: {
		adapter: adapter(),
		// Content-Security-Policy for the SvelteKit HTML shell. Configured here
		// (rather than as a raw response header in hooks.server.ts) so that
		// SvelteKit can automatically hash/nonce its own inline hydration
		// scripts — otherwise a strict `script-src 'self'` breaks the app in
		// production as well as the Vite-injected scripts in dev. Note that
		// `kit.csp` only applies to production builds; dev relies on Vite's
		// own unrestricted script injection.
		csp: {
			mode: 'auto',
			directives: {
				'default-src': ['self'],
				// `wasm-unsafe-eval` is required for the in-browser OCR path
				// (#49): tesseract.js calls `WebAssembly.instantiate()` from
				// its worker, which a strict `script-src` blocks by default.
				// This directive keeps arbitrary `eval()` blocked — it only
				// whitelists WebAssembly compilation.
				'script-src': ['self', 'wasm-unsafe-eval', 'https://cdn.jsdelivr.net'],
				'style-src': ['self', 'unsafe-inline', 'https://fonts.googleapis.com', 'https://cdn.jsdelivr.net'],
				'font-src': ['self', 'https://fonts.gstatic.com', 'https://cdn.jsdelivr.net', 'data:'],
				'img-src': ['self', 'data:', 'blob:'],
				// Backend runs in Docker with host port 8100 mapped to the
				// container's 8000 (see docker-compose.yml). Local-only
				// uvicorn runs default to 8000. Allow both so either workflow
				// connects without a CSP violation. `data:` is required
				// because Shoelace's icon loader uses `fetch()` to hydrate
				// its bundled SVGs, even when they're inlined as data URIs
				// (e.g. <sl-checkbox> check mark).
				'connect-src': [
					'self',
					'data:',
					'http://localhost:8000',
					'http://localhost:8100',
					'https://cdn.jsdelivr.net'
				],
				'worker-src': ['self', 'blob:'],
				'frame-ancestors': ['none'],
				'base-uri': ['self'],
				'form-action': ['self']
			}
		}
	}
};

export default config;
