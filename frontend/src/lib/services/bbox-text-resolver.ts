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

function overlapsVertically(bbox: BoundingBox, item: ExtractedTextItem): boolean {
	const itemCenterY = (item.y0 + item.y1) / 2;
	return itemCenterY >= bbox.y0 && itemCenterY <= bbox.y1;
}

function overlapsHorizontally(bbox: BoundingBox, item: ExtractedTextItem): boolean {
	return item.x0 < bbox.x1 + X_TOLERANCE && item.x1 > bbox.x0 - X_TOLERANCE;
}

/**
 * Return the substring of `item.text` that corresponds to the portion
 * of the item sitting inside `bbox`, using linear x-to-character mapping.
 *
 * If the item is fully contained within the bbox (within a small
 * tolerance), the entire text is returned. If only part of the item
 * overlaps, the proportional slice is returned. A zero-width item (or
 * one with no characters) returns the full text as a safe fallback.
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

	const startFrac = (overlapX0 - item.x0) / itemWidth;
	const endFrac = (overlapX1 - item.x0) / itemWidth;
	const startIdx = Math.max(0, Math.floor(startFrac * item.text.length));
	const endIdx = Math.min(item.text.length, Math.ceil(endFrac * item.text.length));
	if (endIdx <= startIdx) return '';
	return item.text.slice(startIdx, endIdx).trim();
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
