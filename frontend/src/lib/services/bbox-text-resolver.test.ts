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
		// to cover just the name. The resolver must return *only* that
		// substring, not the full line.
		const line = 'de familie El Khatib (huisnummer 22). Ook de heer W. de Groot, bewoner van nummer 26, heeft';
		// Make the line 930 units wide so each character is ~10 units
		// wide. That lets us pick a bbox that maps cleanly to character
		// indices for an assertion.
		const itemX0 = 0;
		const itemX1 = line.length * 10;
		const ext = makeExtraction([[{ text: line, x0: itemX0, x1: itemX1 }]]);

		// "W. de Groot" starts at char index 50 and ends at 61.
		const nameStart = line.indexOf('W. de Groot');
		const nameEnd = nameStart + 'W. de Groot'.length;
		const bbox = box(0, nameStart * 10, nameEnd * 10);

		const text = findTextForBboxes([bbox], ext);
		expect(text).toBe('W. de Groot');
	});

	it('slices an item when the bbox covers a substring near the start', () => {
		const line = 'mevrouw T. Bakker (huisnummer 18)';
		const itemX0 = 0;
		const itemX1 = line.length * 10;
		const ext = makeExtraction([[{ text: line, x0: itemX0, x1: itemX1 }]]);

		const nameStart = line.indexOf('T. Bakker');
		const nameEnd = nameStart + 'T. Bakker'.length;
		const bbox = box(0, nameStart * 10, nameEnd * 10);

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
		const resolved = resolveEntityTexts(detections, ext);
		expect(resolved[0].entity_text).toBe('Jan de Vries');
	});

	it('drops detections when no text items match the bbox', () => {
		const ext = makeExtraction([[{ text: 'Jan', x0: 0, x1: 18 }]]);
		const detections = [
			{ id: '1', entity_text: undefined, bounding_boxes: [box(0, 500, 600)] }
		];
		const resolved = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(0);
	});

	it('drops detections that carry no bounding boxes at all', () => {
		const ext = makeExtraction([[{ text: 'Jan', x0: 0, x1: 18 }]]);
		const detections = [{ id: '1', entity_text: undefined, bounding_boxes: [] }];
		const resolved = resolveEntityTexts(detections, ext);
		expect(resolved).toHaveLength(0);
	});

	it('preserves an existing entity_text (manual detections)', () => {
		const ext = makeExtraction([[{ text: 'anything', x0: 0, x1: 48 }]]);
		const detections = [
			{ id: '1', entity_text: 'reviewer typed this', bounding_boxes: [box(0, 0, 48)] }
		];
		const resolved = resolveEntityTexts(detections, ext);
		expect(resolved[0].entity_text).toBe('reviewer typed this');
	});
});
