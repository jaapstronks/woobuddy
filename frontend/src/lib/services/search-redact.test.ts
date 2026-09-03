import { describe, it, expect } from 'vitest';
import { searchDocument } from './search-redact';
import type { BoundingBox, ExtractionResult, PageRotation } from '$lib/types';
import { ROTATIONS, rotateBox } from './testing/viewer-rotation';

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
 * Independent re-derivation of the AFM-weighted x span of `text[from, to)`
 * inside an item drawn from `x0` to `x1`. Deliberately does not import
 * `glyph-metrics`: the tests assert the geometry a reviewer sees, so they
 * carry their own (much smaller) width table for the glyphs the fixtures
 * actually use rather than trusting the module under test to weigh itself.
 */
function afmSpan(
	text: string,
	x0: number,
	x1: number,
	from: number,
	to: number
): { x0: number; x1: number } {
	// Helvetica advance widths, 1/1000 em, for the ASCII the fixtures use.
	const w: Record<string, number> = {
		' ': 278, ',': 278, '.': 278, '@': 1015,
		P: 667, U: 722, V: 667,
		a: 556, b: 556, c: 500, d: 556, e: 556, f: 278, g: 556, h: 556, i: 222,
		j: 222, k: 500, l: 222, m: 833, n: 556, o: 556, p: 556, q: 556, r: 333,
		s: 500, t: 278, u: 556, v: 500, w: 722, x: 500, y: 500, z: 500
	};
	const width = (ch: string) => w[ch] ?? 500;
	let total = 0;
	for (const ch of text) total += width(ch);
	const scale = (x1 - x0) / total;
	let before = 0;
	for (let i = 0; i < from; i++) before += width(text[i]);
	let upto = before;
	for (let i = from; i < to; i++) upto += width(text[i]);
	return { x0: x0 + before * scale, x1: x0 + upto * scale };
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
		// Items on the same y-line merge into one continuous bbox starting at
		// "Van" (x=50). Since #86 the right edge stops at the end of "Berg"
		// rather than at the item edge (140): the trailing comma of "Berg,"
		// is outside the match and has no business being blacked out.
		expect(occs[0].bboxes).toHaveLength(1);
		expect(occs[0].bboxes[0].x0).toBe(50);
		expect(occs[0].bboxes[0].x1).toBeGreaterThan(134);
		expect(occs[0].bboxes[0].x1).toBeLessThan(140);
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

	// #86 — pdf.js hands back one item per line for scanner output and most
	// letter templates. Boxing the whole item blacked out the surrounding
	// sentence: redacting without grounds, on every search the reviewer runs.
	it('narrows the bbox to the match inside a line-wide text item', () => {
		const line = 'Uw verzoek is behandeld door onze medewerker Pieter de Vries.';
		const extraction = makeExtraction([[{ text: line, x: 40 }]]);

		const occs = searchDocument('Pieter de Vries', extraction, []);
		expect(occs).toHaveLength(1);
		expect(occs[0].bboxes).toHaveLength(1);

		const bbox = occs[0].bboxes[0];
		const itemX0 = 40;
		const itemX1 = 40 + line.length * 6;
		const expected = afmSpan(line, itemX0, itemX1, line.indexOf('Pieter'), line.indexOf('.'));
		expect(bbox.x0).toBeCloseTo(expected.x0, 5);
		expect(bbox.x1).toBeCloseTo(expected.x1, 5);
		// And the reviewer-visible claim behind those numbers: the bar covers
		// the name, not the sentence it sits in. The 44 characters of
		// "Uw verzoek … medewerker " stay outside it, and so does the period.
		const charWidth = (itemX1 - itemX0) / line.length;
		expect(bbox.x0).toBeGreaterThan(itemX0 + charWidth * 30);
		expect(bbox.x1).toBeLessThan(itemX1);
		expect(bbox.x1 - bbox.x0).toBeLessThan((itemX1 - itemX0) * 0.4);
	});

	it('narrows each line of a match that runs over a line end', () => {
		const first = 'Uw verzoek is behandeld door medewerker Pieter';
		const second = 'de Vries, bereikbaar op p.devries@voorbeeld.nl';
		const extraction = makeLines([[{ text: first, x: 0 }], [{ text: second, x: 0 }]]);

		const occs = searchDocument('Pieter de Vries', extraction, []);
		expect(occs).toHaveLength(1);
		expect(occs[0].bboxes).toHaveLength(2);

		const [top, bottom] = occs[0].bboxes;
		// First line: narrowed on the left only — the match runs to the end
		// of the item, so its right edge stays the item's right edge.
		const firstX1 = first.length * 6;
		expect(top.x0).toBeCloseTo(
			afmSpan(first, 0, firstX1, first.indexOf('Pieter'), first.length).x0,
			5
		);
		expect(top.x1).toBeCloseTo(firstX1, 5);
		expect(top.x0).toBeGreaterThan(0);

		// Second line: narrowed on the right only.
		const secondX1 = second.length * 6;
		expect(bottom.x0).toBeCloseTo(0, 5);
		expect(bottom.x1).toBeCloseTo(afmSpan(second, 0, secondX1, 0, second.indexOf(',')).x1, 5);
		expect(bottom.x1).toBeLessThan(secondX1);
	});

	// The alreadyRedacted threshold measures overlap relative to the *hit*,
	// so a narrower box makes coverage easier to reach, not harder — but a
	// pre-existing black bar around the term must still count as cover.
	it('still flags a narrowed hit that an existing detection covers', () => {
		const line = 'Uw verzoek is behandeld door onze medewerker Pieter de Vries.';
		const extraction = makeExtraction([[{ text: line, x: 40 }]]);
		const itemX1 = 40 + line.length * 6;
		const term = afmSpan(line, 40, itemX1, line.indexOf('Pieter'), line.indexOf('.'));

		const existing = [
			{
				bounding_boxes: [box(0, term.x0 - 1, term.x1 + 1)],
				review_status: 'auto_accepted' as const
			}
		];
		const occs = searchDocument('Pieter de Vries', extraction, existing);
		expect(occs).toHaveLength(1);
		expect(occs[0].alreadyRedacted).toBe(true);
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

// ---------------------------------------------------------------------------
// #87 — rotation invariance.
//
// `segmentToBox` cut a line-wide item down to the match along x, and
// `mergeLineBboxes` decided "same line" from y. Both are only the reading
// direction at /Rotate 0. On a /Rotate 90 page the cut ran across the line
// instead of along it, so a search hit blacked out the whole sentence around
// the term — over-redaction, not a leak, but it is exactly the thing
// search-and-redact exists to avoid.
//
// The property asserted here: rotating the page must rotate the boxes, and
// nothing else.
// ---------------------------------------------------------------------------

function rotateExtraction(ext: ExtractionResult, rotation: PageRotation): ExtractionResult {
	return {
		...ext,
		pages: ext.pages.map((p) => ({
			...p,
			rotation,
			textItems: p.textItems.map((it) => rotateBox(it, rotation))
		}))
	};
}

function expectSameBox(actual: BoundingBox, expected: BoundingBox) {
	expect(actual.page).toBe(expected.page);
	expect(actual.x0).toBeCloseTo(expected.x0, 5);
	expect(actual.y0).toBeCloseTo(expected.y0, 5);
	expect(actual.x1).toBeCloseTo(expected.x1, 5);
	expect(actual.y1).toBeCloseTo(expected.y1, 5);
}

describe('searchDocument on rotated pages', () => {
	const LINE = 'Uw verzoek is behandeld door onze medewerker Pieter de Vries.';

	it.each(ROTATIONS)('narrows to the term, not the sentence, at /Rotate %i', (rotation) => {
		const flat = makeExtraction([[{ text: LINE, x: 40 }]]);
		const rotated = rotateExtraction(flat, rotation);

		const expected = searchDocument('Pieter de Vries', flat, [])[0];
		const actual = searchDocument('Pieter de Vries', rotated, [])[0];

		expect(actual.matchText).toBe(expected.matchText);
		expect(actual.bboxes).toHaveLength(1);
		expectSameBox(actual.bboxes[0], rotateBox(expected.bboxes[0], rotation));

		// The claim in reviewer terms, restated so it survives a rewrite of
		// the helper above: the bar covers well under half the line.
		const item = rotated.pages[0].textItems[0];
		const itemArea = (item.x1 - item.x0) * (item.y1 - item.y0);
		const bar = actual.bboxes[0];
		const barArea = (bar.x1 - bar.x0) * (bar.y1 - bar.y0);
		expect(barArea).toBeLessThan(itemArea * 0.4);
	});

	it.each(ROTATIONS)('narrows both halves of a wrapped match at /Rotate %i', (rotation) => {
		const first = 'Uw verzoek is behandeld door medewerker Pieter';
		const second = 'de Vries, bereikbaar op p.devries@voorbeeld.nl';
		const flat = makeLines([[{ text: first, x: 0 }], [{ text: second, x: 0 }]]);
		const rotated = rotateExtraction(flat, rotation);

		const expected = searchDocument('Pieter de Vries', flat, [])[0];
		const actual = searchDocument('Pieter de Vries', rotated, [])[0];

		// Two lines stay two bars: `mergeLineBboxes` must not fuse them just
		// because they now share a coordinate on the axis it used to test.
		expect(actual.bboxes).toHaveLength(2);
		const expectedBoxes = expected.bboxes.map((b) => rotateBox(b, rotation));
		for (const want of expectedBoxes) {
			expect(actual.bboxes.some((got) => Math.abs(got.x0 - want.x0) < 1e-5)).toBe(true);
		}
	});

	it.each(ROTATIONS)('merges same-line items into one bar at /Rotate %i', (rotation) => {
		// Two adjacent items on one line: the merge has to produce a single
		// bar spanning both, at every rotation.
		const flat = makeExtraction([
			[
				{ text: 'Pieter', x: 0 },
				{ text: 'de', x: 42 },
				{ text: 'Vries', x: 60 }
			]
		]);
		const rotated = rotateExtraction(flat, rotation);
		const occs = searchDocument('Pieter de Vries', rotated, []);
		expect(occs).toHaveLength(1);
		expect(occs[0].bboxes).toHaveLength(1);
		expectSameBox(
			occs[0].bboxes[0],
			rotateBox(searchDocument('Pieter de Vries', flat, [])[0].bboxes[0], rotation)
		);
	});

	it('treats a page with no rotation field as /Rotate 0', () => {
		const flat = makeExtraction([[{ text: LINE, x: 40 }]]);
		expect(flat.pages[0].rotation).toBeUndefined();
		expect(searchDocument('Pieter de Vries', flat, [])).toHaveLength(1);
	});
});
