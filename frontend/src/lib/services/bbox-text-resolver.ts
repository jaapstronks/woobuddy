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

		const matching = page.textItems
			.filter((item) => overlapsVertically(bbox, item) && overlapsHorizontally(bbox, item))
			.sort((a, b) => {
				// Sort by position: top-to-bottom, then left-to-right
				const yDiff = a.y0 - b.y0;
				if (Math.abs(yDiff) > 2) return yDiff;
				return a.x0 - b.x0;
			})
			.map((item) => sliceItemTextByBbox(bbox, item))
			.filter((t) => t.length > 0);

		if (matching.length === 0) continue;

		const joined = matching.join(' ').replace(/\s+/g, ' ').trim();
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
 * Returns new detection objects with entity_text populated from local extraction.
 */
export function resolveEntityTexts<T extends { entity_text?: string; bounding_boxes: BoundingBox[] }>(
	detections: T[],
	extraction: ExtractionResult
): T[] {
	return detections.map((det) => {
		if (det.entity_text && det.entity_text !== '[redacted]') return det;
		const text = findTextForBboxes(det.bounding_boxes ?? [], extraction);
		return { ...det, entity_text: text || '[onbekend]' };
	});
}
