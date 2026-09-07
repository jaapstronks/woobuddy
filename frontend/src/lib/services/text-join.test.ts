import { describe, it, expect } from 'vitest';
import {
	ADJACENT_X_TOLERANCE,
	SAME_LINE_TOLERANCE,
	joinTextItems,
	separatorBetween,
	type JoinBox
} from './text-join';

/** A 12pt-tall box on the line whose top edge sits at `y`, starting at `x`. */
function box(x: number, y: number, width: number): JoinBox {
	return { x0: x, y0: y, x1: x + width, y1: y + 12 };
}

describe('separatorBetween', () => {
	it('joins touching items on a line without a separator', () => {
		// pdf.js splits IBANs, URLs and phone numbers across items; a phantom
		// space here breaks both the Tier 1 regexes and NER.
		expect(separatorBetween(box(100, 100, 30), box(130, 100, 30))).toBe('');
	});

	it('spaces items that share a line but stand apart', () => {
		expect(separatorBetween(box(100, 100, 30), box(200, 100, 30))).toBe(' ');
	});

	it('starts a new line when the next item drops below the tolerance', () => {
		expect(separatorBetween(box(100, 100, 30), box(100, 100 + SAME_LINE_TOLERANCE, 30))).toBe(
			'\n'
		);
	});

	it('breaks the line before it merges, however close the x-coordinates', () => {
		// Content-stream order is not reading order: the first item of a new
		// line often starts exactly where the previous line ended. Testing the
		// line first is what stops "Postbus" and the resident's street from
		// becoming one word.
		expect(separatorBetween(box(100, 100, 30), box(130, 140, 30))).toBe('\n');
	});

	it('treats sub-tolerance jitter as the same line', () => {
		const jitter = SAME_LINE_TOLERANCE / 2;
		expect(separatorBetween(box(100, 100, 30), box(200, 100 + jitter, 30))).toBe(' ');
	});

	it('splits words once the gap reaches the adjacency tolerance', () => {
		const gap = box(130 + ADJACENT_X_TOLERANCE, 100, 30);
		expect(separatorBetween(box(100, 100, 30), gap)).toBe(' ');
	});
});

describe('joinTextItems', () => {
	const texts = ['Postbus', '30', 'Kerkstraat', '3'];
	const boxes = [box(100, 100, 40), box(145, 100, 12), box(100, 120, 60), box(165, 120, 8)];

	it('applies the three separators in one pass', () => {
		expect(joinTextItems(texts, boxes)).toBe('Postbus 30\nKerkstraat 3');
	});

	it('uses exactly one character per separator', () => {
		// Offsets travel with the text: `start_char`/`end_char` must mean the
		// same thing whichever separator the join picked, or every bbox in the
		// review screen shifts.
		expect(joinTextItems(texts, boxes)).toHaveLength(texts.join('').length + 3);
	});

	it('returns an empty string for a page without items', () => {
		expect(joinTextItems([], [])).toBe('');
	});

	it('returns a single item unchanged', () => {
		expect(joinTextItems(['Alleen'], [box(100, 100, 40)])).toBe('Alleen');
	});
});
