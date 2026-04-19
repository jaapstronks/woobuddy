/**
 * Resolves entity text from bounding box coordinates using local text extraction.
 *
 * This is the "client-side join" between server detection metadata (bboxes)
 * and locally-held text extraction data. The server deliberately does not
 * store entity_text — the client reconstructs it here.
 */

import type { BoundingBox, ExtractionResult, ExtractedTextItem } from '$lib/types';

// Horizontal tolerance in PDF points — a few points of slack on the x
// axis is safe because text items on the same line never occupy the
// same x range. Vertical matching uses the text item's *center* y
// against the bbox's y range (no tolerance): an AABB overlap with any
// y-tolerance at all accidentally picks up adjacent lines, because
// PyMuPDF/pdf.js line boxes include ascender/descender padding that
// causes a 1–2pt overlap between consecutive lines. This used to
// surface as a detection card showing e.g. "Postbus 9100, 2300 PC
// Leiden\nTelefoon: 071 516 50 00" for a bbox that only covers the
// "Postbus" line — the card then contradicted what the PDF overlay
// actually highlighted.
const X_TOLERANCE = 2.0;

// When a text item is *contained* within the bbox (its x range falls
// wholly inside bbox.x range, within tolerance), return the whole item
// text verbatim. When the bbox is *narrower* than the text item —
// typical when the backend has proportionally narrowed a span-level
// bbox down to just the matched entity (`_narrow_bbox_to_substring`
// in pdf_engine.py), but pdf.js reports the entire line as one text
// item — slice the item's text proportionally by the overlap so the
// sidebar card highlights the same characters that the PDF overlay
// draws a box around. Without this slicing, a narrow bbox for
// "W. de Groot" inside a line-wide pdf.js item would return the full
// line "de familie El Khatib (huisnummer 22). Ook de heer W. de
// Groot, bewoner van nummer 26, heeft" and the sidebar's orange
// highlight would span a whole paragraph the PDF overlay never
// touched.
const CONTAINED_ITEM_TOLERANCE = 1.5;

// Gap (in points) below which two matched items on the same line are
// considered "touching" and join without a space in the display text.
// Mirrors `ADJACENT_X_TOLERANCE` in `pdf-text-extractor.ts`: the
// extractor uses the same threshold to decide whether to insert a space
// when building the per-page fullText sent to the backend, so the card
// display matches the text the detector actually saw. Without this, a
// monospace PDF (e.g. Menlo) where pdf.js returns one item per glyph
// surfaces every detection as "W i l l e m i j n" / "0 0 0 4 7 5 2 8 6 1"
// in the sidebar, even though the underlying detection is correct.
const TOUCHING_GAP = 1.5;
const SAME_LINE_Y_TOLERANCE = 2;

// Helvetica/Arial AFM advance widths in 1/1000 em. Mirrors the backend's
// `_GLYPH_WIDTHS` table in `span_resolver.py` so that the client's
// x-to-character mapping agrees with the bbox narrowing the backend just
// did. Without AFM weighting a linear-by-char-count mapping clips the
// first character of names like "P. Hoogvliet" inside a line-wide
// pdf.js item ("Wethouder P. Hoogvliet …"): "Wethouder" is full of wide
// glyphs (W, d, u, o) and narrow glyphs (t, e, r), which pushes the
// perceived start of "P." past the true pixel boundary and the slicer
// lands on the "." instead. Values outside this table fall back to
// `DEFAULT_GLYPH_WIDTH`, matching the backend's behavior for non-ASCII
// glyphs.
const DEFAULT_GLYPH_WIDTH = 500;
const GLYPH_WIDTHS: Record<string, number> = {
	' ': 278, '!': 278, '"': 355, '#': 556, '$': 556, '%': 889, '&': 667,
	"'": 191, '(': 333, ')': 333, '*': 389, '+': 584, ',': 278, '-': 333,
	'.': 278, '/': 278,
	'0': 556, '1': 556, '2': 556, '3': 556, '4': 556, '5': 556, '6': 556,
	'7': 556, '8': 556, '9': 556,
	':': 278, ';': 278, '<': 584, '=': 584, '>': 584, '?': 556, '@': 1015,
	A: 667, B: 667, C: 722, D: 722, E: 667, F: 611, G: 778, H: 722, I: 278,
	J: 500, K: 667, L: 556, M: 833, N: 722, O: 778, P: 667, Q: 778, R: 722,
	S: 667, T: 611, U: 722, V: 667, W: 944, X: 667, Y: 667, Z: 611,
	'[': 278, '\\': 278, ']': 278, '^': 469, '_': 556, '`': 333,
	a: 556, b: 556, c: 500, d: 556, e: 556, f: 278, g: 556, h: 556, i: 222,
	j: 222, k: 500, l: 222, m: 833, n: 556, o: 556, p: 556, q: 556, r: 333,
	s: 500, t: 278, u: 556, v: 500, w: 722, x: 500, y: 500, z: 500,
	'{': 334, '|': 260, '}': 334, '~': 584
};

function glyphWidth(ch: string): number {
	return GLYPH_WIDTHS[ch] ?? DEFAULT_GLYPH_WIDTH;
}

function overlapsVertically(bbox: BoundingBox, item: ExtractedTextItem): boolean {
	const itemCenterY = (item.y0 + item.y1) / 2;
	return itemCenterY >= bbox.y0 && itemCenterY <= bbox.y1;
}

function overlapsHorizontally(bbox: BoundingBox, item: ExtractedTextItem): boolean {
	return item.x0 < bbox.x1 + X_TOLERANCE && item.x1 > bbox.x0 - X_TOLERANCE;
}

/**
 * Return the substring of `item.text` that corresponds to the portion
 * of the item sitting inside `bbox`.
 *
 * If the item is fully contained within the bbox (within a small
 * tolerance), the entire text is returned. Otherwise the item's
 * characters are weighted by Helvetica AFM advance widths and the
 * slice is chosen so the pixel range [bbox.x0, bbox.x1] lines up with
 * whole characters — the same weighting the backend uses in
 * `_narrow_bbox_to_substring` when it computed this bbox in the first
 * place.
 */
function sliceItemTextByBbox(bbox: BoundingBox, item: ExtractedTextItem): string {
	const itemWidth = item.x1 - item.x0;
	if (itemWidth <= 0 || item.text.length === 0) return item.text;

	const contained =
		item.x0 >= bbox.x0 - CONTAINED_ITEM_TOLERANCE &&
		item.x1 <= bbox.x1 + CONTAINED_ITEM_TOLERANCE;
	if (contained) return item.text;

	const overlapX0 = Math.max(item.x0, bbox.x0);
	const overlapX1 = Math.min(item.x1, bbox.x1);
	if (overlapX1 <= overlapX0) return '';

	// AFM-weighted cumulative x positions in item-local coordinates.
	// `cumulative[i]` is the pixel offset (from `item.x0`) at the left
	// edge of character `i`; `cumulative[text.length]` is the right
	// edge of the last character, i.e. `itemWidth`.
	const chars = Array.from(item.text);
	let totalAfm = 0;
	for (const ch of chars) totalAfm += glyphWidth(ch);
	if (totalAfm <= 0) return item.text;
	const scale = itemWidth / totalAfm;

	const cumulative = new Array<number>(chars.length + 1);
	cumulative[0] = 0;
	let acc = 0;
	for (let i = 0; i < chars.length; i++) {
		acc += glyphWidth(chars[i]) * scale;
		cumulative[i + 1] = acc;
	}

	const targetStart = overlapX0 - item.x0;
	const targetEnd = overlapX1 - item.x0;

	// Snap the slice to character boundaries by midpoint: a char is
	// included if its midpoint lies inside [targetStart, targetEnd].
	// This avoids clipping a glyph whose left edge sits a hair before
	// `targetStart` (the "P. Hoogvliet" case) or whose right edge
	// spills a hair past `targetEnd`.
	let startIdx = chars.length;
	for (let i = 0; i < chars.length; i++) {
		const mid = (cumulative[i] + cumulative[i + 1]) / 2;
		if (mid >= targetStart) {
			startIdx = i;
			break;
		}
	}
	let endIdx = 0;
	for (let i = chars.length - 1; i >= 0; i--) {
		const mid = (cumulative[i] + cumulative[i + 1]) / 2;
		if (mid <= targetEnd) {
			endIdx = i + 1;
			break;
		}
	}

	if (endIdx <= startIdx) return '';
	return chars.slice(startIdx, endIdx).join('').trim();
}

/**
 * Find the text content that corresponds to a set of bounding boxes.
 * Matches text items from the extraction that overlap spatially with the bboxes.
 */
export function findTextForBboxes(
	bboxes: BoundingBox[],
	extraction: ExtractionResult
): string {
	// Detections routinely carry multiple bboxes for the same canonical
	// entity — one per occurrence in the document. Resolving each bbox
	// independently and joining produces "A.B. Bakker A.B. Bakker" or
	// "Amsterdam Amsterdam Amsterdam Amsterdam," in the sidebar. Dedupe
	// parts that normalize to the same text so the card shows the
	// canonical name once, regardless of how many times it appears.
	const parts: string[] = [];
	const seen = new Set<string>();

	for (const bbox of bboxes) {
		const page = extraction.pages.find((p) => p.pageNumber === bbox.page);
		if (!page) continue;

		const matchingItems = page.textItems
			.filter((item) => overlapsVertically(bbox, item) && overlapsHorizontally(bbox, item))
			.sort((a, b) => {
				// Sort by position: top-to-bottom, then left-to-right
				const yDiff = a.y0 - b.y0;
				if (Math.abs(yDiff) > 2) return yDiff;
				return a.x0 - b.x0;
			});

		if (matchingItems.length === 0) continue;

		// Join text items preserving visual adjacency: if the next item
		// starts where the previous one ended (same line, touching x
		// coordinates), concatenate without inserting a space. This is
		// the same heuristic `pdf-text-extractor.ts` uses when building
		// the backend full-text, and it is essential for PDFs where
		// pdf.js returns one text item per glyph (monospace fonts like
		// Menlo). Without it the sidebar card shows "W i l l e m i j n"
		// while the PDF clearly reads "Willemijn" and the detector saw
		// "Willemijn".
		let joined = '';
		let prev: ExtractedTextItem | null = null;
		for (const item of matchingItems) {
			const slice = sliceItemTextByBbox(bbox, item);
			if (!slice) continue;
			if (prev === null) {
				joined = slice;
			} else {
				const sameLine = Math.abs(item.y0 - prev.y0) < SAME_LINE_Y_TOLERANCE;
				const touching = sameLine && item.x0 - prev.x1 < TOUCHING_GAP;
				joined += (touching ? '' : ' ') + slice;
			}
			prev = item;
		}
		joined = joined.replace(/\s+/g, ' ').trim();
		if (!joined) continue;

		// Normalize for dedup: collapse whitespace, lowercase, strip
		// trailing punctuation so "Amsterdam" and "Amsterdam," collapse.
		const key = joined.toLowerCase().replace(/[.,;:]+$/, '');
		if (seen.has(key)) continue;
		seen.add(key);
		parts.push(joined);
	}

	return parts.join(' ').replace(/\s+/g, ' ').trim();
}

/**
 * Resolve entity_text for all detections that are missing it.
 *
 * Returns new detection objects with entity_text populated from local
 * extraction. Detections whose text cannot be recovered from the client
 * extraction — either because they carry no bboxes or because the
 * bboxes do not overlap any extracted text item — are dropped rather
 * than surfaced as "[onbekend]" placeholder cards. A card with no
 * recoverable text is never actionable (the reviewer has nothing to
 * confirm, reject, or see highlighted), so dropping is always the
 * right call. Detections with a reviewer-authored entity_text are
 * preserved verbatim — those are manual/search_redact rows that never
 * go through this resolution path at all.
 */
// Characters peeled off the tail of URL-like resolved texts. pdf.js
// reports a whole line as one text item and our proportional bbox
// slicing rounds up one character when the bbox ends a hair past the
// URL — which leaks the trailing sentence period into the sidebar
// card ("https://example.com."). Mirrors the server-side URL strip in
// `_tier1.py`.
const URL_TRAILING_PUNCT = /[.,;:!?)\]}>]+$/;

export function resolveEntityTexts<T extends { entity_text?: string; bounding_boxes: BoundingBox[]; entity_type?: string }>(
	detections: T[],
	extraction: ExtractionResult
): T[] {
	const out: T[] = [];
	for (const det of detections) {
		if (det.entity_text && det.entity_text !== '[redacted]') {
			out.push(det);
			continue;
		}
		const bboxes = det.bounding_boxes ?? [];
		if (bboxes.length === 0) continue;
		let text = findTextForBboxes(bboxes, extraction);
		if (!text) continue;
		if (det.entity_type === 'url' || /^https?:\/\//i.test(text)) {
			text = text.replace(URL_TRAILING_PUNCT, '');
		}
		out.push({ ...det, entity_text: text });
	}
	return out;
}
