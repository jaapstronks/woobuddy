/**
 * Google Drive file picker (client-side only).
 *
 * Flow:
 *   1. Load `apis.google.com/js/api.js` (for gapi + the Picker module)
 *      and `accounts.google.com/gsi/client` (for token-client OAuth).
 *   2. Request an access token via GIS with the `drive.file` scope —
 *      the narrowest scope Drive supports for the picker case: it
 *      *only* gives us access to files the user picks, not their
 *      whole drive.
 *   3. Show the Picker. The picker UI is hosted by Google in an
 *      iframe inside our page; no file bytes cross our origin.
 *   4. When the user picks a file, download it straight from the
 *      Drive CDN using the access token (`alt=media`).
 *
 * The access token lives in memory for the life of this promise. We
 * do not persist it — a fresh pick requires a fresh token request,
 * which Google short-circuits without a prompt when the user already
 * consented.
 */

import { googlePickerConfig } from '$lib/config/file-picker';
import { loadScript } from './script-loader';
import { PickerError, type PickerHandlers, type PickerResult } from './types';

const GAPI_SRC = 'https://apis.google.com/js/api.js';
const GIS_SRC = 'https://accounts.google.com/gsi/client';
const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file';

/* eslint-disable @typescript-eslint/no-explicit-any */
interface GoogleWindow {
	gapi?: {
		load: (name: string, cb: () => void) => void;
	};
	google?: {
		accounts: {
			oauth2: {
				initTokenClient: (config: {
					client_id: string;
					scope: string;
					callback: (res: { access_token?: string; error?: string }) => void;
				}) => { requestAccessToken: (overrides?: { prompt?: string }) => void };
			};
		};
		picker: any;
	};
}

function win(): GoogleWindow & Window {
	return window as unknown as GoogleWindow & Window;
}

async function loadPickerModule(): Promise<void> {
	await loadScript(GAPI_SRC);
	return new Promise((resolve, reject) => {
		const gapi = win().gapi;
		if (!gapi) {
			reject(new Error('gapi unavailable after load'));
			return;
		}
		gapi.load('picker', () => resolve());
	});
}

async function requestAccessToken(clientId: string): Promise<string> {
	await loadScript(GIS_SRC);
	const g = win().google;
	if (!g?.accounts?.oauth2) {
		throw new Error('Google Identity Services unavailable after load');
	}
	return new Promise<string>((resolve, reject) => {
		const client = g.accounts.oauth2.initTokenClient({
			client_id: clientId,
			scope: DRIVE_SCOPE,
			callback: (res) => {
				if (res.error) {
					// `access_denied` is what GIS returns when the user
					// closes the OAuth popup or declines consent.
					if (res.error === 'access_denied' || res.error === 'popup_closed') {
						reject(new PickerError('cancelled', 'google', 'Aanmelding geannuleerd'));
					} else {
						reject(new PickerError('auth', 'google', `OAuth-fout: ${res.error}`));
					}
					return;
				}
				if (!res.access_token) {
					reject(new PickerError('auth', 'google', 'Geen toegangstoken ontvangen'));
					return;
				}
				resolve(res.access_token);
			}
		});
		client.requestAccessToken();
	});
}

interface PickedFile {
	id: string;
	name: string;
	mimeType: string;
	sizeBytes: number | null;
}

async function showPicker(token: string): Promise<PickedFile> {
	const cfg = googlePickerConfig;
	if (!cfg) throw new PickerError('disabled', 'google', 'Google-picker is niet geconfigureerd');
	await loadPickerModule();
	const picker = win().google?.picker;
	if (!picker) throw new PickerError('unknown', 'google', 'Picker-module niet geladen');

	return new Promise<PickedFile>((resolve, reject) => {
		// Only show PDFs. `drive.file` scope + MIME filter means the
		// reviewer can only open files they explicitly select here —
		// the picker won't list the rest of their drive.
		const view = new picker.DocsView(picker.ViewId.DOCS)
			.setMimeTypes('application/pdf')
			.setSelectFolderEnabled(false)
			.setIncludeFolders(true);

		const pickerInstance = new picker.PickerBuilder()
			.setAppId(cfg.appId)
			.setDeveloperKey(cfg.apiKey)
			.setOAuthToken(token)
			.addView(view)
			.setLocale('nl')
			.setCallback((data: any) => {
				if (data.action === picker.Action.PICKED) {
					const doc = data.docs?.[0];
					if (!doc) {
						reject(new PickerError('unknown', 'google', 'Geen bestand ontvangen'));
						return;
					}
					resolve({
						id: doc.id,
						name: doc.name,
						mimeType: doc.mimeType,
						sizeBytes: typeof doc.sizeBytes === 'number' ? doc.sizeBytes : null
					});
				} else if (data.action === picker.Action.CANCEL) {
					reject(new PickerError('cancelled', 'google', 'Selectie geannuleerd'));
				}
			})
			.build();
		pickerInstance.setVisible(true);
	});
}
/* eslint-enable @typescript-eslint/no-explicit-any */

async function downloadFileBytes(
	picked: PickedFile,
	token: string,
	handlers: PickerHandlers | undefined
): Promise<Blob> {
	const url = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(picked.id)}?alt=media`;
	let res: Response;
	try {
		res = await fetch(url, {
			headers: { Authorization: `Bearer ${token}` }
		});
	} catch (cause) {
		throw new PickerError(
			'network',
			'google',
			'Verbinding met Google Drive mislukte',
			cause
		);
	}

	if (!res.ok) {
		throw new PickerError(
			'download',
			'google',
			`Download mislukte (${res.status})`
		);
	}

	handlers?.onDownloadStart?.();

	const total = picked.sizeBytes ?? parseContentLength(res.headers.get('Content-Length'));
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

export async function pickFromGoogle(handlers?: PickerHandlers): Promise<PickerResult> {
	const cfg = googlePickerConfig;
	if (!cfg) throw new PickerError('disabled', 'google', 'Google-picker is niet geconfigureerd');

	const token = await requestAccessToken(cfg.clientId);
	const picked = await showPicker(token);
	const blob = await downloadFileBytes(picked, token, handlers);

	// Picker result is always exposed as a `File` so downstream code
	// (upload-flow.ts) can treat a drag-drop and a Drive pick the
	// same way.
	return new File([blob], picked.name, {
		type: picked.mimeType || 'application/pdf'
	});
}
