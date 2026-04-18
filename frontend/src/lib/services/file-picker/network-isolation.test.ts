/**
 * Network-isolation guardrail for the client-side file picker (#51).
 *
 * The acceptance criterion is strict: picking a file from Microsoft or
 * Google must result in **zero** outbound requests to the WOO Buddy
 * server during the pick+download phase. These tests enforce that two
 * ways:
 *
 *   1. Static scan. The picker module source must not import the API
 *      client or reference `PUBLIC_API_URL`. If someone reaches for
 *      `$lib/api/client` inside a picker file in the future, the
 *      build breaks here before it breaks the trust story.
 *
 *   2. Runtime fetch assertion. We spy on `globalThis.fetch`, run
 *      the Google picker's download helper end-to-end with stubbed
 *      provider SDKs, and assert every URL touched is a Google
 *      origin — none ever hits the WOO Buddy API base.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'http://woobuddy.invalid',
	PUBLIC_MS_PICKER_CLIENT_ID: 'test-ms-client',
	PUBLIC_MS_PICKER_AUTHORITY: 'https://login.microsoftonline.com/common',
	PUBLIC_GOOGLE_PICKER_CLIENT_ID: 'test-google-client',
	PUBLIC_GOOGLE_PICKER_API_KEY: 'test-google-key',
	PUBLIC_GOOGLE_PICKER_APP_ID: 'test-google-app'
}));

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_API_URL: 'http://woobuddy.invalid',
		PUBLIC_MS_PICKER_CLIENT_ID: 'test-ms-client',
		PUBLIC_MS_PICKER_AUTHORITY: 'https://login.microsoftonline.com/common',
		PUBLIC_GOOGLE_PICKER_CLIENT_ID: 'test-google-client',
		PUBLIC_GOOGLE_PICKER_API_KEY: 'test-google-key',
		PUBLIC_GOOGLE_PICKER_APP_ID: 'test-google-app'
	}
}));

// Vite-provided glob import of every source file in the picker module
// so we can scan them as strings without reaching for `node:fs`
// (which would require @types/node).
const PICKER_SOURCES = import.meta.glob('./*.ts', {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

const WOOBUDDY_API_URL = 'http://woobuddy.invalid';

describe('file-picker — network isolation (#51)', () => {
	it('no picker source imports the WOO Buddy API client or PUBLIC_API_URL', () => {
		const sources = Object.entries(PICKER_SOURCES).filter(
			([path]) => !path.endsWith('.test.ts')
		);

		expect(sources.length).toBeGreaterThan(0);

		for (const [path, body] of sources) {
			expect(body, `${path} must not import the WOO Buddy API client`).not.toMatch(
				/\$lib\/api\/client/
			);
			expect(body, `${path} must not reference PUBLIC_API_URL`).not.toMatch(
				/PUBLIC_API_URL/
			);
		}
	});

	it('every fetch made during a Google pick+download stays on provider origins', async () => {
		const fetchUrls: string[] = [];
		const originalFetch = globalThis.fetch;
		const originalWindow = (globalThis as unknown as { window?: unknown }).window;

		// The picker modules use `window` to hang provider SDKs off the
		// host object; in a Node test environment we stub just enough
		// of it to let the google flow run without touching the DOM.
		(globalThis as unknown as { window: unknown }).window = globalThis;

		const stubFetch = vi.fn(async (input: RequestInfo | URL) => {
			const url = typeof input === 'string' ? input : input.toString();
			fetchUrls.push(url);
			// Return a 200 with a 4-byte PDF magic blob.
			return new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
				status: 200,
				headers: { 'Content-Type': 'application/pdf', 'Content-Length': '4' }
			});
		});
		globalThis.fetch = stubFetch as unknown as typeof fetch;

		try {
			// Stub the two Google SDKs so `loadScript` is a no-op and the
			// token + picker flows resolve immediately with fixtures.
			const pickerDouble = {
				ViewId: { DOCS: 'DOCS' },
				Action: { PICKED: 'picked', CANCEL: 'cancel' },
				DocsView: class {
					setMimeTypes() {
						return this;
					}
					setSelectFolderEnabled() {
						return this;
					}
					setIncludeFolders() {
						return this;
					}
				},
				PickerBuilder: class {
					private cb: ((d: unknown) => void) | null = null;
					setAppId() {
						return this;
					}
					setDeveloperKey() {
						return this;
					}
					setOAuthToken() {
						return this;
					}
					addView() {
						return this;
					}
					setLocale() {
						return this;
					}
					setCallback(cb: (d: unknown) => void) {
						this.cb = cb;
						return this;
					}
					build() {
						return {
							setVisible: () => {
								this.cb?.({
									action: 'picked',
									docs: [
										{
											id: 'fake-file-id',
											name: 'woo-document.pdf',
											mimeType: 'application/pdf',
											sizeBytes: 4
										}
									]
								});
							}
						};
					}
				}
			};

			(globalThis as unknown as { gapi: unknown }).gapi = {
				load: (_: string, cb: () => void) => cb()
			};
			(globalThis as unknown as { google: unknown }).google = {
				accounts: {
					oauth2: {
						initTokenClient: ({
							callback
						}: {
							callback: (r: { access_token: string }) => void;
						}) => ({
							requestAccessToken: () => callback({ access_token: 'test-access-token' })
						})
					}
				},
				picker: pickerDouble
			};

			// Pretend the <script> tags already loaded.
			const scriptLoader = await import('./script-loader');
			vi.spyOn(scriptLoader, 'loadScript').mockResolvedValue(undefined);

			const { pickFromGoogle } = await import('./google');
			const file = await pickFromGoogle();

			expect(file).toBeInstanceOf(File);
			expect(file.name).toBe('woo-document.pdf');
			expect(fetchUrls.length).toBeGreaterThan(0);

			for (const url of fetchUrls) {
				expect(url, `forbidden fetch to WOO Buddy origin: ${url}`).not.toContain(
					WOOBUDDY_API_URL
				);
				expect(
					url,
					`fetch outside Google origins: ${url}`
				).toMatch(/^https:\/\/(www\.)?googleapis\.com\//);
			}
		} finally {
			globalThis.fetch = originalFetch;
			if (originalWindow === undefined) {
				delete (globalThis as unknown as { window?: unknown }).window;
			} else {
				(globalThis as unknown as { window: unknown }).window = originalWindow;
			}
			delete (globalThis as unknown as { gapi?: unknown }).gapi;
			delete (globalThis as unknown as { google?: unknown }).google;
		}
	});

	beforeEach(() => {
		// Fresh module registry so each test gets a clean picker module.
		vi.resetModules();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});
});
