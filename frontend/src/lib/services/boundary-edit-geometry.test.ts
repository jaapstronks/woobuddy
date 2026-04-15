import { describe, it, expect } from 'vitest';
import type { BoundingBox } from '$lib/types';
import {
	BBOX_MIN_PT,
	applyHandleDelta,
	arrowKeyToNudge,
	bboxesEqual,
	cloneBboxes,
	computeSplitBboxes,
	extendBboxToWord,
	nudgeBbox,
	shrinkBboxByWord
} from './boundary-edit-geometry';

function bb(x0: number, y0: number, x1: number, y1: number, page = 1): BoundingBox {
	return { page, x0, y0, x1, y1 };
}

describe('cloneBboxes', () => {
	it('returns a shallow clone of each bbox', () => {
		const src = [bb(0, 0, 10, 10), bb(20, 20, 30, 30)];
		const copy = cloneBboxes(src);
		expect(copy).toEqual(src);
		expect(copy).not.toBe(src);
		expect(copy[0]).not.toBe(src[0]);
		copy[0].x0 = 99;
		expect(src[0].x0).toBe(0);
	});
});

describe('bboxesEqual', () => {
	it('returns true for structurally identical arrays', () => {
		expect(bboxesEqual([bb(1, 2, 3, 4)], [bb(1, 2, 3, 4)])).toBe(true);
	});
	it('returns false when any coord differs', () => {
		expect(bboxesEqual([bb(1, 2, 3, 4)], [bb(1, 2, 3, 5)])).toBe(false);
	});
	it('returns false for mismatched length', () => {
		expect(bboxesEqual([bb(1, 2, 3, 4)], [])).toBe(false);
	});
	it('returns false for null inputs', () => {
		expect(bboxesEqual(null, [bb(1, 2, 3, 4)])).toBe(false);
		expect(bboxesEqual([bb(1, 2, 3, 4)], null)).toBe(false);
	});
});

describe('applyHandleDelta', () => {
	const initial = bb(10, 20, 50, 60);

	it('moves the east edge on an "e" handle', () => {
		const out = applyHandleDelta(initial, 'e', 5, 0);
		expect(out).toEqual(bb(10, 20, 55, 60));
	});
	it('moves the north edge on an "n" handle', () => {
		const out = applyHandleDelta(initial, 'n', 0, -3);
		expect(out).toEqual(bb(10, 17, 50, 60));
	});
	it('moves two edges on a corner handle', () => {
		const out = applyHandleDelta(initial, 'se', 4, 6);
		expect(out).toEqual(bb(10, 20, 54, 66));
	});
	it('clamps against BBOX_MIN_PT when dragging past the opposite edge', () => {
		// west handle dragged far right — should stop BBOX_MIN_PT shy of x1.
		const out = applyHandleDelta(initial, 'w', 1000, 0);
		expect(out.x0).toBe(initial.x1 - BBOX_MIN_PT);
	});
	it('preserves the page field', () => {
		const out = applyHandleDelta(bb(0, 0, 10, 10, 7), 'e', 1, 0);
		expect(out.page).toBe(7);
	});
});

describe('nudgeBbox', () => {
	const b = bb(10, 10, 20, 20);

	it('plain (extend) left moves x0 outward', () => {
		expect(nudgeBbox(b, 'left', 3, false).x0).toBe(7);
	});
	it('shrink left moves x0 inward', () => {
		expect(nudgeBbox(b, 'left', 3, true).x0).toBe(13);
	});
	it('clamps shrink against the opposite edge', () => {
		expect(nudgeBbox(b, 'left', 999, true).x0).toBe(b.x1 - BBOX_MIN_PT);
	});
	it('leaves unrelated edges alone', () => {
		const out = nudgeBbox(b, 'top', 5, false);
		expect(out.y0).toBe(5);
		expect(out.x0).toBe(b.x0);
		expect(out.x1).toBe(b.x1);
		expect(out.y1).toBe(b.y1);
	});
});

describe('arrowKeyToNudge', () => {
	it('maps plain ArrowLeft to extend-left coarse step', () => {
		expect(arrowKeyToNudge('ArrowLeft', false, false)).toEqual({
			side: 'left',
			stepPt: 3,
			shrink: false
		});
	});
	it('maps Shift+ArrowLeft to shrink-right coarse step', () => {
		expect(arrowKeyToNudge('ArrowLeft', true, false)).toEqual({
			side: 'right',
			stepPt: 3,
			shrink: true
		});
	});
	it('maps Alt+ArrowUp to extend-top fine step', () => {
		expect(arrowKeyToNudge('ArrowUp', false, true)).toEqual({
			side: 'top',
			stepPt: 0.5,
			shrink: false
		});
	});
	it('maps Shift+Alt+ArrowDown to shrink-top fine step', () => {
		expect(arrowKeyToNudge('ArrowDown', true, true)).toEqual({
			side: 'top',
			stepPt: 0.5,
			shrink: true
		});
	});
	it('returns null for non-arrow keys', () => {
		expect(arrowKeyToNudge('Enter', false, false)).toBeNull();
		expect(arrowKeyToNudge('a', false, false)).toBeNull();
	});
});

describe('extendBboxToWord', () => {
	it('unions two bboxes on the same page', () => {
		const out = extendBboxToWord(bb(10, 10, 20, 20), bb(5, 15, 25, 18));
		expect(out).toEqual(bb(5, 10, 25, 20));
	});
	it('preserves the original page field', () => {
		const out = extendBboxToWord(bb(0, 0, 10, 10, 3), bb(5, 5, 15, 15, 3));
		expect(out.page).toBe(3);
	});
});

describe('shrinkBboxByWord', () => {
	const b = bb(10, 10, 50, 20);

	it('caps x1 when the word sits on the right half', () => {
		const out = shrinkBboxByWord(b, bb(40, 10, 48, 20));
		expect(out.x0).toBe(10);
		expect(out.x1).toBe(40);
	});
	it('caps x0 when the word sits on the left half', () => {
		const out = shrinkBboxByWord(b, bb(12, 10, 18, 20));
		expect(out.x0).toBe(18);
		expect(out.x1).toBe(50);
	});
	it('clamps the cap so the bbox cannot collapse', () => {
		// Word sits in the right half (wMid=30 == mid), so the right-half
		// path runs: x1 = max(x0 + BBOX_MIN_PT, wordBbox.x0). With
		// wordBbox.x0=11 vs x0+BBOX_MIN_PT=12, the clamp kicks in.
		const out = shrinkBboxByWord(b, bb(11, 10, 49, 20));
		expect(out.x1).toBe(b.x0 + BBOX_MIN_PT);
	});
});

describe('computeSplitBboxes', () => {
	it('splits a single-bbox detection at pdfX', () => {
		const result = computeSplitBboxes([bb(10, 10, 50, 20)], 0, 30);
		expect(result).not.toBeNull();
		expect(result!.bboxesA).toEqual([bb(10, 10, 30, 20)]);
		expect(result!.bboxesB).toEqual([bb(30, 10, 50, 20)]);
	});

	it('clamps pdfX so neither half collapses below BBOX_MIN_PT', () => {
		const result = computeSplitBboxes([bb(10, 10, 20, 20)], 0, 11);
		expect(result).not.toBeNull();
		// 11 is within BBOX_MIN_PT (2) of x0=10 → clamped to 12.
		expect(result!.bboxesA[0].x1).toBe(12);
		expect(result!.bboxesB[0].x0).toBe(12);
	});

	it('partitions multi-bbox detections along reader order', () => {
		const bboxes = [bb(0, 0, 10, 5), bb(0, 10, 10, 15), bb(0, 20, 10, 25)];
		const result = computeSplitBboxes(bboxes, 1, 4);
		expect(result).not.toBeNull();
		expect(result!.bboxesA).toEqual([bb(0, 0, 10, 5), bb(0, 10, 4, 15)]);
		expect(result!.bboxesB).toEqual([bb(4, 10, 10, 15), bb(0, 20, 10, 25)]);
	});

	it('returns null when bboxIndex is out of range', () => {
		expect(computeSplitBboxes([bb(0, 0, 10, 10)], 5, 5)).toBeNull();
	});

	it('deep-clones surrounding bboxes so the caller cannot mutate the source', () => {
		const src = [bb(0, 0, 10, 5), bb(0, 10, 10, 15)];
		const result = computeSplitBboxes(src, 1, 5);
		expect(result).not.toBeNull();
		result!.bboxesA[0].x1 = 999;
		expect(src[0].x1).toBe(10);
	});
});
