/**
 * SvelteKit server hooks.
 *
 * Content-Security-Policy is configured via `kit.csp` in `svelte.config.js`
 * so SvelteKit can hash/nonce its own inline hydration scripts — setting a
 * strict `script-src 'self'` as a raw header here breaks the framework. The
 * FastAPI backend applies its own (much tighter) CSP to JSON responses via
 * `app/security.py`.
 *
 * This hook still attaches the other security headers that SvelteKit doesn't
 * manage itself.
 *
 * CSRF: SvelteKit enables `csrf.checkOrigin` by default (see
 * https://svelte.dev/docs/kit/configuration#csrf), which rejects cross-site
 * form POSTs to `+page.server.ts` actions. We do not disable it.
 *
 * Proxy shared secret: when the backend is eventually placed behind a
 * server-side SvelteKit proxy (instead of the browser talking to FastAPI
 * directly), `handleFetch` below can attach the `x-woobuddy-proxy-secret`
 * header. The backend already verifies it in `app/security.py` —
 * `verify_proxy_secret` is a no-op when the env var is empty, so the wiring
 * is safe to turn on from either side first.
 */

import type { Handle, HandleFetch } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

export const handle: Handle = async ({ event, resolve }) => {
	const response = await resolve(event);

	// Only attach HTML-shell headers to actual HTML responses — JSON/static
	// assets already have their own headers set elsewhere.
	const contentType = response.headers.get('content-type') ?? '';
	if (contentType.includes('text/html')) {
		response.headers.set('X-Content-Type-Options', 'nosniff');
		response.headers.set('X-Frame-Options', 'DENY');
		response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
		response.headers.set(
			'Permissions-Policy',
			'geolocation=(), microphone=(), camera=()'
		);
	}

	return response;
};

/**
 * Attach the shared proxy secret on server-side fetches to the backend.
 *
 * This only fires for `fetch()` calls made inside `+page.server.ts` /
 * `+layout.server.ts` / hooks. Browser-side `fetch` from `client.ts`
 * currently bypasses this; when we move API calls through the SvelteKit
 * server as part of the auth rollout, this header will start flowing and
 * the backend `verify_proxy_secret` dependency will enforce it.
 */
export const handleFetch: HandleFetch = async ({ request, fetch }) => {
	const secret = env.PRIVATE_API_PROXY_SECRET;
	if (secret && request.url.includes('/api/')) {
		request.headers.set('x-woobuddy-proxy-secret', secret);
	}
	return fetch(request);
};
