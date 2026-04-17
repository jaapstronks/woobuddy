/**
 * File-picker feature flags and OAuth client IDs.
 *
 * Both Microsoft (Graph File Picker v8) and Google (Picker API) run
 * entirely in the browser: the provider hosts the picker UI, the user
 * authenticates against the provider directly, and we fetch the picked
 * file's bytes from the provider's CDN via the OAuth-scoped download
 * URL. See `$lib/services/file-picker/` for the implementation and
 * `docs/self-hosting/file-picker.md` for how to create your own app
 * registrations.
 *
 * The feature is **opt-in per deployment**: a provider button only
 * renders when its client ID is configured. That way self-hosters
 * without Azure AD / Google Cloud setup don't see a broken button,
 * and WOO Buddy's hosted tier can ship Microsoft first and Google
 * later without a code change.
 */
import {
	PUBLIC_MS_PICKER_CLIENT_ID,
	PUBLIC_MS_PICKER_AUTHORITY,
	PUBLIC_GOOGLE_PICKER_CLIENT_ID,
	PUBLIC_GOOGLE_PICKER_API_KEY,
	PUBLIC_GOOGLE_PICKER_APP_ID
} from '$env/static/public';

export type PickerProvider = 'microsoft' | 'google';

export interface MicrosoftPickerConfig {
	clientId: string;
	/**
	 * OAuth authority. `common` lets any work/school or personal account
	 * sign in. A single-tenant deployment can pin to its own tenant ID.
	 */
	authority: string;
}

export interface GooglePickerConfig {
	clientId: string;
	apiKey: string;
	/**
	 * Google Cloud project number — required by the Picker API so it
	 * can show the user which app they're authorizing.
	 */
	appId: string;
}

export const microsoftPickerConfig: MicrosoftPickerConfig | null =
	PUBLIC_MS_PICKER_CLIENT_ID
		? {
				clientId: PUBLIC_MS_PICKER_CLIENT_ID,
				authority:
					PUBLIC_MS_PICKER_AUTHORITY || 'https://login.microsoftonline.com/common'
			}
		: null;

export const googlePickerConfig: GooglePickerConfig | null =
	PUBLIC_GOOGLE_PICKER_CLIENT_ID && PUBLIC_GOOGLE_PICKER_API_KEY && PUBLIC_GOOGLE_PICKER_APP_ID
		? {
				clientId: PUBLIC_GOOGLE_PICKER_CLIENT_ID,
				apiKey: PUBLIC_GOOGLE_PICKER_API_KEY,
				appId: PUBLIC_GOOGLE_PICKER_APP_ID
			}
		: null;

export function isPickerEnabled(provider: PickerProvider): boolean {
	return provider === 'microsoft'
		? microsoftPickerConfig !== null
		: googlePickerConfig !== null;
}

export function anyPickerEnabled(): boolean {
	return isPickerEnabled('microsoft') || isPickerEnabled('google');
}
