/**
 * Manual text-selection redaction state machine (#06).
 *
 * Wraps the three-stage flow `idle → bar → form` that the review page
 * drives from PdfViewer selection events. Kept as a tiny store so the
 * review route isn't a 400-line kitchen sink.
 *
 * Client-first: the selected text lives here in memory only; the review
 * page builds a `CreateManualCommand` from it and pushes the result into
 * the undo stack — the plain text string itself never crosses the wire.
 */

import type { ManualSelection } from '$lib/services/selection-bbox';

type Stage = 'idle' | 'bar' | 'form';

let selection = $state<ManualSelection | null>(null);
let stage = $state<Stage>('idle');

function setSelection(next: ManualSelection) {
	selection = next;
	// A new selection while a form is already open replaces it — the
	// reviewer is re-picking their target before confirming.
	stage = 'bar';
}

function clearIfInBar() {
	// If the form is already open, ignore transient "selection cleared"
	// events — the form owns the state until confirm/cancel.
	if (stage === 'bar') {
		selection = null;
		stage = 'idle';
	}
}

function confirmBar() {
	if (selection) stage = 'form';
}

function cancel() {
	selection = null;
	stage = 'idle';
	if (typeof window !== 'undefined') {
		window.getSelection()?.removeAllRanges();
	}
}

export const manualSelectionStore = {
	get selection() {
		return selection;
	},
	get stage() {
		return stage;
	},
	setSelection,
	clearIfInBar,
	confirmBar,
	cancel
};
