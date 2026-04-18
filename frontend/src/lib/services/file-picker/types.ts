/**
 * Shared types for the file-picker module.
 *
 * A picker returns a `File` because the rest of the upload flow
 * (`$lib/services/upload-flow.ts`) already speaks that shape — dropping
 * picker results into `ingestFile` requires no other changes.
 */

import type { PickerProvider } from '$lib/config/file-picker';

export type { PickerProvider };

export type PickerErrorKind =
	| 'disabled' // picker flag off / client ID missing
	| 'cancelled' // user closed the picker without picking
	| 'consent' // tenant blocked third-party app consent
	| 'popup-blocked' // browser blocked the auth popup
	| 'auth' // OAuth token acquisition failed
	| 'download' // the provider rejected the download request
	| 'unsupported' // picked a file type we don't accept
	| 'network' // transport failure talking to the provider
	| 'unknown';

export class PickerError extends Error {
	constructor(
		public readonly kind: PickerErrorKind,
		public readonly provider: PickerProvider,
		message: string,
		public readonly cause?: unknown
	) {
		super(message);
		this.name = 'PickerError';
	}
}

export interface PickerHandlers {
	/**
	 * Fires when bytes start flowing from the provider CDN into the
	 * browser. The UI uses this to swap the "authenticate / pick"
	 * spinner for a percentage progress bar with the trust copy
	 * ("Uw bestand wordt direct uit [provider] naar uw browser
	 * gehaald. Het passeert onze servers niet.").
	 */
	onDownloadStart?: () => void;
	/**
	 * Download progress in bytes. `total` may be null when the
	 * provider doesn't advertise Content-Length.
	 */
	onDownloadProgress?: (loaded: number, total: number | null) => void;
}

/**
 * Shared result shape. The concrete providers build a `File` from
 * the downloaded bytes + the picked item's name so the downstream
 * upload flow doesn't need to know where it came from.
 */
export type PickerResult = File;
