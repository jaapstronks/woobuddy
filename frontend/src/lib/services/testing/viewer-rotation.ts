/**
 * Test-only helper: re-express a viewer-space box on a rotated page.
 *
 * Not imported by any application code. It lives outside the `*.test.ts`
 * pattern so several suites can share it (#87).
 *
 * The mapping is derived from pdf.js's own `PageViewport` transforms and was
 * checked against real viewports built over a four-rotation PyMuPDF fixture:
 * take the /Rotate 0 viewer box for a piece of text and this returns the box
 * pdf.js reports for that same text once the page carries /Rotate R.
 *
 *   /Rotate  90: (x, y) → (H - y, x)          page becomes H × W
 *   /Rotate 180: (x, y) → (W - x, H - y)      page stays  W × H
 *   /Rotate 270: (x, y) → (y, W - x)          page becomes H × W
 *
 * Tests use it to assert the invariant that actually matters: rotating a page
 * must not change which characters a bbox resolves to, or which characters a
 * search hit blacks out.
 */

import type { PageRotation } from '$lib/types';

export interface RotatableBox {
	x0: number;
	y0: number;
	x1: number;
	y1: number;
}

/** A4 in points — the page box every rotation fixture in the suite uses. */
export const PAGE_WIDTH = 595;
export const PAGE_HEIGHT = 842;

function mapPoint(
	rotation: PageRotation,
	x: number,
	y: number,
	width: number,
	height: number
): [number, number] {
	switch (rotation) {
		case 90:
			return [height - y, x];
		case 180:
			return [width - x, height - y];
		case 270:
			return [y, width - x];
		default:
			return [x, y];
	}
}

/**
 * Map a /Rotate 0 viewer-space box onto the same page at `rotation`.
 *
 * Corners are transformed independently and re-sorted, exactly as
 * `toViewportBox` in `pdf-text-extractor.ts` does — at 90/270 the transform
 * swaps which corner is "top-left".
 */
export function rotateBox<T extends RotatableBox>(
	box: T,
	rotation: PageRotation,
	width = PAGE_WIDTH,
	height = PAGE_HEIGHT
): T {
	const [ax, ay] = mapPoint(rotation, box.x0, box.y0, width, height);
	const [bx, by] = mapPoint(rotation, box.x1, box.y1, width, height);
	return {
		...box,
		x0: Math.min(ax, bx),
		y0: Math.min(ay, by),
		x1: Math.max(ax, bx),
		y1: Math.max(ay, by)
	};
}

/** The four rotations, for `it.each`-style loops. */
export const ROTATIONS: PageRotation[] = [0, 90, 180, 270];
