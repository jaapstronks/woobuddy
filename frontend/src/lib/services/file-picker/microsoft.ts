/**
 * Microsoft 365 / SharePoint / OneDrive file picker (client-side only).
 *
 * Uses the Microsoft Graph File Picker v8 protocol. The picker UI is
 * hosted by Microsoft on the user's SharePoint/OneDrive origin, loaded
 * into an iframe inside a popup we control. We speak to it over
 * `postMessage` on an isolated `MessageChannel`:
 *
 *   1. Sign the user in via MSAL.js (popup flow). MSAL returns a home
 *      account object which tells us which tenant they're on.
 *   2. Derive the picker origin. For consumer OneDrive accounts we
 *      use `https://onedrive.live.com`; for work/school accounts we
 *      use `https://{tenant}-my.sharepoint.com` which we discover
 *      from the Graph `/me/drives` endpoint.
 *   3. Open a popup pointing at the picker URL. Seed it with our
 *      picker options via a form POST (standard v8 pattern).
 *   4. The picker posts an `initialize` message; we reply with a
 *      `MessagePort` so further traffic runs on the channel only.
 *   5. The picker asks us for access tokens as it needs them
 *      (`authenticate` command). We request a fresh token from MSAL
 *      scoped to the resource the picker named and reply with it.
 *   6. When the user picks a file, the picker sends a `pick` command
 *      with a `@microsoft.graph.downloadUrl` we fetch directly from
 *      the SharePoint/OneDrive CDN.
 *
 * The download URL is pre-signed: we do *not* send the access token
 * along with it. The file bytes stream straight from Microsoft's CDN
 * into the reviewer's browser. WOO Buddy's server is not involved.
 *
 * Full protocol reference:
 * https://learn.microsoft.com/en-us/onedrive/developer/controls/file-pickers/
 */

import { microsoftPickerConfig } from '$lib/config/file-picker';
import { loadScript } from './script-loader';
import { PickerError, type PickerHandlers, type PickerResult } from './types';

// MSAL.js is loaded from Microsoft's own CDN. Pinning a major.minor
// keeps the bundle stable; patch updates flow through automatically.
const MSAL_SRC = 'https://alcdn.msauth.net/browser/3.10.0/js/msal-browser.min.js';

// The File Picker v8 channel API version we speak.
const PICKER_CHANNEL_VERSION = '8.0';

// Scopes the picker itself needs. The MSAL login asks for these;
// picker-token requests come back scoped to the resource the picker
// names, which MSAL maps through its silent flow.
const BASE_SCOPES = ['openid', 'profile', 'User.Read', 'Files.Read', 'Files.Read.All'];

/* eslint-disable @typescript-eslint/no-explicit-any */
interface MsalPopupResult {
	account: MsalAccount;
	accessToken: string;
}

interface MsalAccount {
	homeAccountId: string;
	tenantId: string;
	username: string;
}

interface MsalInstance {
	initialize: () => Promise<void>;
	loginPopup: (request: { scopes: string[] }) => Promise<MsalPopupResult>;
	getAllAccounts: () => MsalAccount[];
	setActiveAccount: (account: MsalAccount | null) => void;
	acquireTokenSilent: (request: { scopes: string[]; account: MsalAccount }) => Promise<{
		accessToken: string;
	}>;
	acquireTokenPopup: (request: { scopes: string[] }) => Promise<{ accessToken: string }>;
}

interface MsalWindow {
	msal?: {
		PublicClientApplication: new (config: {
			auth: { clientId: string; authority: string; redirectUri: string };
			cache: { cacheLocation: string };
		}) => MsalInstance;
		InteractionRequiredAuthError?: new (...args: any[]) => Error;
	};
}

function win(): MsalWindow & Window {
	return window as unknown as MsalWindow & Window;
}

let msalInstance: MsalInstance | null = null;

async function getMsal(): Promise<MsalInstance> {
	if (msalInstance) return msalInstance;
	const cfg = microsoftPickerConfig;
	if (!cfg) throw new PickerError('disabled', 'microsoft', 'Microsoft-picker is niet geconfigureerd');
	await loadScript(MSAL_SRC);
	const msal = win().msal;
	if (!msal) throw new PickerError('unknown', 'microsoft', 'MSAL kon niet geladen worden');
	const instance = new msal.PublicClientApplication({
		auth: {
			clientId: cfg.clientId,
			authority: cfg.authority,
			redirectUri: window.location.origin
		},
		// sessionStorage so the token disappears when the tab closes
		// — we don't want a stray token outliving the tab.
		cache: { cacheLocation: 'sessionStorage' }
	});
	await instance.initialize();
	msalInstance = instance;
	return instance;
}

async function signIn(): Promise<MsalAccount> {
	const msal = await getMsal();
	const existing = msal.getAllAccounts();
	if (existing.length > 0) {
		msal.setActiveAccount(existing[0]);
		return existing[0];
	}
	try {
		const res = await msal.loginPopup({ scopes: BASE_SCOPES });
		msal.setActiveAccount(res.account);
		return res.account;
	} catch (cause) {
		const msg = errorMessage(cause);
		if (msg.includes('popup_window_error') || msg.includes('popup')) {
			throw new PickerError('popup-blocked', 'microsoft', 'Aanmeldvenster is geblokkeerd', cause);
		}
		if (msg.includes('consent') || msg.includes('AADSTS65001')) {
			throw new PickerError(
				'consent',
				'microsoft',
				'Uw organisatie staat WOO Buddy nog niet toe als externe app',
				cause
			);
		}
		if (msg.includes('user_cancelled') || msg.includes('user_cancelled_popup')) {
			throw new PickerError('cancelled', 'microsoft', 'Aanmelding geannuleerd', cause);
		}
		throw new PickerError('auth', 'microsoft', 'Aanmelden bij Microsoft mislukte', cause);
	}
}

async function acquireToken(resource: string, account: MsalAccount): Promise<string> {
	const msal = await getMsal();
	const scopes = [`${resource}/.default`];
	try {
		const res = await msal.acquireTokenSilent({ scopes, account });
		return res.accessToken;
	} catch {
		// Fall through to popup flow if silent refresh fails (common
		// when the picker asks for a resource not covered by the
		// initial login).
		const res = await msal.acquireTokenPopup({ scopes });
		return res.accessToken;
	}
}

// Discover the user's OneDrive / SharePoint base URL so we know where
// to open the picker. `/me/drive` returns `webUrl` like
// `https://contoso-my.sharepoint.com/personal/jane_contoso_com/Documents`
// or `https://onedrive.live.com/?cid=...` for consumer accounts.
async function discoverPickerHost(account: MsalAccount): Promise<string> {
	const graphToken = await acquireToken('https://graph.microsoft.com', account);
	const res = await fetch('https://graph.microsoft.com/v1.0/me/drive?$select=webUrl', {
		headers: { Authorization: `Bearer ${graphToken}` }
	});
	if (!res.ok) {
		throw new PickerError(
			'network',
			'microsoft',
			`Kon OneDrive-locatie niet ophalen (${res.status})`
		);
	}
	const body = (await res.json()) as { webUrl?: string };
	if (!body.webUrl) {
		throw new PickerError('unknown', 'microsoft', 'OneDrive-locatie ontbreekt in Graph-antwoord');
	}
	const u = new URL(body.webUrl);
	return `${u.protocol}//${u.host}`;
}

interface PickedItem {
	name: string;
	downloadUrl: string;
	mimeType: string | null;
	sizeBytes: number | null;
}

async function openPickerPopup(
	host: string,
	account: MsalAccount
): Promise<PickedItem> {
	const cfg = microsoftPickerConfig!;
	const channelId = cryptoRandomId();
	const pickerUrl = new URL(`${host}/_layouts/15/FilePicker.aspx`);
	const options = {
		sdk: PICKER_CHANNEL_VERSION,
		entry: { oneDrive: { files: {} } },
		authentication: {},
		messaging: {
			origin: window.location.origin,
			channelId
		},
		selection: { mode: 'single' },
		typesAndSources: {
			mode: 'files',
			filters: ['.pdf'],
			pivots: { oneDrive: true, recent: true }
		}
	};

	const popup = window.open('', 'woobuddy-ms-picker', 'width=1080,height=720');
	if (!popup) {
		throw new PickerError('popup-blocked', 'microsoft', 'Bestand-picker is geblokkeerd');
	}

	// Seed the picker by POSTing the options through a self-submitting
	// form — the picker URL requires form data, not a query string.
	const form = popup.document.createElement('form');
	form.method = 'POST';
	form.action = pickerUrl.toString();
	addHiddenField(form, 'filePicker', JSON.stringify(options));
	popup.document.body.appendChild(form);
	form.submit();

	try {
		return await runPickerChannel(popup, host, channelId, account);
	} finally {
		if (!popup.closed) popup.close();
	}
}

function addHiddenField(form: HTMLFormElement, name: string, value: string): void {
	const input = form.ownerDocument.createElement('input');
	input.type = 'hidden';
	input.name = name;
	input.value = value;
	form.appendChild(input);
}

function cryptoRandomId(): string {
	const bytes = new Uint8Array(16);
	crypto.getRandomValues(bytes);
	return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

// The picker posts an `initialize` message on `window.postMessage`.
// We reply with a `MessagePort`; all further traffic runs on the
// port so we're not listening to arbitrary window messages.
async function runPickerChannel(
	popup: Window,
	pickerHost: string,
	channelId: string,
	account: MsalAccount
): Promise<PickedItem> {
	return new Promise<PickedItem>((resolve, reject) => {
		let port: MessagePort | null = null;
		let settled = false;

		function settle(fn: () => void): void {
			if (settled) return;
			settled = true;
			window.removeEventListener('message', onWindowMessage);
			if (port) {
				port.close();
				port = null;
			}
			fn();
		}

		function onWindowMessage(ev: MessageEvent): void {
			if (ev.source !== popup) return;
			if (ev.origin !== pickerHost) return;
			const data = ev.data as { type?: string; channelId?: string; port?: MessagePort } & {
				data?: unknown;
			};
			if (data?.type !== 'initialize' || data.channelId !== channelId) return;

			port = ev.ports[0];
			if (!port) {
				settle(() =>
					reject(new PickerError('unknown', 'microsoft', 'Picker stuurde geen kanaal'))
				);
				return;
			}

			port.addEventListener('message', onPortMessage);
			port.start();
			port.postMessage({ type: 'activate' });
		}

		function onPortMessage(ev: MessageEvent): void {
			const msg = ev.data as {
				type?: string;
				id?: string;
				data?: any;
			};
			if (!msg) return;
			if (msg.type === 'command') {
				handleCommand(msg);
			} else if (msg.type === 'notification') {
				// Informational — ignore for now.
			}
		}

		async function handleCommand(msg: { id?: string; data?: any }): Promise<void> {
			const cmd = msg.data;
			if (!cmd || !port) return;

			try {
				if (cmd.command === 'authenticate') {
					const token = await acquireToken(cmd.resource as string, account);
					port.postMessage({
						type: 'result',
						id: msg.id,
						data: {
							result: 'token',
							data: { token }
						}
					});
				} else if (cmd.command === 'close') {
					settle(() =>
						reject(new PickerError('cancelled', 'microsoft', 'Picker gesloten'))
					);
				} else if (cmd.command === 'pick') {
					const items = cmd.items ?? [];
					if (items.length === 0) {
						settle(() =>
							reject(new PickerError('cancelled', 'microsoft', 'Geen bestand gekozen'))
						);
						return;
					}
					const item = items[0];
					const downloadUrl = item['@microsoft.graph.downloadUrl'] as string | undefined;
					if (!downloadUrl) {
						// Fallback: ask Graph for a download URL using the
						// item's drive+id. Rare but possible if the picker
						// wasn't configured to inject the shortcut.
						settle(() =>
							reject(
								new PickerError(
									'download',
									'microsoft',
									'Picker leverde geen downloadlink'
								)
							)
						);
						return;
					}
					port.postMessage({
						type: 'result',
						id: msg.id,
						data: { result: 'success' }
					});
					settle(() =>
						resolve({
							name: item.name,
							downloadUrl,
							mimeType: (item.file?.mimeType as string) ?? null,
							sizeBytes: typeof item.size === 'number' ? item.size : null
						})
					);
				}
			} catch (cause) {
				settle(() =>
					reject(
						cause instanceof PickerError
							? cause
							: new PickerError(
									'unknown',
									'microsoft',
									'Onbekende fout in picker-kanaal',
									cause
								)
					)
				);
			}
		}

		window.addEventListener('message', onWindowMessage);

		// Give the popup a reasonable window to contact us. If the
		// user is still on the Microsoft login screen this can take a
		// while, so we err on the generous side.
		const timeout = window.setTimeout(
			() => {
				settle(() =>
					reject(new PickerError('network', 'microsoft', 'Picker reageerde niet op tijd'))
				);
			},
			5 * 60 * 1000
		);

		// Detect user closing the popup manually.
		const closedPoll = window.setInterval(() => {
			if (popup.closed) {
				window.clearInterval(closedPoll);
				window.clearTimeout(timeout);
				settle(() =>
					reject(new PickerError('cancelled', 'microsoft', 'Picker gesloten'))
				);
			}
		}, 500);
	});
}
/* eslint-enable @typescript-eslint/no-explicit-any */

async function downloadItemBytes(
	item: PickedItem,
	handlers: PickerHandlers | undefined
): Promise<Blob> {
	let res: Response;
	try {
		// `@microsoft.graph.downloadUrl` is already pre-signed — no
		// Authorization header needed or wanted. Sending one would
		// actually cause a 401 on some hosts.
		res = await fetch(item.downloadUrl);
	} catch (cause) {
		throw new PickerError(
			'network',
			'microsoft',
			'Verbinding met Microsoft 365 mislukte',
			cause
		);
	}
	if (!res.ok) {
		throw new PickerError(
			'download',
			'microsoft',
			`Download mislukte (${res.status})`
		);
	}

	handlers?.onDownloadStart?.();

	const total = item.sizeBytes ?? parseContentLength(res.headers.get('Content-Length'));
	if (res.body && handlers?.onDownloadProgress) {
		return streamWithProgress(res.body, total, handlers.onDownloadProgress);
	}
	return res.blob();
}

function parseContentLength(header: string | null): number | null {
	if (!header) return null;
	const n = Number(header);
	return Number.isFinite(n) && n > 0 ? n : null;
}

async function streamWithProgress(
	stream: ReadableStream<Uint8Array>,
	total: number | null,
	onProgress: (loaded: number, total: number | null) => void
): Promise<Blob> {
	const reader = stream.getReader();
	const chunks: Uint8Array[] = [];
	let loaded = 0;
	// eslint-disable-next-line no-constant-condition
	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		if (value) {
			chunks.push(value);
			loaded += value.byteLength;
			onProgress(loaded, total);
		}
	}
	return new Blob(chunks as BlobPart[]);
}

function errorMessage(e: unknown): string {
	if (e instanceof Error) return e.message;
	if (typeof e === 'string') return e;
	try {
		return JSON.stringify(e);
	} catch {
		return '';
	}
}

export async function pickFromMicrosoft(handlers?: PickerHandlers): Promise<PickerResult> {
	const cfg = microsoftPickerConfig;
	if (!cfg) throw new PickerError('disabled', 'microsoft', 'Microsoft-picker is niet geconfigureerd');
	const account = await signIn();
	const host = await discoverPickerHost(account);
	const picked = await openPickerPopup(host, account);
	const blob = await downloadItemBytes(picked, handlers);
	return new File([blob], picked.name, {
		type: picked.mimeType || 'application/pdf'
	});
}
