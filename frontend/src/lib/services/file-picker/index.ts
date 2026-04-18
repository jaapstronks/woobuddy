/**
 * Provider-agnostic file picker module (#51).
 *
 * The picker runs entirely client-side: both Microsoft's Graph File
 * Picker v8 and Google's Picker API render their UI in the reviewer's
 * browser, return a file reference, and let us download the bytes
 * directly from the provider's CDN with an OAuth-scoped URL. WOO
 * Buddy's server is never in the path of the document.
 *
 * Providers are gated by env-var feature flags (see
 * `$lib/config/file-picker.ts`). A deployment without Azure AD /
 * Google Cloud apps registered simply doesn't render the provider
 * button — the existing drag-and-drop path is untouched.
 *
 * Downstream consumers should `pick()` this module, feed the
 * returned `File` into `ingestFile()` from `upload-flow.ts`, and
 * treat cancellations as non-errors.
 */

export { pickFromMicrosoft } from './microsoft';
export { pickFromGoogle } from './google';
export { trackPicker } from './analytics';
export { PickerError } from './types';
export type { PickerHandlers, PickerResult, PickerErrorKind } from './types';

import { pickFromMicrosoft } from './microsoft';
import { pickFromGoogle } from './google';
import type { PickerProvider } from '$lib/config/file-picker';
import type { PickerHandlers, PickerResult } from './types';

export async function pickFromProvider(
	provider: PickerProvider,
	handlers?: PickerHandlers
): Promise<PickerResult> {
	return provider === 'microsoft'
		? pickFromMicrosoft(handlers)
		: pickFromGoogle(handlers);
}
