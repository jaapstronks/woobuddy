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
				//
				// The provider SDKs for #51 (Microsoft Graph File Picker and
				// Google Picker) are loaded from their own CDNs — both
				// publish the canonical URLs there and Google in particular
				// explicitly forbids re-hosting.
				'script-src': [
					'self',
					'wasm-unsafe-eval',
					'https://cdn.jsdelivr.net',
					'https://alcdn.msauth.net',
					'https://apis.google.com',
					'https://accounts.google.com',
					// Plausible self-hosted tracker script (#41). Domain matches
					// PUBLIC_PLAUSIBLE_SRC; when analytics is disabled in an
					// environment (empty PUBLIC_PLAUSIBLE_DOMAIN) the script is
					// never injected, so allowing it here is harmless.
					'https://analytics.woobuddy.nl'
				],
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
				//
				// Picker connections (#51): the user's OAuth token is
				// exchanged against Microsoft and Google endpoints, and the
				// picked file's bytes are downloaded from SharePoint /
				// OneDrive / Google Drive CDNs. All of this happens direct
				// from the browser — we allow the origins here so the
				// fetches aren't blocked.
				'connect-src': [
					'self',
					'data:',
					'http://localhost:8000',
					'http://localhost:8100',
					'https://cdn.jsdelivr.net',
					'https://login.microsoftonline.com',
					'https://graph.microsoft.com',
					'https://*.sharepoint.com',
					'https://*.onedrive.com',
					'https://*.office.com',
					'https://apis.google.com',
					'https://accounts.google.com',
					'https://oauth2.googleapis.com',
					'https://www.googleapis.com',
					'https://content.googleapis.com',
					'https://docs.google.com',
					'https://*.googleusercontent.com',
					// Plausible event endpoint (#41). Same self-hosted origin as
					// the tracker script above.
					'https://analytics.woobuddy.nl'
				],
				// Both pickers render their UI in an iframe we embed. The
				// Microsoft picker lives on the user's SharePoint/OneDrive
				// host, the Google picker lives on docs.google.com.
				'frame-src': [
					'self',
					'https://login.microsoftonline.com',
					'https://*.sharepoint.com',
					'https://*.onedrive.com',
					'https://onedrive.live.com',
					'https://accounts.google.com',
					'https://content.googleapis.com',
					'https://docs.google.com'
				],
				'worker-src': ['self', 'blob:'],
				'frame-ancestors': ['none'],
				'base-uri': ['self'],
				'form-action': ['self']
			}
		}
	},
	vitePlugin: {
		inspector: {
			toggleKeyCombo: 'meta-shift',
			showToggleButton: 'always',
			toggleButtonPos: 'bottom-right'
		}
	}
};

export default config;
