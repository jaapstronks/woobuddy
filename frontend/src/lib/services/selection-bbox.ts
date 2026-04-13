/**
 * DOM Selection → PDF bounding-box mapping.
 *
 * Manual text-redaction flow (#06): the reviewer drags across the pdf.js
 * text layer, the browser produces a native `Range`, and we translate that
 * into one or more bounding boxes in PDF coordinate space so the server can
 * store it as a detection.
 *
 * Coordinate model (matches `pdf-text-extractor.ts` and the backend):
 *
 *   - Origin: top-left of the page (PyMuPDF convention)
 *   - Units:  PDF points (1 point = 1/72 inch)
 *
 * Since the text layer container is positioned so that its CSS origin equals
 * the top-left of the page, and pdf.js scales text runs by `scale`, a pixel
 * inside the container at offset `(px, py)` maps to `(px / scale, py / scale)`
 * in PDF points.
 */

import type { BoundingBox } from '$lib/types';

/**
 * Result of a reviewer's text selection — everything the UI needs to pop
 * the action bar / form and eventually POST a manual detection.
 *
 * `text` is held purely client-side (it never leaves the browser on the
 * wire to the server, only on the wire to IndexedDB / UI state).
 */
export interface ManualSelection {
	page: number;
	text: string;
	bboxes: BoundingBox[];
	anchor: SelectionAnchor;
}

const WORD_BOUNDARY_RE = /[\s\u00A0.,;:!?()[\]{}"'«»„"—–-]/;

/**
 * Small slack (0.5 pt) helps PyMuPDF's redaction annotations fully cover
 * descenders and antialiasing — without it we sometimes see a sliver of
 * the original character peeking out of the black bar. Area selection uses
 * the same value so the two flows produce pixel-compatible redactions.
 */
export const BBOX_SLACK_PT = 0.5;

/**
 * Convert a single viewport-space rectangle (from `getBoundingClientRect()` or
 * `Range.getClientRects()`) into a PDF-points `BoundingBox`, relative to a
 * container rect. Used by both the text-selection flow (#06) and the area
 * selection flow (#07) so they stay pixel-compatible.
 */
export function rectToBoundingBox(
	rect: { left: number; top: number; right: number; bottom: number },
	containerRect: { left: number; top: number },
	scale: number,
	page: number
): BoundingBox {
	return {
		page,
		x0: (rect.left - containerRect.left) / scale - BBOX_SLACK_PT,
		y0: (rect.top - containerRect.top) / scale - BBOX_SLACK_PT,
		x1: (rect.right - containerRect.left) / scale + BBOX_SLACK_PT,
		y1: (rect.bottom - containerRect.top) / scale + BBOX_SLACK_PT
	};
}

/**
 * Extend a Range to the nearest word boundaries inside the current text
 * nodes. Used when the reviewer drags without holding Alt — most of the
 * time they want whole words (names, phone numbers), not mid-word snippets.
 */
export function snapRangeToWordBoundaries(range: Range): void {
	const startNode = range.startContainer;
	if (startNode.nodeType === Node.TEXT_NODE) {
		const text = startNode.textContent ?? '';
		let start = range.startOffset;
		while (start > 0 && !WORD_BOUNDARY_RE.test(text[start - 1])) start--;
		try {
			range.setStart(startNode, start);
		} catch {
			// Offset fell outside the node — leave the range untouched.
		}
	}

	const endNode = range.endContainer;
	if (endNode.nodeType === Node.TEXT_NODE) {
		const text = endNode.textContent ?? '';
		let end = range.endOffset;
		while (end < text.length && !WORD_BOUNDARY_RE.test(text[end])) end++;
		try {
			range.setEnd(endNode, end);
		} catch {
			// Offset fell outside the node — leave the range untouched.
		}
	}
}

/**
 * Convert a DOM Range over the pdf.js text layer into one bounding box per
 * visual line. Client rects come from the browser's layout engine, so
 * multi-line selections naturally produce one rect per line.
 *
 * `container` is the text-layer div; all rects are returned in PDF points
 * relative to its top-left corner.
 */
export function rangeToBoundingBoxes(
	range: Range,
	container: HTMLElement,
	scale: number,
	page: number
): BoundingBox[] {
	if (range.collapsed) return [];

	const containerRect = container.getBoundingClientRect();

	const rects: BoundingBox[] = [];
	for (const rect of Array.from(range.getClientRects())) {
		if (rect.width <= 0 || rect.height <= 0) continue;
		rects.push(rectToBoundingBox(rect, containerRect, scale, page));
	}

	// Merge rects whose vertical spans overlap heavily — browsers sometimes
	// split a single visual line across multiple DOMRects (one per span) and
	// the reviewer expects one redaction bar per line.
	return mergeHorizontallyAdjacent(rects);
}

function mergeHorizontallyAdjacent(rects: BoundingBox[]): BoundingBox[] {
	if (rects.length <= 1) return rects;
	const sorted = [...rects].sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
	const merged: BoundingBox[] = [];
	for (const r of sorted) {
		const last = merged[merged.length - 1];
		const sameLine = last && Math.abs(last.y0 - r.y0) < 2 && Math.abs(last.y1 - r.y1) < 2;
		const touching = last && r.x0 <= last.x1 + 2;
		if (sameLine && touching) {
			last.x0 = Math.min(last.x0, r.x0);
			last.x1 = Math.max(last.x1, r.x1);
			last.y0 = Math.min(last.y0, r.y0);
			last.y1 = Math.max(last.y1, r.y1);
		} else {
			merged.push({ ...r });
		}
	}
	return merged;
}

/**
 * Page-space anchor point for positioning floating UI near a selection.
 *
 * Coordinates are in PDF points, relative to the top-left of the page's
 * text layer (same coordinate space as `BoundingBox`). The consumer projects
 * them to viewport pixels using `stageEl.getBoundingClientRect()` + the
 * current `scale`, which lets the anchor follow the selection while the
 * reviewer scrolls or zooms — without a scroll listener on a specific
 * scroller or a stored live `Range`.
 *
 * `placement` is computed at capture time from the range's viewport
 * position; recomputing it on every scroll would make the bar jitter
 * between "above" and "below" as the selection nears the viewport edge.
 */
export interface SelectionAnchor {
	page: number;
	pdfX: number;
	pdfY: number;
	placement: 'above' | 'below';
}

export function computeSelectionAnchor(
	range: Range,
	container: HTMLElement,
	scale: number,
	page: number
): SelectionAnchor | null {
	const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0 && r.height > 0);
	if (rects.length === 0) return null;
	const first = rects[0];
	const last = rects[rects.length - 1];
	const containerRect = container.getBoundingClientRect();

	const GAP = 8;
	const BAR_HEIGHT_ESTIMATE = 44;
	const placement: 'above' | 'below' =
		first.top >= BAR_HEIGHT_ESTIMATE + GAP ? 'above' : 'below';

	if (placement === 'above') {
		const xPx = (first.left + first.right) / 2 - containerRect.left;
		const yPx = first.top - containerRect.top - GAP;
		return { page, pdfX: xPx / scale, pdfY: yPx / scale, placement };
	}
	const xPx = (last.left + last.right) / 2 - containerRect.left;
	const yPx = last.bottom - containerRect.top + GAP;
	return { page, pdfX: xPx / scale, pdfY: yPx / scale, placement };
}

/**
 * Anchor a floating bar on an area-selection rectangle. Mirrors
 * `computeSelectionAnchor` but works from a single rectangle in viewport
 * space instead of a DOM Range. The bar sits above the rectangle when
 * there's room above it in the viewport, otherwise below — same rule as
 * text selection.
 */
export function computeRectAnchor(
	rectViewport: { left: number; top: number; right: number; bottom: number },
	containerRect: { left: number; top: number },
	scale: number,
	page: number
): SelectionAnchor {
	const GAP = 8;
	const BAR_HEIGHT_ESTIMATE = 44;
	const placement: 'above' | 'below' =
		rectViewport.top >= BAR_HEIGHT_ESTIMATE + GAP ? 'above' : 'below';

	const centerPx = (rectViewport.left + rectViewport.right) / 2 - containerRect.left;
	if (placement === 'above') {
		const yPx = rectViewport.top - containerRect.top - GAP;
		return { page, pdfX: centerPx / scale, pdfY: yPx / scale, placement };
	}
	const yPx = rectViewport.bottom - containerRect.top + GAP;
	return { page, pdfX: centerPx / scale, pdfY: yPx / scale, placement };
}
