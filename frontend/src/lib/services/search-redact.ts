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
 *    the match range, narrow each item's box to the matched characters
 *    (AFM-weighted, see `segmentToBox`), and merge those into one box per
 *    visual line (same rule as manual text selection in #06).
 * 4. Flag matches whose bboxes *all* overlap ≥50% with an existing detection
 *    that will actually produce a black bar — the UI shows those as "already
 *    redacted" so the reviewer doesn't double-redact.
 *
 * This is an exact-match search with case-insensitive + whitespace-normalized
 * matching only. The todo defers fuzzy Dutch name-particle matching to P3.
 */

import type {
	BoundingBox,
	ExtractedTextItem,
	ExtractionResult,
	ReviewStatus
} from '$lib/types';
import { charIndexAtOffset, measureText } from './glyph-metrics';
import { readingAxis, type ReadingAxis } from './reading-axis';

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
	/**
	 * True if *every* line of the match is already covered by a detection
	 * that will be redacted. A match that is only partly covered stays
	 * redactable: see {@link searchDocument}.
	 */
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
	/** Which viewer axis this page's text reads along (#87). */
	axis: ReadingAxis;
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
		segments,
		axis: readingAxis(page.rotation)
	};
}

/**
 * Box the part of `segment` that the match `[matchStart, matchEnd)` actually
 * covers, in page-string offsets.
 *
 * pdf.js hands back one text item per *line* for plenty of real documents
 * (scanner output, most letter templates), so taking the item's own box would
 * black out the whole sentence around the hit — redacting without grounds.
 * The item's characters are weighted by AFM advance widths, the same
 * weighting `sliceItemTextByBbox` uses for the reverse translation, and the
 * box is cut back to the matched span.
 *
 * A match that runs over a line end gets one narrowed box per item: the first
 * from the start of the match to the end of its item, the second from the
 * start of its item to the end of the match. That falls out of clamping the
 * match range to the segment rather than being a separate case.
 *
 * #87 — the cut runs along the page's reading direction, which is only x at
 * /Rotate 0. Cutting along x on a /Rotate 90 page turned the box into a band
 * across the line, blacking out the whole sentence around the hit.
 */
function segmentToBox(
	axis: ReadingAxis,
	segment: PageIndex['segments'][number],
	page: number,
	matchStart: number,
	matchEnd: number
): BoundingBox {
	const item = segment.item;
	const fullBox = { page, x0: item.x0, y0: item.y0, x1: item.x1, y1: item.y1 };

	const startInItem = Math.max(0, matchStart - segment.start);
	const endInItem = Math.min(item.text.length, matchEnd - segment.start);
	// The whole item is inside the match — nothing to narrow, and skipping
	// the measurement keeps the common word-per-item case exact.
	if (startInItem <= 0 && endInItem >= item.text.length) return fullBox;
	if (endInItem <= startInItem) return fullBox;

	const span = axis.along(item);
	const ruler = measureText(item.text, span.end - span.start);
	if (!ruler) return fullBox;

	const startIdx = charIndexAtOffset(ruler, startInItem);
	const endIdx = charIndexAtOffset(ruler, endInItem);
	if (endIdx <= startIdx) return fullBox;

	return axis.withAlong(
		fullBox,
		span.start + ruler.cumulative[startIdx],
		span.start + ruler.cumulative[endIdx]
	);
}

/**
 * Merge bboxes that sit on the same visual line into one continuous bar.
 * Matches the rule used for manual text selection: compare the two edges
 * across the reading direction within a 2-point tolerance and union the span
 * along it. Unlike `mergeHorizontallyAdjacent` in selection-bbox.ts, we don't
 * require touching/adjacent boxes because a search hit can span words
 * separated by a space (distinct pdf.js items with a small gap).
 *
 * #87 — on a /Rotate 90 page a line runs down the screen, so the old y-based
 * "same line" test compared boxes stacked in a column: two halves of one hit
 * came back as separate bars, and two words that happened to share a y were
 * merged into a bar spanning the space between two different lines.
 */
function mergeLineBboxes(axis: ReadingAxis, bboxes: BoundingBox[]): BoundingBox[] {
	if (bboxes.length <= 1) return bboxes.map((b) => ({ ...b }));
	const sorted = [...bboxes].sort(
		(a, b) => axis.cross(a).start - axis.cross(b).start || axis.along(a).start - axis.along(b).start
	);
	const merged: BoundingBox[] = [];
	for (const b of sorted) {
		const last = merged[merged.length - 1];
		const lastCross = last ? axis.cross(last) : null;
		const cross = axis.cross(b);
		if (
			last &&
			lastCross &&
			Math.abs(lastCross.start - cross.start) < 2 &&
			Math.abs(lastCross.end - cross.end) < 2
		) {
			const union = {
				...last,
				x0: Math.min(last.x0, b.x0),
				x1: Math.max(last.x1, b.x1),
				y0: Math.min(last.y0, b.y0),
				y1: Math.max(last.y1, b.y1)
			};
			merged[merged.length - 1] = union;
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
 *               Rows the reviewer rejected are skipped — see below.
 */
export function searchDocument(
	query: string,
	extraction: ExtractionResult | null,
	existingDetections: { bounding_boxes: BoundingBox[] | null; review_status?: ReviewStatus }[]
): SearchOccurrence[] {
	if (!extraction) return [];
	const needle = normalizeQuery(query);
	if (needle.length < 2) return [];

	// Flatten existing detection bboxes once so we don't re-scan for every
	// match. A rejected row is the reviewer saying "leave this visible", so
	// its box covers nothing: counting it would answer a search for that
	// very term with "al gelakt" while the page stays readable (#85).
	const existingBoxes: BoundingBox[] = [];
	for (const det of existingDetections) {
		if (!det.bounding_boxes) continue;
		if (det.review_status === 'rejected') continue;
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

			const itemBboxes = hits.map((h) =>
				segmentToBox(pageIndex.axis, h, pageIndex.pageNumber, found, matchEnd)
			);
			const bboxes = mergeLineBboxes(pageIndex.axis, itemBboxes);

			// Every line has to be covered, not just one. A name broken over
			// a line end is exactly the case the "kon niet geplaatst worden"
			// banner sends the reviewer here for (#78/#85): the second half
			// often shares a line with an auto-redacted e-mail or phone
			// number, and with `.some()` that one covered line marked the
			// whole match handled — leaving the first half unredacted with
			// no way left to act on it.
			const alreadyRedacted = bboxes.every((bb) =>
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
