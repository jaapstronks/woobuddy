import { describe, it, expect } from 'vitest';
import { searchDocument } from './search-redact';
import type { BoundingBox, ExtractionResult } from '$lib/types';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

/**
 * Build an ExtractionResult from a list of pages, where each page is a list
 * of `{ text, x }` tuples. Items on the same page sit on a single visual
 * line (y in [100, 110]) with width = text.length * 6 px, advancing
 * horizontally. This keeps the geometry obvious so tests can assert bboxes
 * without doing arithmetic.
 */
function makeExtraction(
	pages: { text: string; x: number }[][]
): ExtractionResult {
	const pageObjs = pages.map((items, pageIdx) => {
		const textItems = items.map((it) => ({
			text: it.text,
			x0: it.x,
			y0: 100,
			x1: it.x + it.text.length * 6,
			y1: 110
		}));
		const fullText = items.map((it) => it.text).join(' ');
		return { pageNumber: pageIdx, fullText, textItems };
	});
	return {
		pages: pageObjs,
		pageCount: pages.length,
		fullText: pageObjs.map((p) => p.fullText).join('\n\n')
	};
}

function box(page: number, x0: number, x1: number): BoundingBox {
	return { page, x0, y0: 100, x1, y1: 110 };
}

/**
 * Single-page extraction with items spread over several visual lines,
 * 20px apart starting at y=100. Needed for the line-break cases in #85 —
 * `makeExtraction` puts everything on one line, which cannot express a
 * name that runs past the right margin onto the next.
 */
function makeLines(lines: { text: string; x: number }[][]): ExtractionResult {
	const textItems = lines.flatMap((items, lineIdx) =>
		items.map((it) => ({
			text: it.text,
			x0: it.x,
			y0: 100 + lineIdx * 20,
			x1: it.x + it.text.length * 6,
			y1: 110 + lineIdx * 20
		}))
	);
	const fullText = textItems.map((it) => it.text).join(' ');
	const page = { pageNumber: 0, fullText, textItems };
	return { pages: [page], pageCount: 1, fullText };
}

function lineBox(page: number, line: number, x0: number, x1: number): BoundingBox {
	return { page, x0, y0: 100 + line * 20, x1, y1: 110 + line * 20 };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('searchDocument', () => {
	it('returns no results for short or empty queries', () => {
		const extraction = makeExtraction([[{ text: 'Van', x: 0 }]]);
		expect(searchDocument('', extraction, [])).toEqual([]);
		expect(searchDocument(' ', extraction, [])).toEqual([]);
		expect(searchDocument('a', extraction, [])).toEqual([]);
	});

	it('finds exact matches case-insensitively across items on a line', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Namens', x: 0 },
				{ text: 'Van', x: 50 },
				{ text: 'der', x: 80 },
				{ text: 'Berg,', x: 110 },
				{ text: 'gemeente', x: 160 }
			]
		]);

		const occs = searchDocument('van der berg', extraction, []);
		expect(occs).toHaveLength(1);
		expect(occs[0].page).toBe(0);
		expect(occs[0].matchText.toLowerCase()).toBe('van der berg');
		// Items on the same y-line merge into one continuous bbox spanning
		// from "Van" (x=50) through the end of "Berg" (x=110 + 5*6 = 140).
		expect(occs[0].bboxes).toHaveLength(1);
		expect(occs[0].bboxes[0].x0).toBe(50);
		expect(occs[0].bboxes[0].x1).toBeGreaterThanOrEqual(140);
	});

	it('returns one occurrence per visible instance across pages', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Van', x: 0 },
				{ text: 'der', x: 30 },
				{ text: 'Berg', x: 60 }
			],
			[
				{ text: 'Rapport', x: 0 },
				{ text: 'Van', x: 60 },
				{ text: 'der', x: 90 },
				{ text: 'Berg', x: 120 }
			]
		]);
		const occs = searchDocument('Van der Berg', extraction, []);
		expect(occs).toHaveLength(2);
		expect(occs.map((o) => o.page)).toEqual([0, 1]);
	});

	it('normalizes whitespace runs in the query', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Van', x: 0 },
				{ text: 'der', x: 30 },
				{ text: 'Berg', x: 60 }
			]
		]);
		const occs = searchDocument('  Van   der   Berg  ', extraction, []);
		expect(occs).toHaveLength(1);
	});

	it('reports zero occurrences when nothing matches', () => {
		const extraction = makeExtraction([[{ text: 'Rapport', x: 0 }]]);
		expect(searchDocument('Van der Berg', extraction, [])).toEqual([]);
	});

	it('flags matches overlapped by existing detections as alreadyRedacted', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Van', x: 0 },
				{ text: 'der', x: 30 },
				{ text: 'Berg', x: 60 }
			]
		]);
		const existing = [{ bounding_boxes: [box(0, 0, 200)] }];
		const occs = searchDocument('Van der Berg', extraction, existing);
		expect(occs).toHaveLength(1);
		expect(occs[0].alreadyRedacted).toBe(true);
	});

	it('does not flag non-overlapping detections as alreadyRedacted', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Van', x: 0 },
				{ text: 'der', x: 30 },
				{ text: 'Berg', x: 60 }
			]
		]);
		// Existing box far to the right of the actual match (0..84).
		const existing = [{ bounding_boxes: [box(0, 500, 600)] }];
		const occs = searchDocument('Van der Berg', extraction, existing);
		expect(occs[0].alreadyRedacted).toBe(false);
	});

	// #85 — the "kon niet geplaatst worden" banner sends the reviewer here
	// with exactly this shape of term: a name the analyzer found across a
	// line end, which therefore has no box of its own. Marking it handled
	// because the tail happens to share a line with an auto-redacted
	// e-mail leaves the head of the name readable and takes away the only
	// route the banner offered.
	it('keeps a match redactable when only some of its lines are covered', () => {
		const extraction = makeLines([
			[
				{ text: 'medewerker', x: 0 },
				{ text: 'Pieter', x: 70 }
			],
			[
				{ text: 'de', x: 0 },
				{ text: 'Vries,', x: 20 },
				{ text: 'p.devries@voorbeeld.nl', x: 60 }
			]
		]);
		// Auto-redacted e-mail: covers the whole second line, nothing of the first.
		const existing = [
			{ bounding_boxes: [lineBox(0, 1, 0, 200)], review_status: 'auto_accepted' as const }
		];
		const occs = searchDocument('Pieter de Vries', extraction, existing);
		expect(occs).toHaveLength(1);
		expect(occs[0].bboxes).toHaveLength(2);
		expect(occs[0].alreadyRedacted).toBe(false);
	});

	it('flags a multi-line match when every line is covered', () => {
		const extraction = makeLines([
			[{ text: 'Pieter', x: 0 }],
			[{ text: 'de Vries', x: 0 }]
		]);
		const existing = [
			{ bounding_boxes: [lineBox(0, 0, 0, 200)], review_status: 'accepted' as const },
			{ bounding_boxes: [lineBox(0, 1, 0, 200)], review_status: 'accepted' as const }
		];
		const occs = searchDocument('Pieter de Vries', extraction, existing);
		expect(occs).toHaveLength(1);
		expect(occs[0].alreadyRedacted).toBe(true);
	});

	// A rejected row is the reviewer saying "leave this readable". Counting
	// its box as cover answered a search for that very term with "al
	// gelakt" while the page stayed readable.
	it('ignores rejected detections when flagging alreadyRedacted', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Van', x: 0 },
				{ text: 'der', x: 30 },
				{ text: 'Berg', x: 60 }
			]
		]);
		const existing = [{ bounding_boxes: [box(0, 0, 200)], review_status: 'rejected' as const }];
		const occs = searchDocument('Van der Berg', extraction, existing);
		expect(occs).toHaveLength(1);
		expect(occs[0].alreadyRedacted).toBe(false);
	});

	it('includes surrounding context with the match in the middle', () => {
		const extraction = makeExtraction([
			[
				{ text: 'Betreft:', x: 0 },
				{ text: 'briefing', x: 60 },
				{ text: 'van', x: 130 },
				{ text: 'de', x: 170 },
				{ text: 'heer', x: 200 },
				{ text: 'Pietersen', x: 240 },
				{ text: 'namens', x: 320 },
				{ text: 'gemeente', x: 390 }
			]
		]);
		const occs = searchDocument('Pietersen', extraction, []);
		expect(occs).toHaveLength(1);
		expect(occs[0].context.toLowerCase()).toContain('pietersen');
		// Context is ~24 chars on each side; the trailing ellipsis only
		// appears when we've clipped the page text.
		expect(occs[0].context.length).toBeGreaterThan('Pietersen'.length);
	});

	it('handles null extraction gracefully', () => {
		expect(searchDocument('anything', null, [])).toEqual([]);
	});

	it('does not emit overlapping matches for the same substring', () => {
		// "aaaa" contains overlapping "aa" matches if we stepped by 1 — the
		// implementation steps past each match so the reviewer gets two,
		// not three.
		const extraction = makeExtraction([[{ text: 'aaaa', x: 0 }]]);
		const occs = searchDocument('aa', extraction, []);
		expect(occs).toHaveLength(2);
	});
});
