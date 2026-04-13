/**
 * Search-and-Redact (#09) — client-side document search.
 *
 * Operates entirely on the `ExtractionResult` already in memory from
 * `pdf-text-extractor.ts`. No server round-trip: the server never stored
 * the text in the first place.
 *
 * Strategy
 * --------
 * 1. For each page, concatenate trimmed `textItems` with a single space
 *    separator into one searchable string, tracking each item's
 *    `[start, end)` offset in that string.
 * 2. Lowercase the page string and the query, collapsing runs of whitespace
 *    in the query (the concatenation already produces single spaces).
 * 3. `indexOf` scan; for each match, collect the items whose offsets overlap
 *    the match range and merge their bboxes into one box per visual line
 *    (same rule as manual text selection in #06).
 * 4. Flag matches whose bboxes overlap ≥50% with any existing detection —
 *    the UI shows those as "already redacted" so the reviewer doesn't
 *    double-redact.
 *
 * This is an exact-match search with case-insensitive + whitespace-normalized
 * matching only. The todo defers fuzzy Dutch name-particle matching to P3.
 */

import type { BoundingBox, ExtractedTextItem, ExtractionResult } from '$lib/types';

export interface SearchOccurrence {
	/** Stable id derived from page + offset — safe as a list key and as a Set entry. */
	id: string;
	page: number;
	/** Original (case-preserved) matched text pulled from the concatenated page string. */
	matchText: string;
	/** ~40 chars of surrounding context with the match in the middle. */
	context: string;
	/** Merged per-line bboxes in PDF points, ready to post as a manual detection. */
	bboxes: BoundingBox[];
	/** True if the match's area is already covered by an existing detection. */
	alreadyRedacted: boolean;
}

const CONTEXT_CHARS = 24;

/**
 * Normalize the query: lowercase + collapse whitespace runs into single
 * spaces + trim. The page text we search against already has single-space
 * separators from `pdf-text-extractor.ts`, so only the query needs collapsing.
 */
function normalizeQuery(query: string): string {
	return query.toLowerCase().replace(/\s+/g, ' ').trim();
}

/**
 * Build a page-string and per-item offset map. Shape is kept local to the
 * search call — the extraction itself already lives in the detection store,
 * so caching an index across calls would just duplicate state.
 */
interface PageIndex {
	pageNumber: number;
	text: string; // original case, space-joined
	lower: string; // lowercased version for matching
	segments: { item: ExtractedTextItem; start: number; end: number }[];
}

function indexPage(page: ExtractionResult['pages'][number]): PageIndex {
	const segments: PageIndex['segments'] = [];
	let text = '';
	for (let i = 0; i < page.textItems.length; i++) {
		const item = page.textItems[i];
		if (i > 0) text += ' ';
		const start = text.length;
		text += item.text;
		segments.push({ item, start, end: text.length });
	}
	return {
		pageNumber: page.pageNumber,
		text,
		lower: text.toLowerCase(),
		segments
	};
}

function itemToBox(item: ExtractedTextItem, page: number): BoundingBox {
	return { page, x0: item.x0, y0: item.y0, x1: item.x1, y1: item.y1 };
}

/**
 * Merge bboxes that sit on the same visual line into one continuous bar.
 * Matches the rule used for manual text selection: compare y0/y1 within a
 * 2-point tolerance and union the horizontal span. Unlike
 * `mergeHorizontallyAdjacent` in selection-bbox.ts, we don't require
 * touching/adjacent boxes because a search hit can span words separated by
 * a space (distinct pdf.js items with a small horizontal gap).
 */
function mergeLineBboxes(bboxes: BoundingBox[]): BoundingBox[] {
	if (bboxes.length <= 1) return bboxes.map((b) => ({ ...b }));
	const sorted = [...bboxes].sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
	const merged: BoundingBox[] = [];
	for (const b of sorted) {
		const last = merged[merged.length - 1];
		if (last && Math.abs(last.y0 - b.y0) < 2 && Math.abs(last.y1 - b.y1) < 2) {
			last.x0 = Math.min(last.x0, b.x0);
			last.x1 = Math.max(last.x1, b.x1);
			last.y0 = Math.min(last.y0, b.y0);
			last.y1 = Math.max(last.y1, b.y1);
		} else {
			merged.push({ ...b });
		}
	}
	return merged;
}

/**
 * Returns true if ≥50% of `area`'s bbox is already covered by `cover`.
 * We measure relative to `area` (the search hit) so a huge pre-existing
 * redaction that overlaps a small match still counts as "already redacted".
 */
function bboxesOverlap(area: BoundingBox, cover: BoundingBox): boolean {
	if (area.page !== cover.page) return false;
	const ix0 = Math.max(area.x0, cover.x0);
	const iy0 = Math.max(area.y0, cover.y0);
	const ix1 = Math.min(area.x1, cover.x1);
	const iy1 = Math.min(area.y1, cover.y1);
	if (ix1 <= ix0 || iy1 <= iy0) return false;
	const inter = (ix1 - ix0) * (iy1 - iy0);
	const areaSize = Math.max(1e-6, (area.x1 - area.x0) * (area.y1 - area.y0));
	return inter / areaSize >= 0.5;
}

function buildContext(text: string, start: number, end: number): string {
	const before = Math.max(0, start - CONTEXT_CHARS);
	const after = Math.min(text.length, end + CONTEXT_CHARS);
	const leading = before > 0 ? '…' : '';
	const trailing = after < text.length ? '…' : '';
	// Collapse any embedded newlines (there shouldn't be any in the joined
	// page text, but defensive against future changes in the extractor).
	const raw = text.slice(before, after).replace(/\s+/g, ' ');
	return `${leading}${raw}${trailing}`;
}

/**
 * Run a search against the currently-extracted document text.
 *
 * @param query  Reviewer's needle. Short queries (< 2 chars after normalization)
 *               are treated as "no query" and return `[]` — single letters
 *               would match hundreds of times on any page and swamp the UI.
 * @param extraction  The per-page text + item bboxes from `pdf-text-extractor`.
 * @param existingDetections  Existing detections to flag overlap against.
 */
export function searchDocument(
	query: string,
	extraction: ExtractionResult | null,
	existingDetections: { bounding_boxes: BoundingBox[] | null }[]
): SearchOccurrence[] {
	if (!extraction) return [];
	const needle = normalizeQuery(query);
	if (needle.length < 2) return [];

	// Flatten existing detection bboxes once so we don't re-scan for every match.
	const existingBoxes: BoundingBox[] = [];
	for (const det of existingDetections) {
		if (!det.bounding_boxes) continue;
		for (const b of det.bounding_boxes) existingBoxes.push(b);
	}

	const occurrences: SearchOccurrence[] = [];

	for (const rawPage of extraction.pages) {
		const pageIndex = indexPage(rawPage);
		if (pageIndex.lower.length < needle.length) continue;

		let scanFrom = 0;
		while (scanFrom <= pageIndex.lower.length - needle.length) {
			const found = pageIndex.lower.indexOf(needle, scanFrom);
			if (found === -1) break;
			const matchEnd = found + needle.length;

			const hits = pageIndex.segments.filter((s) => s.start < matchEnd && s.end > found);
			if (hits.length === 0) {
				scanFrom = found + 1;
				continue;
			}

			const itemBboxes = hits.map((h) => itemToBox(h.item, pageIndex.pageNumber));
			const bboxes = mergeLineBboxes(itemBboxes);

			const alreadyRedacted = bboxes.some((bb) =>
				existingBoxes.some((db) => bboxesOverlap(bb, db))
			);

			occurrences.push({
				id: `p${pageIndex.pageNumber}-o${found}`,
				page: pageIndex.pageNumber,
				matchText: pageIndex.text.slice(found, matchEnd),
				context: buildContext(pageIndex.text, found, matchEnd),
				bboxes,
				alreadyRedacted
			});

			// Step past this match. Overlapping matches would be confusing for
			// bulk redaction (the reviewer expects one row per visible occurrence).
			scanFrom = matchEnd;
		}
	}

	return occurrences;
}
