import { describe, it, expect } from 'vitest';
import { normalizeRotation, readingAxis } from './reading-axis';
import { PAGE_HEIGHT, PAGE_WIDTH, ROTATIONS, rotateBox } from './testing/viewer-rotation';

// A line of text at /Rotate 0: 100pt wide, 12pt tall, starting at x = 72.
const LINE = { x0: 72, y0: 148, x1: 172, y1: 160 };
// The next word on the same line, starting where LINE ends.
const NEXT = { x0: 172, y0: 148, x1: 210, y1: 160 };
// The first word of the line below.
const BELOW = { x0: 72, y0: 178, x1: 172, y1: 190 };

describe('normalizeRotation', () => {
	it('accepts the four supported rotations verbatim', () => {
		for (const r of ROTATIONS) expect(normalizeRotation(r)).toBe(r);
	});

	it('wraps out-of-range multiples of 90 into [0, 360)', () => {
		expect(normalizeRotation(360)).toBe(0);
		expect(normalizeRotation(450)).toBe(90);
		expect(normalizeRotation(-90)).toBe(270);
	});

	// A /Rotate that is not a multiple of 90 is invalid PDF that pdf.js
	// rejects outright, and an extraction cached before #87 carries no
	// rotation at all. Both have to land on 0 — the behavior this module
	// replaced — rather than throwing in the middle of a review session.
	it('falls back to 0 for anything else', () => {
		expect(normalizeRotation(45)).toBe(0);
		expect(normalizeRotation(undefined)).toBe(0);
		expect(normalizeRotation(null)).toBe(0);
		expect(normalizeRotation(Number.NaN)).toBe(0);
	});
});

describe('readingAxis', () => {
	it('reports a positive extent along the reading direction at every rotation', () => {
		for (const rotation of ROTATIONS) {
			const axis = readingAxis(rotation);
			const span = axis.along(rotateBox(LINE, rotation));
			expect(span.end - span.start).toBeCloseTo(100, 6);
		}
	});

	it('orders words on a line the way they are read, at every rotation', () => {
		// This is the property the sameLine/touching join depends on: at
		// /Rotate 180 and 270 reading order runs *against* the viewer axis,
		// so a raw x0/y0 comparison puts the second word first.
		for (const rotation of ROTATIONS) {
			const axis = readingAxis(rotation);
			const first = axis.along(rotateBox(LINE, rotation));
			const second = axis.along(rotateBox(NEXT, rotation));
			expect(first.start).toBeLessThan(second.start);
			// And they touch: no gap between the end of one and the start of
			// the next, which is what suppresses the phantom space.
			expect(second.start - first.end).toBeCloseTo(0, 6);
		}
	});

	it('separates lines on the cross axis at every rotation', () => {
		for (const rotation of ROTATIONS) {
			const axis = readingAxis(rotation);
			const sameLine = Math.abs(
				axis.cross(rotateBox(LINE, rotation)).start - axis.cross(rotateBox(NEXT, rotation)).start
			);
			const nextLine = Math.abs(
				axis.cross(rotateBox(LINE, rotation)).start - axis.cross(rotateBox(BELOW, rotation)).start
			);
			expect(sameLine).toBeCloseTo(0, 6);
			expect(nextLine).toBeCloseTo(30, 6);
		}
	});

	it('round-trips withAlong back into viewer space', () => {
		for (const rotation of ROTATIONS) {
			const axis = readingAxis(rotation);
			const box = rotateBox(LINE, rotation);
			const span = axis.along(box);
			const same = axis.withAlong(box, span.start, span.end);
			expect(same).toEqual(box);
		}
	});

	it('narrows to the second half of a line, in viewer space, at every rotation', () => {
		// Cutting [50, 100) of a 100pt line at /Rotate 0 gives x 122..172.
		// Rotating that box has to give the same answer as narrowing the
		// rotated line — that equivalence is the whole point of #87.
		const expected0 = { x0: 122, y0: 148, x1: 172, y1: 160 };
		for (const rotation of ROTATIONS) {
			const axis = readingAxis(rotation);
			const box = rotateBox(LINE, rotation);
			const span = axis.along(box);
			const narrowed = axis.withAlong(box, span.start + 50, span.end);
			const expected = rotateBox(expected0, rotation);
			expect(narrowed.x0).toBeCloseTo(expected.x0, 6);
			expect(narrowed.y0).toBeCloseTo(expected.y0, 6);
			expect(narrowed.x1).toBeCloseTo(expected.x1, 6);
			expect(narrowed.y1).toBeCloseTo(expected.y1, 6);
		}
	});

	it('preserves fields beyond the rect, so a BoundingBox keeps its page', () => {
		const axis = readingAxis(90);
		const withPage = { page: 3, ...rotateBox(LINE, 90) };
		const span = axis.along(withPage);
		expect(axis.withAlong(withPage, span.start, span.end).page).toBe(3);
	});

	it('keeps the narrowed box inside the page at every rotation', () => {
		// A band that ran the wrong way used to leave the page box entirely
		// once the axes were swapped; assert the geometry stays on the sheet.
		for (const rotation of ROTATIONS) {
			const axis = readingAxis(rotation);
			const swaps = rotation === 90 || rotation === 270;
			const width = swaps ? PAGE_HEIGHT : PAGE_WIDTH;
			const height = swaps ? PAGE_WIDTH : PAGE_HEIGHT;
			const box = rotateBox(LINE, rotation);
			const span = axis.along(box);
			const narrowed = axis.withAlong(box, span.start + 10, span.start + 40);
			expect(narrowed.x0).toBeGreaterThanOrEqual(0);
			expect(narrowed.y0).toBeGreaterThanOrEqual(0);
			expect(narrowed.x1).toBeLessThanOrEqual(width);
			expect(narrowed.y1).toBeLessThanOrEqual(height);
		}
	});
});
