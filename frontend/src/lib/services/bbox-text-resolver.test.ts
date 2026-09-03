import { describe, it, expect } from 'vitest';
import { findTextForBboxes, resolveEntityTexts } from './bbox-text-resolver';
import type { BoundingBox, ExtractionResult } from '$lib/types';

/**
 * Build an ExtractionResult where each page is a list of text items
 * positioned on a single visual line (y in [100, 110]). The caller
 * provides the x-range explicitly so these tests can model pdf.js's
 * real behavior — notably line-wide items that the backend later
 * narrows proportionally.
 */
function makeExtraction(
	pages: { text: string; x0: number; x1: number }[][]
): ExtractionResult {
	const pageObjs = pages.map((items, pageIdx) => {
		const textItems = items.map((it) => ({
			text: it.text,
			x0: it.x0,
			y0: 100,
			x1: it.x1,
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

describe('findTextForBboxes', () => {
	it('returns the whole item when the bbox contains it', () => {
		const ext = makeExtraction([[{ text: 'Mw. De Vries', x0: 10, x1: 82 }]]);
		const text = findTextForBboxes([box(0, 8, 84)], ext);
		expect(text).toBe('Mw. De Vries');
	});

	it('slices a line-wide item proportionally when the bbox is narrower', () => {
		// Simulates the "W. de Groot" regression. pdf.js emits the whole
		// line as one text item; the backend has narrowed the bbox down
		// to cover just the name using Helvetica AFM widths, and the
		// resolver must invert that with the same weighting. Char-count
		// linear slicing clipped the first glyph of names preceded by
		// glyph-wide prefixes ("W. de Groot" ← "Ook de heer "). Pixel
		// positions below come from the AFM table in bbox-text-resolver.
		const line =
			'de familie El Khatib (huisnummer 22). Ook de heer W. de Groot, bewoner van nummer 26, heeft';
		const itemWidth = 42518; // AFM sum of the whole line (1/1000 em units)
		const nameX0 = 22731; // AFM sum of "de familie … Ook de heer "
		const nameX1 = 28122; // + AFM sum of "W. de Groot"
		const ext = makeExtraction([[{ text: line, x0: 0, x1: itemWidth }]]);
		const bbox = box(0, nameX0, nameX1);

		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('W. de Groot');
	});

	it('keeps the leading initial of names preceded by wider glyphs', () => {
		// Regression: in the demo-video fixture the detector found
		// "P. Hoogvliet" inside the line-wide pdf.js item
		// "Wethouder P. Hoogvliet neemt het dossier in behandeling.".
		// With char-count linear slicing the resolver landed one glyph
		// past the "P" (the "Wethouder" prefix is full of wide glyphs:
		// W, d, u, o) and the sidebar card showed ". Hoogvliet".
		const line = 'Wethouder P. Hoogvliet neemt het dossier in behandeling.';
		const itemWidth = 25846; // AFM sum of the whole line
		const nameX0 = 5169; // AFM sum of "Wethouder "
		const nameX1 = 10560; // + AFM sum of "P. Hoogvliet"
		const ext = makeExtraction([[{ text: line, x0: 0, x1: itemWidth }]]);
		const bbox = box(0, nameX0, nameX1);

		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('P. Hoogvliet');
	});

	it('slices an item when the bbox covers a substring near the start', () => {
		// "mevrouw T. Bakker (huisnummer 18)" — AFM positions for the
		// "T. Bakker" substring so the slicer exercises the AFM path.
		const line = 'mevrouw T. Bakker (huisnummer 18)';
		const itemWidth = 16488;
		const nameX0 = 4334; // AFM sum of "mevrouw "
		const nameX1 = 8613; // + AFM sum of "T. Bakker"
		const ext = makeExtraction([[{ text: line, x0: 0, x1: itemWidth }]]);
		const bbox = box(0, nameX0, nameX1);

		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('T. Bakker');
	});

	it('returns the full string for short, whole-item matches', () => {
		const ext = makeExtraction([
			[{ text: 'voorzitter dhr. K. Hendriks.', x0: 10, x1: 178 }]
		]);
		const bbox = box(0, 10, 178);
		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('voorzitter dhr. K. Hendriks.');
	});

	it('dedupes identical parts from repeated bboxes for the same entity', () => {
		// A "persoon" detection with two occurrences of "A.B. Bakker" —
		// one per bbox. The sidebar used to show "A.B. Bakker A.B. Bakker".
		const ext = makeExtraction([
			[
				{ text: 'A.B. Bakker', x0: 10, x1: 76 },
				{ text: 'A.B. Bakker', x0: 10, x1: 76 }
			]
		]);
		ext.pages[0].textItems[0].y0 = 100;
		ext.pages[0].textItems[0].y1 = 110;
		ext.pages[0].textItems[1].y0 = 200;
		ext.pages[0].textItems[1].y1 = 210;

		const text = findTextForBboxes(
			[
				{ page: 0, x0: 10, y0: 100, x1: 76, y1: 110 },
				{ page: 0, x0: 10, y0: 200, x1: 76, y1: 210 }
			],
			ext
		);
		expect(text).toBe('A.B. Bakker');
	});

	it('dedupes across trailing punctuation ("Amsterdam" vs "Amsterdam,")', () => {
		const ext = makeExtraction([
			[
				{ text: 'Amsterdam', x0: 10, x1: 70 },
				{ text: 'Amsterdam,', x0: 10, x1: 76 }
			]
		]);
		ext.pages[0].textItems[0].y0 = 100;
		ext.pages[0].textItems[0].y1 = 110;
		ext.pages[0].textItems[1].y0 = 200;
		ext.pages[0].textItems[1].y1 = 210;

		const text = findTextForBboxes(
			[
				{ page: 0, x0: 10, y0: 100, x1: 70, y1: 110 },
				{ page: 0, x0: 10, y0: 200, x1: 76, y1: 210 }
			],
			ext
		);
		// The first unique form wins — we don't try to pick the "nicer" one.
		expect(text).toBe('Amsterdam');
	});

	it('joins touching single-glyph items without spaces (Menlo/monospace)', () => {
		// Regression: pdf.js returns each glyph as its own text item for
		// some monospace fonts (Menlo, Courier). The resolver used to
		// `.join(' ')` unconditionally and rendered "W i l l e m i j n"
		// in the sidebar card, even though the glyphs visually touch and
		// the detector saw "Willemijn".
		const chars = 'Willemijn'.split('');
		const charWidth = 7.22;
		const items = chars.map((c, i) => ({
			text: c,
			x0: 10 + i * charWidth,
			x1: 10 + (i + 1) * charWidth
		}));
		const ext = makeExtraction([items]);
		const bbox = box(0, 10, 10 + chars.length * charWidth);
		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('Willemijn');
	});

	it('inserts a space when single-glyph items are separated by a visual gap', () => {
		// Same setup as the previous test, but with a 10pt visual gap
		// halfway through — e.g. "Willem ijn" in a monospace font where
		// the extractor would (correctly) see a word break.
		const charWidth = 7.22;
		const items = [
			{ text: 'W', x0: 10, x1: 10 + charWidth },
			{ text: 'i', x0: 10 + charWidth, x1: 10 + charWidth * 2 },
			{ text: 'l', x0: 10 + charWidth * 2, x1: 10 + charWidth * 3 },
			// Big gap here
			{ text: 'X', x0: 10 + charWidth * 3 + 10, x1: 10 + charWidth * 4 + 10 },
			{ text: 'Y', x0: 10 + charWidth * 4 + 10, x1: 10 + charWidth * 5 + 10 }
		];
		const ext = makeExtraction([items]);
		const bbox = box(0, 10, 10 + charWidth * 5 + 10);
		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('Wil XY');
	});

	it('never crosses lines even when the bbox y range overlaps both', () => {
		const ext = makeExtraction([
			[
				{ text: 'first line with a target name', x0: 10, x1: 160 },
				{ text: 'second line with other text', x0: 10, x1: 160 }
			]
		]);
		// Set the second line at a different y — the helper above uses
		// a fixed y [100..110] so for this test we build manually.
		ext.pages[0].textItems[0].y0 = 100;
		ext.pages[0].textItems[0].y1 = 110;
		ext.pages[0].textItems[1].y0 = 120;
		ext.pages[0].textItems[1].y1 = 130;

		const bbox = box(0, 40, 80); // only line 1 center-y sits inside
		const text = findTextForBboxes([bbox], ext);
		expect(text).not.toContain('second line');
	});
});

describe('resolveEntityTexts', () => {
	it('fills in entity_text from the extraction', () => {
		const ext = makeExtraction([[{ text: 'Jan de Vries', x0: 0, x1: 72 }]]);
		const detections = [
			{ id: '1', entity_text: undefined, bounding_boxes: [box(0, 0, 72)] }
		];
		const { detections: resolved, unplaced } = resolveEntityTexts(detections, ext);
		expect(resolved[0].entity_text).toBe('Jan de Vries');
		expect(unplaced).toHaveLength(0);
	});

	it('drops detections when no text items match the bbox', () => {
		const ext = makeExtraction([[{ text: 'Jan', x0: 0, x1: 18 }]]);
		const detections = [
			{ id: '1', entity_text: undefined, bounding_boxes: [box(0, 500, 600)] }
		];
		const { detections: resolved } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(0);
	});

	it('drops detections that carry no bounding boxes at all', () => {
		const ext = makeExtraction([[{ text: 'Jan', x0: 0, x1: 18 }]]);
		const detections = [{ id: '1', entity_text: undefined, bounding_boxes: [] }];
		const { detections: resolved } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(0);
	});

	it('preserves an existing entity_text (manual detections)', () => {
		const ext = makeExtraction([[{ text: 'anything', x0: 0, x1: 48 }]]);
		const detections = [
			{ id: '1', entity_text: 'reviewer typed this', bounding_boxes: [box(0, 0, 48)] }
		];
		const { detections: resolved } = resolveEntityTexts(detections, ext);
		expect(resolved[0].entity_text).toBe('reviewer typed this');
	});
});

// #78 — a dropped detection is a detection the reviewer never sees. These
// cover the reporting side: what got dropped, why, and with which term.
describe('resolveEntityTexts — unplaced reporting', () => {
	it('reports a detection without bboxes and recovers its term from the offsets', () => {
		const ext = makeExtraction([[{ text: 'Jan de Vries werkt hier', x0: 0, x1: 138 }]]);
		const detections = [
			{
				id: 'd1',
				entity_text: undefined,
				entity_type: 'person',
				tier: '2',
				bounding_boxes: [],
				start_char: 0,
				end_char: 12
			}
		];
		const { detections: resolved, unplaced } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(0);
		expect(unplaced).toEqual([
			{
				id: 'd1',
				entity_type: 'person',
				tier: '2',
				page: null,
				text: 'Jan de Vries',
				reason: 'no_bbox'
			}
		]);
	});

	it('reports a bbox that lands outside the page, with its page number', () => {
		const ext = makeExtraction([[{ text: 'Jan de Vries', x0: 0, x1: 72 }]]);
		const detections = [
			{
				id: 'd2',
				entity_text: undefined,
				bounding_boxes: [box(0, -40, -10)],
				start_char: 0,
				end_char: 12
			}
		];
		const { detections: resolved, unplaced } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(0);
		expect(unplaced).toHaveLength(1);
		expect(unplaced[0]).toMatchObject({
			id: 'd2',
			page: 0,
			text: 'Jan de Vries',
			reason: 'no_text_match'
		});
	});

	it('offsets index the untrimmed page join, matching the server', () => {
		const ext = makeExtraction([
			[{ text: 'pagina een', x0: 0, x1: 60 }],
			[{ text: 'Jan de Vries', x0: 0, x1: 72 }]
		]);
		// "pagina een" (10) + "\n\n" (2) = offset 12 for page two.
		const detections = [
			{ id: 'd3', entity_text: undefined, bounding_boxes: [], start_char: 12, end_char: 24 }
		];
		const { unplaced } = resolveEntityTexts(detections, ext);
		expect(unplaced[0].text).toBe('Jan de Vries');
	});

	it('reports the drop without a term when the offsets are missing or out of range', () => {
		const ext = makeExtraction([[{ text: 'Jan', x0: 0, x1: 18 }]]);
		const detections = [
			{ id: 'no-offsets', entity_text: undefined, bounding_boxes: [] },
			{
				id: 'out-of-range',
				entity_text: undefined,
				bounding_boxes: [],
				start_char: 900,
				end_char: 950
			}
		];
		const { unplaced } = resolveEntityTexts(detections, ext);
		expect(unplaced.map((u) => u.text)).toEqual([null, null]);
		expect(unplaced.map((u) => u.id)).toEqual(['no-offsets', 'out-of-range']);
	});

	it('keeps an area redaction that has neither text nor overlapping items', () => {
		// A Shift+drag over a signature is stored with `entity_text: ''`,
		// and IDB strips the field anyway — dropping it on hydrate would
		// lose a redaction the reviewer drew by hand.
		const ext = makeExtraction([[{ text: 'Met vriendelijke groet', x0: 0, x1: 120 }]]);
		const detections = [
			{
				id: 'area',
				entity_text: undefined,
				source: 'manual',
				bounding_boxes: [{ page: 0, x0: 20, y0: 400, x1: 160, y1: 460 }]
			}
		];
		const { detections: resolved, unplaced } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(1);
		expect(unplaced).toHaveLength(0);
	});

	it('restores the label of a reviewer-authored row from its bbox after a refresh', () => {
		// `persistDetections` strips `entity_text` before writing to IDB, so
		// a split half or a search-and-redact hit comes back textless. Its
		// bbox does sit on real text, and the sidebar label depends on that
		// resolution still happening. The left half of a split resolves to
		// its own part of the name, not the whole original.
		const ext = makeExtraction([[{ text: 'Pieter de Vries', x0: 0, x1: 90 }]]);
		const detections = [
			{
				id: 'half',
				entity_text: undefined,
				source: 'manual',
				bounding_boxes: [box(0, 0, 36)]
			}
		];
		const { detections: resolved, unplaced } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(1);
		expect(resolved[0].entity_text).toBe('Pieter');
		expect(unplaced).toHaveLength(0);
	});

	it('does not report reviewer-authored rows, which never resolve', () => {
		const ext = makeExtraction([[{ text: 'Jan', x0: 0, x1: 18 }]]);
		const detections = [
			{ id: 'manual', entity_text: 'handmatig gelakt', bounding_boxes: [] }
		];
		const { detections: resolved, unplaced } = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(1);
		expect(unplaced).toHaveLength(0);
	});
});
