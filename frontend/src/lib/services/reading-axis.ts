/**
 * Reading direction on a rotated page.
 *
 * Every bbox in WOO Buddy lives in *viewer space*: /Rotate applied, top-left
 * origin (see `pdf-text-extractor.ts`). That is the right space to draw in and
 * to hand to `apply_redactions`, but it is the wrong space to reason about
 * text in: at /Rotate 90 a line of text runs top-to-bottom down the screen, so
 * "narrow this box to the matched characters" has to cut along y, not x, and
 * "are these two items on the same line" has to compare x, not y.
 *
 * Before #87 both were hard-coded to x. On a /Rotate 90 page that turned a
 * narrowed box into a band straight across the line: safe (over-redaction, not
 * a leak) but wrong, and it swallowed the rest of the sentence.
 *
 * pdf.js only accepts /Rotate in multiples of 90, so the viewport transform is
 * always axis-aligned and the reading direction is one of four cases. Deriving
 * them from the pdf.js viewport transform (`convertToViewportPoint` applies
 * `[a b c d e f]`, with `a d` set from the rotation):
 *
 * | /Rotate | user +x maps to | reading axis | line-height axis |
 * |---------|-----------------|--------------|------------------|
 * |       0 | +x              | x, forwards  | y                |
 * |      90 | +y              | y, forwards  | x                |
 * |     180 | -x              | x, backwards | y                |
 * |     270 | -y              | y, backwards | x                |
 *
 * "Backwards" is handled by negating the coordinates, so `along()` always
 * returns an extent that increases in reading order. Those negative numbers
 * never leave this module: `withAlong()` maps them back to viewer space.
 *
 * The mirror of this module is `_reading_axis` in `span_resolver.py`, which
 * does the same job for the bboxes the server computes.
 */

import type { PageRotation } from '$lib/types';

export type { PageRotation };

/** The minimal rect shape shared by `ExtractedTextItem` and `BoundingBox`. */
export interface AxisRect {
	x0: number;
	y0: number;
	x1: number;
	y1: number;
}

/** A one-dimensional span, `start <= end`. */
export interface Extent {
	start: number;
	end: number;
}

export interface ReadingAxis {
	rotation: PageRotation;
	/**
	 * Extent along the reading direction, increasing in reading order.
	 * Values are comparable between boxes on the same page and nothing else —
	 * at /Rotate 180 and 270 they are negated viewer coordinates.
	 */
	along(rect: AxisRect): Extent;
	/** Extent across the reading direction — the line-height axis. */
	cross(rect: AxisRect): Extent;
	/** Midpoint of `cross`, for "which line is this item on" tests. */
	crossCenter(rect: AxisRect): number;
	/**
	 * Copy `rect` with its along-extent replaced, in the coordinates `along()`
	 * returns. Every other field (including `page` on a `BoundingBox`) is
	 * preserved.
	 */
	withAlong<T extends AxisRect>(rect: T, start: number, end: number): T;
}

interface AxisSpec {
	/** Which viewer-space axis text runs along. */
	axis: 'x' | 'y';
	/** +1 when reading order follows the axis, -1 when it runs against it. */
	sign: 1 | -1;
}

const AXIS_SPECS: Record<PageRotation, AxisSpec> = {
	0: { axis: 'x', sign: 1 },
	90: { axis: 'y', sign: 1 },
	180: { axis: 'x', sign: -1 },
	270: { axis: 'y', sign: -1 }
};

/**
 * Coerce anything into one of the four supported rotations.
 *
 * Extractions cached in IndexedDB before #87 carry no rotation at all, and a
 * /Rotate that is not a multiple of 90 is invalid PDF that pdf.js already
 * rejects. Both fall back to 0, which is exactly the behavior this module
 * replaces — no worse than before for the pages it cannot classify.
 */
export function normalizeRotation(rotation: number | null | undefined): PageRotation {
	if (typeof rotation !== 'number' || !Number.isFinite(rotation)) return 0;
	const normalized = ((Math.round(rotation) % 360) + 360) % 360;
	return normalized === 90 || normalized === 180 || normalized === 270 ? normalized : 0;
}

const CACHE = new Map<PageRotation, ReadingAxis>();

/** The reading axis for a page rotation. Instances are shared and stateless. */
export function readingAxis(rotation: number | null | undefined): ReadingAxis {
	const normalized = normalizeRotation(rotation);
	const cached = CACHE.get(normalized);
	if (cached) return cached;

	const { axis, sign } = AXIS_SPECS[normalized];
	const alongLo = (r: AxisRect) => (axis === 'x' ? r.x0 : r.y0);
	const alongHi = (r: AxisRect) => (axis === 'x' ? r.x1 : r.y1);
	const crossLo = (r: AxisRect) => (axis === 'x' ? r.y0 : r.x0);
	const crossHi = (r: AxisRect) => (axis === 'x' ? r.y1 : r.x1);

	const built: ReadingAxis = {
		rotation: normalized,
		along(rect) {
			return sign === 1
				? { start: alongLo(rect), end: alongHi(rect) }
				: { start: -alongHi(rect), end: -alongLo(rect) };
		},
		cross(rect) {
			return { start: crossLo(rect), end: crossHi(rect) };
		},
		crossCenter(rect) {
			return (crossLo(rect) + crossHi(rect)) / 2;
		},
		withAlong(rect, start, end) {
			const lo = sign === 1 ? start : -end;
			const hi = sign === 1 ? end : -start;
			return axis === 'x' ? { ...rect, x0: lo, x1: hi } : { ...rect, y0: lo, y1: hi };
		}
	};
	CACHE.set(normalized, built);
	return built;
}
