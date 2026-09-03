/**
 * Resolves entity text from bounding box coordinates using local text extraction.
 *
 * This is the "client-side join" between server detection metadata (bboxes)
 * and locally-held text extraction data. The server deliberately does not
 * store entity_text — the client reconstructs it here.
 */

import type { BoundingBox, ExtractionResult, ExtractedTextItem } from '$lib/types';
import { measureText } from './glyph-metrics';
import { readingAxis, type ReadingAxis } from './reading-axis';

// Tolerance along the reading direction, in PDF points — a few points of
// slack is safe because text items on the same line never occupy the same
// range along it. Matching across the reading direction uses the text
// item's *center* against the bbox's range (no tolerance): an AABB overlap
// with any cross-axis tolerance at all accidentally picks up adjacent
// lines, because PyMuPDF/pdf.js line boxes include ascender/descender
// padding that causes a 1–2pt overlap between consecutive lines. This used
// to surface as a detection card showing e.g. "Postbus 9100, 2300 PC
// Leiden\nTelefoon: 071 516 50 00" for a bbox that only covers the
// "Postbus" line — the card then contradicted what the PDF overlay
// actually highlighted.
//
// #87 — both axes come from `reading-axis.ts` rather than being hard-coded
// to x and y. On a /Rotate 90 page a line runs down the screen, so the
// "same line" test has to compare x and the slicing below has to cut y.
const ALONG_TOLERANCE = 2.0;

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
const SAME_LINE_TOLERANCE = 2;

/** Is the item's line the one this bbox sits on? */
function overlapsAcross(axis: ReadingAxis, bbox: BoundingBox, item: ExtractedTextItem): boolean {
	const center = axis.crossCenter(item);
	const range = axis.cross(bbox);
	return center >= range.start && center <= range.end;
}

/** Does the item overlap the bbox along the reading direction? */
function overlapsAlong(axis: ReadingAxis, bbox: BoundingBox, item: ExtractedTextItem): boolean {
	const a = axis.along(item);
	const b = axis.along(bbox);
	return a.start < b.end + ALONG_TOLERANCE && a.end > b.start - ALONG_TOLERANCE;
}

/**
 * Return the substring of `item.text` that corresponds to the portion
 * of the item sitting inside `bbox`.
 *
 * If the item is fully contained within the bbox (within a small
 * tolerance), the entire text is returned. Otherwise the item's
 * characters are weighted by Helvetica AFM advance widths and the
 * slice is chosen so the overlap along the reading direction lines up
 * with whole characters — the same weighting the backend uses in
 * `_narrow_bbox_to_substring` when it computed this bbox in the first
 * place.
 *
 * #87 — measured along `axis`, not along x. Cutting along x on a
 * /Rotate 90 page produced a band across the whole line instead of a box
 * around the term: over-redaction rather than a leak, but it swallowed
 * the rest of the sentence and clipped the line height.
 */
function sliceItemTextByBbox(
	axis: ReadingAxis,
	bbox: BoundingBox,
	item: ExtractedTextItem
): string {
	const itemSpan = axis.along(item);
	const bboxSpan = axis.along(bbox);
	const itemLength = itemSpan.end - itemSpan.start;
	if (itemLength <= 0 || item.text.length === 0) return item.text;

	const contained =
		itemSpan.start >= bboxSpan.start - CONTAINED_ITEM_TOLERANCE &&
		itemSpan.end <= bboxSpan.end + CONTAINED_ITEM_TOLERANCE;
	if (contained) return item.text;

	const overlapStart = Math.max(itemSpan.start, bboxSpan.start);
	const overlapEnd = Math.min(itemSpan.end, bboxSpan.end);
	if (overlapEnd <= overlapStart) return '';

	// AFM-weighted cumulative positions in item-local coordinates, shared
	// with the reverse translation in `search-redact.ts`.
	const ruler = measureText(item.text, itemLength);
	if (!ruler) return item.text;
	const { chars, cumulative } = ruler;

	const targetStart = overlapStart - itemSpan.start;
	const targetEnd = overlapEnd - itemSpan.start;

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

		const axis = readingAxis(page.rotation);
		const matchingItems = page.textItems
			.filter((item) => overlapsAcross(axis, bbox, item) && overlapsAlong(axis, bbox, item))
			.sort((a, b) => {
				// Sort in reading order: line by line, then along the line.
				const lineDiff = axis.cross(a).start - axis.cross(b).start;
				if (Math.abs(lineDiff) > SAME_LINE_TOLERANCE) return lineDiff;
				return axis.along(a).start - axis.along(b).start;
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
		//
		// #87 — "same line" and "touching" are measured on the reading axis.
		// Since #84 the items are in viewer space, so on a /Rotate 90 page the
		// old y-based same-line test compared two points on the same *column*
		// and never matched, which brought "W i l l e m i j n" back to the
		// sidebar for exactly the monospace PDFs this heuristic exists for.
		let joined = '';
		let prev: ExtractedTextItem | null = null;
		for (const item of matchingItems) {
			const slice = sliceItemTextByBbox(axis, bbox, item);
			if (!slice) continue;
			if (prev === null) {
				joined = slice;
			} else {
				const sameLine =
					Math.abs(axis.cross(item).start - axis.cross(prev).start) < SAME_LINE_TOLERANCE;
				const touching =
					sameLine && axis.along(item).start - axis.along(prev).end < TOUCHING_GAP;
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
 * Rebuild the text the *server* saw, so `start_char`/`end_char` on a
 * detection can be sliced back into a term.
 *
 * `extraction.fullText` is not usable for this: the extractor trims the
 * combined string (to detect a scanned PDF), which shifts every offset
 * when page 1 starts with whitespace. The server joins the untrimmed
 * page texts with "\n\n" (`extraction_from_client_data` in
 * `pdf_engine.py`), so mirror exactly that.
 */
function serverJoinedText(extraction: ExtractionResult): string {
	return extraction.pages.map((p) => p.fullText).join('\n\n');
}

/**
 * Recover the term for a detection that could not be placed, from its
 * character offsets in the server-joined text. Returns null for
 * reviewer-authored rows (`manual`, `search_redact`), which carry no
 * offsets, and for offsets that fall outside the local text — a
 * mismatch between what the server analyzed and what this browser
 * extracted, where any slice would be a guess.
 */
function textFromOffsets(
	det: { start_char?: number | null; end_char?: number | null },
	joined: string
): string | null {
	const { start_char: start, end_char: end } = det;
	if (typeof start !== 'number' || typeof end !== 'number') return null;
	if (start < 0 || end <= start || end > joined.length) return null;
	const slice = joined.slice(start, end).trim();
	return slice.length > 0 ? slice : null;
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
 * preserved verbatim, and rows whose `source` marks them
 * reviewer-authored are never dropped at all — a manual area selection
 * carries no text and no overlapping items, and must survive a refresh
 * regardless.
 *
 * #78 — dropping is right, dropping *silently* is not: the reviewer
 * ends up with a document where the tool found a name it never showed
 * them. Every dropped row is therefore reported in `unplaced`, with
 * the term recovered from `start_char`/`end_char` where possible, so
 * the review screen can name it and point at search-and-redact.
 */
// Characters peeled off the tail of URL-like resolved texts. pdf.js
// reports a whole line as one text item and our proportional bbox
// slicing rounds up one character when the bbox ends a hair past the
// URL — which leaks the trailing sentence period into the sidebar
// card ("https://example.com."). Mirrors the server-side URL strip in
// `_tier1.py`.
const URL_TRAILING_PUNCT = /[.,;:!?)\]}>]+$/;

export interface UnplacedDetection {
	id: string | null;
	entity_type: string | null;
	tier: string | null;
	/**
	 * 0-indexed page (PyMuPDF convention), when the row carries a bbox at
	 * all. Null for the no-bbox case, where there is nothing to point at.
	 */
	page: number | null;
	/**
	 * The detected term, recovered from the character offsets against the
	 * locally extracted text. Null when the row carries no offsets or the
	 * offsets do not fit the local text — the reviewer then only learns
	 * that *something* went unplaced, which still beats silence.
	 */
	text: string | null;
	reason: 'no_bbox' | 'no_text_match';
}

export interface ResolvedDetections<T> {
	detections: T[];
	unplaced: UnplacedDetection[];
	/**
	 * The rows behind `unplaced`, verbatim and in the same order — what was
	 * dropped from `detections`, not a summary of it.
	 *
	 * #85 — the caller has to be able to persist them. `setFromAnalyze`
	 * writes the server's full answer to IndexedDB, but every later
	 * `persistDetections` writes only the placed rows, so a single
	 * accept/reject silently narrowed the cache and the banner was gone
	 * after the next refresh. Handing the rows back lets the store keep
	 * the cache complete and rebuild the banner on hydrate instead of
	 * remembering it separately.
	 */
	dropped: T[];
}

type Resolvable = {
	id?: string;
	entity_text?: string;
	bounding_boxes: BoundingBox[];
	entity_type?: string;
	tier?: string;
	source?: string;
	start_char?: number | null;
	end_char?: number | null;
};

export function resolveEntityTexts<T extends Resolvable>(
	detections: T[],
	extraction: ExtractionResult
): ResolvedDetections<T> {
	const out: T[] = [];
	const unplaced: UnplacedDetection[] = [];
	const dropped: T[] = [];
	// Only built when something actually goes unplaced — the join is a
	// full-document string copy and the happy path never needs it.
	let joined: string | null = null;
	const report = (det: T, reason: UnplacedDetection['reason']) => {
		joined ??= serverJoinedText(extraction);
		dropped.push(det);
		unplaced.push({
			id: det.id ?? null,
			entity_type: det.entity_type ?? null,
			tier: det.tier ?? null,
			page: det.bounding_boxes?.[0]?.page ?? null,
			text: textFromOffsets(det, joined),
			reason
		});
	};

	for (const det of detections) {
		if (det.entity_text && det.entity_text !== '[redacted]') {
			out.push(det);
			continue;
		}
		// Reviewer-authored rows are decisions, not detections: the box is
		// where the reviewer put it, so it is never dropped and never
		// reported as unplaced. Resolution still runs over it, because
		// `persistDetections` strips `entity_text` before writing to
		// IndexedDB — after a refresh a search-and-redact hit or a split
		// half arrives here textless, and only its bbox can restore the
		// label the sidebar shows. An *area* selection (Shift+drag over a
		// signature or stamp) has no text under it at all: it keeps its
		// empty label and, before #78, was thrown away on every refresh.
		const reviewerAuthored = det.source === 'manual' || det.source === 'search_redact';
		const bboxes = det.bounding_boxes ?? [];
		if (bboxes.length === 0) {
			if (reviewerAuthored) {
				out.push(det);
				continue;
			}
			report(det, 'no_bbox');
			continue;
		}
		let text = findTextForBboxes(bboxes, extraction);
		if (!text) {
			if (reviewerAuthored) {
				out.push(det);
				continue;
			}
			report(det, 'no_text_match');
			continue;
		}
		if (det.entity_type === 'url' || /^https?:\/\//i.test(text)) {
			text = text.replace(URL_TRAILING_PUNCT, '');
		}
		out.push({ ...det, entity_text: text });
	}
	return { detections: out, unplaced, dropped };
}
