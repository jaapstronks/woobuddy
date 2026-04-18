/**
 * Plausible analytics events for the file picker (#51 + #41).
 *
 * Plausible is script-loaded by the landing shell once #41 ships; this
 * helper no-ops when `window.plausible` isn't available so the picker
 * keeps working in dev (and in any deployment without Plausible
 * configured). We deliberately only ship the provider name as a prop —
 * no tenant ID, no file name, no item ID.
 */

import type { PickerProvider } from '$lib/config/file-picker';

export type PickerEvent = 'picker.launched' | 'picker.completed' | 'picker.cancelled';

interface PlausibleFn {
	(event: string, options?: { props?: Record<string, string> }): void;
}

interface PlausibleWindow {
	plausible?: PlausibleFn;
}

export function trackPicker(event: PickerEvent, provider: PickerProvider): void {
	if (typeof window === 'undefined') return;
	const plausible = (window as unknown as PlausibleWindow).plausible;
	if (typeof plausible !== 'function') return;
	plausible(event, { props: { provider } });
}
