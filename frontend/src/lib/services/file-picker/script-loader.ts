/**
 * Dynamic script loader for provider SDKs.
 *
 * MSAL.js and Google's `api.js` / `gsi/client` are only needed when a
 * reviewer actually clicks a picker button. Loading them eagerly would
 * ship two extra vendor bundles to every visitor of the landing page
 * — including reviewers who never use a picker. Instead we inject the
 * `<script>` tags on first use and cache the promise so repeat clicks
 * share the same load.
 *
 * The script origins are whitelisted in `svelte.config.js` CSP.
 */

const loaded = new Map<string, Promise<void>>();

export function loadScript(src: string): Promise<void> {
	const existing = loaded.get(src);
	if (existing) return existing;

	const promise = new Promise<void>((resolve, reject) => {
		const el = document.createElement('script');
		el.src = src;
		el.async = true;
		el.onload = () => resolve();
		el.onerror = () =>
			reject(new Error(`Kon script niet laden: ${src}`));
		document.head.appendChild(el);
	});

	loaded.set(src, promise);
	// If the load fails, allow a retry on the next call rather than
	// poisoning the cache permanently.
	promise.catch(() => loaded.delete(src));
	return promise;
}
