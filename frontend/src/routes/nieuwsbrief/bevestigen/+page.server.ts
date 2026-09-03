import { PUBLIC_API_URL } from '$env/static/public';
import type { PageServerLoad } from './$types';

/**
 * Redeem the newsletter confirmation link (#76).
 *
 * The token is exchanged server-side rather than from the browser for
 * two reasons: the page has to render the outcome in the HTML shell (a
 * confirmation that flashes a spinner first reads as broken), and the
 * token never has to touch client-side JavaScript at all. `handleFetch`
 * in `hooks.server.ts` attaches the proxy secret to this call for free.
 *
 * The route deliberately sits outside the `(hosted)` group: a
 * self-hoster who configures a mailing list needs this page to work
 * under their own domain too.
 *
 * Never throws. The backend answers 200 with a verdict for every
 * outcome, and anything else — an unreachable API, a mangled body —
 * collapses into `unavailable`, which the page phrases as our problem
 * rather than the visitor's.
 */

export type ConfirmStatus =
	| 'confirmed'
	| 'expired'
	| 'invalid'
	| 'missing'
	| 'unavailable';

const KNOWN: ReadonlySet<string> = new Set([
	'confirmed',
	'expired',
	'invalid',
	'unavailable'
]);

export const load: PageServerLoad = async ({ url, fetch }) => {
	const token = url.searchParams.get('t');
	// No token at all means the link was truncated by a mail client, or
	// someone reached the page by hand. Distinct from `invalid` because
	// there is nothing to say about a signature that was never there.
	if (!token) return { status: 'missing' as ConfirmStatus };

	const base = PUBLIC_API_URL ?? 'http://localhost:8000';
	try {
		const response = await fetch(`${base}/api/leads/confirm`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ token })
		});
		if (!response.ok) return { status: 'unavailable' as ConfirmStatus };

		const body: unknown = await response.json();
		const status =
			typeof body === 'object' && body !== null ? (body as { status?: unknown }).status : null;
		if (typeof status === 'string' && KNOWN.has(status)) {
			return { status: status as ConfirmStatus };
		}
		return { status: 'unavailable' as ConfirmStatus };
	} catch {
		return { status: 'unavailable' as ConfirmStatus };
	}
};
