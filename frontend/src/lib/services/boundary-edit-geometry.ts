/**
 * Pure geometry helpers for the boundary-adjustment flow (#11).
 *
 * All functions here are pure and stateless — they take bboxes (plus
 * deltas, directions, or reference rectangles) and return new bboxes.
 * The goal is to keep PdfViewer.svelte focused on state/effect wiring
 * and move the mathy bits into a module that can be unit-tested
 * without a DOM or Svelte runtime.
 *
 * Coordinate model matches `selection-bbox.ts`: PDF points, top-left
 * origin, `page` is 1-based.
 */

import type { BoundingBox } from '$lib/types';

/**
 * Minimum bbox edge length in PDF points. Kept small because inline
 * redactions (e.g. a four-character date) are genuinely tiny; the
 * floor just prevents degenerate zero/negative rectangles when a
 * reviewer drags one resize handle past its opposite edge.
 */
export const BBOX_MIN_PT = 2;

/**
 * Keyboard nudge distances in PDF points, so they stay
 * zoom-independent on screen. Plain Arrow uses the coarse step;
 * Alt+Arrow uses the fine step.
 */
export const ARROW_NUDGE_PT = 3;
export const ARROW_NUDGE_FINE_PT = 0.5;

/**
 * Resize-handle direction. One of eight compass points on a bbox
 * (the four corners and the four edges). The literal strings match
 * the data attributes emitted by `BoundaryEditOverlay.svelte`.
 */
export type HandleDir = 'n' | 'e' | 's' | 'w' | 'ne' | 'nw' | 'se' | 'sw';

/** Shallow clone a bbox array so reviewer drafts don't mutate the store. */
export function cloneBboxes(bboxes: BoundingBox[]): BoundingBox[] {
	return bboxes.map((b) => ({ ...b }));
}

/**
 * Structural equality for two bbox arrays. Used by the boundary-edit
 * Escape handler to decide between "revert draft" and "exit edit".
 */
export function bboxesEqual(a: BoundingBox[] | null, b: BoundingBox[] | null): boolean {
	if (!a || !b || a.length !== b.length) return false;
	return a.every(
		(box, i) =>
			box.page === b[i].page &&
			box.x0 === b[i].x0 &&
			box.y0 === b[i].y0 &&
			box.x1 === b[i].x1 &&
			box.y1 === b[i].y1
	);
}

/**
 * Apply a resize-handle drag delta (in PDF points) to the bbox the
 * reviewer grabbed. The handle direction determines which edges move.
 * Each edge is clamped against its opposite so the box can never
 * collapse below `BBOX_MIN_PT`.
 */
export function applyHandleDelta(
	initial: BoundingBox,
	dir: HandleDir,
	dxPt: number,
	dyPt: number
): BoundingBox {
	let { x0, y0, x1, y1 } = initial;
	if (dir.includes('w')) x0 = Math.min(x1 - BBOX_MIN_PT, x0 + dxPt);
	if (dir.includes('e')) x1 = Math.max(x0 + BBOX_MIN_PT, x1 + dxPt);
	if (dir.includes('n')) y0 = Math.min(y1 - BBOX_MIN_PT, y0 + dyPt);
	if (dir.includes('s')) y1 = Math.max(y0 + BBOX_MIN_PT, y1 + dyPt);
	return { page: initial.page, x0, y0, x1, y1 };
}

/**
 * Extend or shrink a single bbox edge by `stepPt` PDF points. Used
 * by the boundary-edit keyboard nudge (Arrow / Shift+Arrow / Alt+Arrow).
 * `shrink=true` flips the sign so the matching edge moves inward.
 * Returns a new bbox — never mutates `bbox`.
 */
export function nudgeBbox(
	bbox: BoundingBox,
	side: 'left' | 'right' | 'top' | 'bottom',
	stepPt: number,
	shrink: boolean
): BoundingBox {
	const sign = shrink ? -1 : 1;
	const nb = { ...bbox };
	if (side === 'left') nb.x0 = Math.min(nb.x1 - BBOX_MIN_PT, nb.x0 - sign * stepPt);
	if (side === 'right') nb.x1 = Math.max(nb.x0 + BBOX_MIN_PT, nb.x1 + sign * stepPt);
	if (side === 'top') nb.y0 = Math.min(nb.y1 - BBOX_MIN_PT, nb.y0 - sign * stepPt);
	if (side === 'bottom') nb.y1 = Math.max(nb.y0 + BBOX_MIN_PT, nb.y1 + sign * stepPt);
	return nb;
}

/**
 * Map an arrow-key direction + modifier state to the `nudgeBbox` call
 * the reviewer expects. Plain Arrow extends the matching edge
 * outward; Shift+Arrow shrinks the opposite edge inward; Alt uses the
 * fine step. Returns `null` if `key` isn't an arrow.
 */
export function arrowKeyToNudge(
	key: string,
	shiftKey: boolean,
	altKey: boolean
): { side: 'left' | 'right' | 'top' | 'bottom'; stepPt: number; shrink: boolean } | null {
	const stepPt = altKey ? ARROW_NUDGE_FINE_PT : ARROW_NUDGE_PT;
	const shrink = shiftKey;
	switch (key) {
		case 'ArrowLeft':
			return { side: shrink ? 'right' : 'left', stepPt, shrink };
		case 'ArrowRight':
			return { side: shrink ? 'left' : 'right', stepPt, shrink };
		case 'ArrowUp':
			return { side: shrink ? 'bottom' : 'top', stepPt, shrink };
		case 'ArrowDown':
			return { side: shrink ? 'top' : 'bottom', stepPt, shrink };
		default:
			return null;
	}
}

/**
 * Extend a bbox to the union of itself and a clicked word rectangle.
 * Both rectangles live in PDF-point coordinates on the same page.
 * Returns a new bbox — never mutates `bbox`.
 */
export function extendBboxToWord(bbox: BoundingBox, wordBbox: BoundingBox): BoundingBox {
	return {
		page: bbox.page,
		x0: Math.min(bbox.x0, wordBbox.x0),
		y0: Math.min(bbox.y0, wordBbox.y0),
		x1: Math.max(bbox.x1, wordBbox.x1),
		y1: Math.max(bbox.y1, wordBbox.y1)
	};
}

/**
 * Shrink a bbox so that a clicked word sits outside it. We shrink
 * along whichever horizontal edge the word occupies:
 *
 *   - word mostly on the right half → cap `x1` to the word's left edge
 *   - word mostly on the left half  → cap `x0` to the word's right edge
 *
 * Words sitting in the middle of the bbox would require punching a
 * gap, which the single-rectangle model can't represent — those cases
 * are left to the caller to handle (typically by ignoring the click).
 * Returns a new bbox — never mutates `bbox`.
 */
/**
 * Split a detection's bbox list at an x-coordinate inside one of its
 * boxes (#18 split flow). The reviewer clicks a target bbox; we clip
 * it at `pdfX` (clamped to a minimum half-width so neither half
 * degenerates) and partition the full list:
 *
 *   set A = bboxes before the clicked one + the clicked bbox capped
 *           at `x1 = pdfX`
 *   set B = the clicked bbox capped at `x0 = pdfX` + bboxes after
 *
 * Reader-order (earlier-indexed bboxes come first) holds for
 * single-line detections and most multi-line NER spans, which are
 * the only cases split/merge currently targets. Returns `null` if
 * `bboxIndex` is out of range — the caller should bail cleanly.
 */
export function computeSplitBboxes(
	bboxes: BoundingBox[],
	bboxIndex: number,
	pdfX: number
): { bboxesA: BoundingBox[]; bboxesB: BoundingBox[] } | null {
	const target = bboxes[bboxIndex];
	if (!target) return null;

	const clampedX = Math.min(
		Math.max(pdfX, target.x0 + BBOX_MIN_PT),
		target.x1 - BBOX_MIN_PT
	);

	const bboxesA = [
		...bboxes.slice(0, bboxIndex).map((b) => ({ ...b })),
		{ ...target, x1: clampedX }
	];
	const bboxesB = [
		{ ...target, x0: clampedX },
		...bboxes.slice(bboxIndex + 1).map((b) => ({ ...b }))
	];

	return { bboxesA, bboxesB };
}

export function shrinkBboxByWord(bbox: BoundingBox, wordBbox: BoundingBox): BoundingBox {
	const mid = (bbox.x0 + bbox.x1) / 2;
	const wMid = (wordBbox.x0 + wordBbox.x1) / 2;
	if (wMid >= mid) {
		const nx1 = Math.max(bbox.x0 + BBOX_MIN_PT, wordBbox.x0);
		return { ...bbox, x1: nx1 };
	}
	const nx0 = Math.min(bbox.x1 - BBOX_MIN_PT, wordBbox.x1);
	return { ...bbox, x0: nx0 };
}
