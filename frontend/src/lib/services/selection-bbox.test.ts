import { beforeAll, describe, it, expect } from 'vitest';
import {
	rangeToBoundingBoxes,
	snapRangeToWordBoundaries
} from './selection-bbox';

// vitest runs under `environment: 'node'` by default, so there is no
// real DOM. The functions under test only touch a tiny surface area
// (`Node.TEXT_NODE`, `range.{set,get}*`, `getClientRects`, etc.) so we
// shim just that surface and pass in plain objects — no JSDOM needed.
beforeAll(() => {
	const g = globalThis as unknown as { Node?: { TEXT_NODE: number } };
	if (!g.Node) g.Node = { TEXT_NODE: 3 };
});

function textNode(text: string) {
	return { nodeType: 3, textContent: text };
}

interface FakeRange {
	startContainer: ReturnType<typeof textNode>;
	startOffset: number;
	endContainer: ReturnType<typeof textNode>;
	endOffset: number;
	collapsed?: boolean;
	setStart(node: unknown, offset: number): void;
	setEnd(node: unknown, offset: number): void;
	getClientRects?(): DOMRectLike[];
}

interface DOMRectLike {
	left: number;
	top: number;
	right: number;
	bottom: number;
	width: number;
	height: number;
}

function makeRange(
	startNode: ReturnType<typeof textNode>,
	startOffset: number,
	endNode: ReturnType<typeof textNode>,
	endOffset: number
): FakeRange {
	return {
		startContainer: startNode,
		startOffset,
		endContainer: endNode,
		endOffset,
		setStart(node, offset) {
			this.startContainer = node as ReturnType<typeof textNode>;
			this.startOffset = offset as number;
		},
		setEnd(node, offset) {
			this.endContainer = node as ReturnType<typeof textNode>;
			this.endOffset = offset as number;
		}
	};
}

describe('snapRangeToWordBoundaries', () => {
	it('expands a mid-word start to the previous word boundary', () => {
		const node = textNode('hello world foo');
		// selection covers "orl" inside "world"
		const range = makeRange(node, 7, node, 10);
		snapRangeToWordBoundaries(range as unknown as Range);
		// "world" spans offsets 6..11
		expect(range.startOffset).toBe(6);
		expect(range.endOffset).toBe(11);
	});

	it('expands across a leading word to the end of the trailing word', () => {
		const node = textNode('alpha beta gamma');
		// selection covers "lph" .. "amm" — should snap to "alpha" .. "gamma"
		const range = makeRange(node, 1, node, 14);
		snapRangeToWordBoundaries(range as unknown as Range);
		expect(range.startOffset).toBe(0);
		expect(range.endOffset).toBe(16);
	});

	it('leaves a selection that is already on word boundaries untouched', () => {
		const node = textNode('foo bar baz');
		const range = makeRange(node, 4, node, 7); // "bar"
		snapRangeToWordBoundaries(range as unknown as Range);
		expect(range.startOffset).toBe(4);
		expect(range.endOffset).toBe(7);
	});

	it('stops expanding at punctuation word-boundary characters', () => {
		const node = textNode('a.b,c');
		// selection covers just "b" — punctuation on both sides is a boundary
		const range = makeRange(node, 2, node, 3);
		snapRangeToWordBoundaries(range as unknown as Range);
		expect(range.startOffset).toBe(2);
		expect(range.endOffset).toBe(3);
	});

	it('does nothing when the container is not a text node', () => {
		const nonText = { nodeType: 1 /* ELEMENT_NODE */, textContent: '' };
		const range = {
			startContainer: nonText,
			startOffset: 5,
			endContainer: nonText,
			endOffset: 5,
			setStart() {
				throw new Error('should not be called');
			},
			setEnd() {
				throw new Error('should not be called');
			}
		};
		expect(() => snapRangeToWordBoundaries(range as unknown as Range)).not.toThrow();
		expect(range.startOffset).toBe(5);
		expect(range.endOffset).toBe(5);
	});
});

describe('rangeToBoundingBoxes', () => {
	const SLACK = 0.5;
	const container = {
		getBoundingClientRect: () => ({
			left: 10,
			top: 20,
			right: 110,
			bottom: 220,
			width: 100,
			height: 200
		})
	};

	function rangeWithRects(rects: DOMRectLike[]): FakeRange {
		return {
			// start/end/setters are unused here — rangeToBoundingBoxes only
			// reads `.collapsed` and `.getClientRects()`.
			startContainer: textNode(''),
			startOffset: 0,
			endContainer: textNode(''),
			endOffset: 0,
			collapsed: false,
			setStart() {},
			setEnd() {},
			getClientRects: () => rects
		};
	}

	it('returns an empty array when the range is collapsed', () => {
		const range = rangeWithRects([]);
		range.collapsed = true;
		const result = rangeToBoundingBoxes(
			range as unknown as Range,
			container as unknown as HTMLElement,
			1,
			0
		);
		expect(result).toEqual([]);
	});

	it('converts a single rect to PDF-space with slack applied', () => {
		const range = rangeWithRects([
			{ left: 30, top: 40, right: 60, bottom: 60, width: 30, height: 20 }
		]);
		const result = rangeToBoundingBoxes(
			range as unknown as Range,
			container as unknown as HTMLElement,
			2,
			3
		);
		expect(result).toHaveLength(1);
		expect(result[0]).toEqual({
			page: 3,
			// (30 - 10) / 2 - 0.5 = 9.5
			x0: (30 - 10) / 2 - SLACK,
			// (40 - 20) / 2 - 0.5 = 9.5
			y0: (40 - 20) / 2 - SLACK,
			// (60 - 10) / 2 + 0.5 = 25.5
			x1: (60 - 10) / 2 + SLACK,
			// (60 - 20) / 2 + 0.5 = 20.5
			y1: (60 - 20) / 2 + SLACK
		});
	});

	it('merges horizontally-touching rects on the same visual line', () => {
		const range = rangeWithRects([
			// two halves of one line (browsers split per span)
			{ left: 20, top: 30, right: 40, bottom: 50, width: 20, height: 20 },
			{ left: 40, top: 30, right: 60, bottom: 50, width: 20, height: 20 }
		]);
		const result = rangeToBoundingBoxes(
			range as unknown as Range,
			container as unknown as HTMLElement,
			2,
			0
		);
		expect(result).toHaveLength(1);
		expect(result[0].x0).toBeCloseTo((20 - 10) / 2 - SLACK, 5);
		expect(result[0].x1).toBeCloseTo((60 - 10) / 2 + SLACK, 5);
	});

	it('keeps rects on different visual lines as separate bboxes', () => {
		const range = rangeWithRects([
			{ left: 20, top: 30, right: 60, bottom: 50, width: 40, height: 20 },
			{ left: 20, top: 80, right: 60, bottom: 100, width: 40, height: 20 }
		]);
		const result = rangeToBoundingBoxes(
			range as unknown as Range,
			container as unknown as HTMLElement,
			1,
			0
		);
		expect(result).toHaveLength(2);
	});

	it('ignores zero-sized rects that browsers sometimes emit', () => {
		const range = rangeWithRects([
			{ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 },
			{ left: 20, top: 30, right: 60, bottom: 50, width: 40, height: 20 }
		]);
		const result = rangeToBoundingBoxes(
			range as unknown as Range,
			container as unknown as HTMLElement,
			1,
			0
		);
		expect(result).toHaveLength(1);
	});
});
