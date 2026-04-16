/**
 * Extract a manual-redaction payload from the current text-layer
 * selection.
 *
 * Split from PdfViewer.svelte so the range → bboxes → anchor pipeline
 * can be exercised without a component harness. The caller owns the
 * "selection happened" trigger (a mouseup handler) and the callbacks
 * that receive the payload.
 */

import {
	computeSelectionAnchor,
	rangeToBoundingBoxes,
	snapRangeToWordBoundaries,
	type ManualSelection
} from '$lib/services/selection-bbox';

export interface ReadSelectionOptions {
	textLayerEl: HTMLElement;
	scale: number;
	currentPage: number;
	/** `true` when the reviewer held Alt — we skip word-boundary snapping. */
	altKey: boolean;
}

/**
 * Turn the current native Selection into a `ManualSelection` payload,
 * or `null` if the selection is empty / outside the text layer / does
 * not produce any bboxes.
 *
 * Callers distinguish "no selection / invalid" (null) from "valid
 * selection" (the payload) — the former should typically clear any
 * open action bar, the latter should open it.
 */
export function readTextLayerSelection(options: ReadSelectionOptions): ManualSelection | null {
	const { textLayerEl, scale, currentPage, altKey } = options;

	const sel = window.getSelection();
	if (!sel || sel.rangeCount === 0) return null;
	const range = sel.getRangeAt(0);
	if (range.collapsed) return null;

	// Invariant: we render one page at a time, so the browser cannot extend
	// a native selection across pages — there is nothing else in the
	// scroller for it to reach into. If we ever move to a virtual/paginated
	// scroller that keeps multiple pages in the DOM, this guard becomes
	// necessary-but-insufficient: commonAncestorContainer could sit in a
	// shared parent and still span pages. Revisit this check before that
	// change lands.
	if (!textLayerEl.contains(range.commonAncestorContainer)) return null;

	if (!altKey) snapRangeToWordBoundaries(range);

	const text = range.toString().trim();
	if (!text) return null;

	const bboxes = rangeToBoundingBoxes(range, textLayerEl, scale, currentPage);
	if (bboxes.length === 0) return null;

	const anchor = computeSelectionAnchor(range, textLayerEl, scale, currentPage);
	if (!anchor) return null;

	return { page: currentPage, text, bboxes, anchor };
}
