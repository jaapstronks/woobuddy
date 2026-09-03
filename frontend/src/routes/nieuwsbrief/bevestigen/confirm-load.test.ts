/**
 * The confirmation page's server load (#76).
 *
 * Everything a visitor sees on this page comes out of one function, and
 * the cases that matter are the ones where the backend is not helpful: a
 * link with no token, an API that is down, a body that isn't the shape
 * we expect. None of them may throw — a 500 on a confirmation link reads
 * as "your signup is broken", when the truth is usually "try again in a
 * minute".
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('$env/static/public', () => ({ PUBLIC_API_URL: 'http://api.test' }));

import { load } from './+page.server';

type LoadArgs = Parameters<typeof load>[0];

function run(search: string, fetchImpl: typeof fetch) {
	return load({
		url: new URL(`https://woobuddy.nl/nieuwsbrief/bevestigen${search}`),
		fetch: fetchImpl
	} as unknown as LoadArgs);
}

function jsonResponse(body: unknown, status = 200): typeof fetch {
	return (async () =>
		new Response(JSON.stringify(body), {
			status,
			headers: { 'content-type': 'application/json' }
		})) as unknown as typeof fetch;
}

describe('newsletter confirmation load', () => {
	it('passes the token through and returns the backend verdict', async () => {
		const calls: Array<[string, RequestInit | undefined]> = [];
		const fetchImpl = (async (url: string, init?: RequestInit) => {
			calls.push([url, init]);
			return new Response(JSON.stringify({ status: 'confirmed' }), { status: 200 });
		}) as unknown as typeof fetch;

		expect(await run('?t=abc.def', fetchImpl)).toEqual({ status: 'confirmed' });

		expect(calls).toHaveLength(1);
		expect(calls[0][0]).toBe('http://api.test/api/leads/confirm');
		expect(calls[0][1]?.method).toBe('POST');
		expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ token: 'abc.def' });
	});

	it.each(['expired', 'invalid', 'unavailable'] as const)(
		'passes %s through unchanged',
		async (status) => {
			expect(await run('?t=abc.def', jsonResponse({ status }))).toEqual({ status });
		}
	);

	it('reports missing without calling the API when there is no token', async () => {
		const fetchImpl = (async () => {
			throw new Error('must not be called');
		}) as unknown as typeof fetch;

		expect(await run('', fetchImpl)).toEqual({ status: 'missing' });
	});

	it('treats a non-2xx from the API as unavailable', async () => {
		expect(await run('?t=abc.def', jsonResponse({ status: 'confirmed' }, 500))).toEqual({
			status: 'unavailable'
		});
	});

	it('treats an unreachable API as unavailable rather than throwing', async () => {
		const fetchImpl = (async () => {
			throw new TypeError('fetch failed');
		}) as unknown as typeof fetch;

		expect(await run('?t=abc.def', fetchImpl)).toEqual({ status: 'unavailable' });
	});

	it.each([
		{ status: 'something-else' },
		{ status: 42 },
		{},
		null,
		'not an object'
	])('rejects an unrecognised body shape: %j', async (body) => {
		expect(await run('?t=abc.def', jsonResponse(body))).toEqual({ status: 'unavailable' });
	});

	it('treats an unparseable body as unavailable', async () => {
		const fetchImpl = (async () =>
			new Response('<html>502</html>', { status: 200 })) as unknown as typeof fetch;

		expect(await run('?t=abc.def', fetchImpl)).toEqual({ status: 'unavailable' });
	});
});
