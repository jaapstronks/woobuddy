import { describe, it, expect } from 'vitest';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { extractText } from './pdf-text-extractor';

// pdf.js hands text items out in PDF user space: bottom-left origin, /Rotate
// NOT applied. Everything downstream of the extractor works in viewer space
// (top-left origin, /Rotate applied, scale 1) — that is where the overlay
// draws, what area-select produces, and what `apply_redactions` derotates for
// PyMuPDF. Only the page viewport transform bridges the two, so a page with
// /Rotate 90/180/270 is exactly where a bbox can end up in neither space (#84).
//
// vitest runs under `environment: 'node'` and `extractText` never imports
// pdf.js itself (only `loadPdfDocument` does), so a plain object standing in
// for `PDFDocumentProxy` is enough — no module mock, no DOM.

/** A4 in points, the page box every case below uses. */
const PAGE_W = 595;
const PAGE_H = 842;

/**
 * The viewport transforms pdf.js derives for a scale-1 viewport over
 * viewBox [0, 0, W, H], transcribed from `PageViewport` in
 * `pdfjs-dist/build/pdf.mjs`. Written out per rotation rather than recomputed
 * so the test pins the expected geometry independently of the implementation.
 *
 * `convertToViewportPoint(x, y)` applies [a, b, c, d, e, f] as
 * `(a*x + c*y + e, b*x + d*y + f)`.
 */
const VIEWPORT_TRANSFORMS: Record<number, number[]> = {
	0: [1, 0, 0, -1, 0, PAGE_H], // (x, H - y)
	90: [0, 1, 1, 0, 0, 0], // (y, x)
	180: [-1, 0, 0, 1, PAGE_W, 0], // (W - x, y)
	270: [0, -1, -1, 0, PAGE_H, PAGE_W] // (H - y, W - x)
};

interface FakeItem {
	str: string;
	transform: number[];
	width: number;
}

function fakeViewport(rotation: number) {
	const m = VIEWPORT_TRANSFORMS[rotation];
	const swaps = rotation === 90 || rotation === 270;
	return {
		// The old implementation flipped Y against `viewport.height`, so the
		// fake has to carry a truthful height for the regression to be visible.
		width: swaps ? PAGE_H : PAGE_W,
		height: swaps ? PAGE_W : PAGE_H,
		// pdf.js exposes the rotation it actually used; #87 records it on the
		// page so downstream geometry knows which axis the text reads along.
		rotation,
		convertToViewportPoint(x: number, y: number) {
			return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
		}
	};
}

function fakeDoc(rotation: number, items: FakeItem[]): PDFDocumentProxy {
	const page = {
		getViewport({ rotation: requested }: { scale: number; rotation?: number }) {
			// `getViewport` defaults its rotation to the page's own /Rotate; the
			// extractor passes `rotation: 0` explicitly for its layout viewport.
			return fakeViewport(requested ?? rotation);
		},
		getTextContent: async () => ({ items })
	};
	return {
		numPages: 1,
		getPage: async () => page
	} as unknown as PDFDocumentProxy;
}

/** One 12pt word, baseline at (100, 700), 60pt wide. */
const WORD: FakeItem = { str: 'Pieter', transform: [12, 0, 0, 12, 100, 700], width: 60 };

describe('extractText bbox geometry', () => {
	// Hand-computed from the transforms above for the user-space rectangle
	// x 100..160, y 700..712 (baseline origin plus width and font height).
	const cases: Array<[number, { x0: number; y0: number; x1: number; y1: number }]> = [
		[0, { x0: 100, y0: 130, x1: 160, y1: 142 }],
		[90, { x0: 700, y0: 100, x1: 712, y1: 160 }],
		[180, { x0: 435, y0: 700, x1: 495, y1: 712 }],
		[270, { x0: 130, y0: 435, x1: 142, y1: 495 }]
	];

	for (const [rotation, expected] of cases) {
		it(`places the bbox in viewer space at /Rotate ${rotation}`, async () => {
			const result = await extractText(fakeDoc(rotation, [WORD]));
			const [item] = result.pages[0].textItems;

			expect(item.text).toBe('Pieter');
			expect(item).toMatchObject(expected);
		});

		it(`returns an ordered rect at /Rotate ${rotation}`, async () => {
			// 90 and 270 swap the corners, so normalisation is load-bearing:
			// an unsorted rect makes the overlay draw nothing and the export
			// redact nothing.
			const result = await extractText(fakeDoc(rotation, [WORD]));
			const [item] = result.pages[0].textItems;

			expect(item.x0).toBeLessThan(item.x1);
			expect(item.y0).toBeLessThan(item.y1);
		});

		it(`keeps the bbox inside the rotated page at /Rotate ${rotation}`, async () => {
			const vp = fakeViewport(rotation);
			const result = await extractText(fakeDoc(rotation, [WORD]));
			const [item] = result.pages[0].textItems;

			expect(item.x1).toBeLessThanOrEqual(vp.width);
			expect(item.y1).toBeLessThanOrEqual(vp.height);
		});
	}

	it('takes the font height from hypot(tx[2], tx[3]) so skew does not shrink it', async () => {
		// An italic-style text matrix leaks height into tx[2]; |tx[3]| alone
		// would under-report it and the black bar would clip the glyph tops.
		const skewed: FakeItem = { str: 'Vries', transform: [12, 0, 5, 12, 100, 700], width: 40 };
		const result = await extractText(fakeDoc(0, [skewed]));
		const [item] = result.pages[0].textItems;

		expect(item.y1 - item.y0).toBeCloseTo(Math.hypot(5, 12), 6);
	});
});

describe('extractText reading order', () => {
	// pdf.js splits long tokens across items; the extractor rejoins them when
	// they touch. That test runs on unrotated coordinates, because at /Rotate
	// 90 a single baseline runs top-to-bottom in viewer space and every
	// same-line comparison there would fail.
	const split: FakeItem[] = [
		{ str: 'NL91', transform: [12, 0, 0, 12, 100, 700], width: 30 },
		{ str: 'ABNA', transform: [12, 0, 0, 12, 130, 700], width: 30 },
		{ str: 'volgende', transform: [12, 0, 0, 12, 100, 660], width: 50 }
	];

	for (const rotation of [0, 90, 180, 270]) {
		it(`joins touching items and breaks lines at /Rotate ${rotation}`, async () => {
			const result = await extractText(fakeDoc(rotation, split));

			expect(result.pages[0].fullText).toBe('NL91ABNA volgende');
		});
	}
});

// #87 — the boxes above are in viewer space, which is only enough to *draw*.
// Anything that reasons about reading order (narrowing a box to a term,
// deciding two items share a line) needs to know what rotation was baked in,
// so the extractor records it on the page.
describe('extractText page rotation', () => {
	it.each([0, 90, 180, 270])('records /Rotate %i on the page', async (rotation) => {
		const result = await extractText(fakeDoc(rotation, [WORD]));
		expect(result.pages[0].rotation).toBe(rotation);
	});
});
