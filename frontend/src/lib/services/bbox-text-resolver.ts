/**
 * Resolves entity text from bounding box coordinates using local text extraction.
 *
 * This is the "client-side join" between server detection metadata (bboxes)
 * and locally-held text extraction data. The server deliberately does not
 * store entity_text — the client reconstructs it here.
 */

import type { BoundingBox, ExtractionResult, ExtractedTextItem } from '$lib/types';

const TOLERANCE = 2.0; // coordinate tolerance in PDF points for overlap matching

function overlaps(bbox: BoundingBox, item: ExtractedTextItem): boolean {
	return (
		item.x0 < bbox.x1 + TOLERANCE &&
		item.x1 > bbox.x0 - TOLERANCE &&
		item.y0 < bbox.y1 + TOLERANCE &&
		item.y1 > bbox.y0 - TOLERANCE
	);
}

/**
 * Find the text content that corresponds to a set of bounding boxes.
 * Matches text items from the extraction that overlap spatially with the bboxes.
 */
export function findTextForBboxes(
	bboxes: BoundingBox[],
	extraction: ExtractionResult
): string {
	const parts: string[] = [];

	for (const bbox of bboxes) {
		const page = extraction.pages.find((p) => p.pageNumber === bbox.page);
		if (!page) continue;

		const matching = page.textItems
			.filter((item) => overlaps(bbox, item))
			.sort((a, b) => {
				// Sort by position: top-to-bottom, then left-to-right
				const yDiff = a.y0 - b.y0;
				if (Math.abs(yDiff) > 2) return yDiff;
				return a.x0 - b.x0;
			})
			.map((item) => item.text);

		if (matching.length > 0) {
			parts.push(matching.join(' '));
		}
	}

	return parts.join(' ');
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
