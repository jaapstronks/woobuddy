import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { Detection } from '$lib/types';

// ---------------------------------------------------------------------------
// detectionStore fake
//
// A small in-memory stand-in that implements the four methods split/merge
// undo touches (`byId`, `split`, `merge`, `replaceRows`) with the same
// semantics as the real store: both actions delete their inputs and insert
// freshly generated rows. Testing against a fake rather than spies is what
// makes the round-trip assertions ("the document is back where it started")
// meaningful.
// ---------------------------------------------------------------------------

const { fake } = vi.hoisted(() => {
	type Det = { id: string; [k: string]: unknown };
	const state: { rows: Det[]; error: string | null; nextId: number } = {
		rows: [],
		error: null,
		nextId: 0
	};
	const fake = {
		state,
		get byId() {
			return Object.fromEntries(state.rows.map((d) => [d.id, d]));
		},
		get error() {
			return state.error;
		},
		async split(id: string, bboxesA: unknown, bboxesB: unknown) {
			const original = state.rows.find((d) => d.id === id);
			if (!original) return null;
			const halves = [
				{ ...original, id: `split-${state.nextId++}`, bounding_boxes: bboxesA },
				{ ...original, id: `split-${state.nextId++}`, bounding_boxes: bboxesB }
			];
			state.rows = [...state.rows.filter((d) => d.id !== id), ...halves];
			return halves;
		},
		async merge(ids?: string[]) {
			if (!ids || ids.length < 2) {
				state.error = 'Selecteer ten minste twee detecties om samen te voegen.';
				return null;
			}
			const originals = ids.map((id) => state.rows.find((d) => d.id === id));
			if (originals.some((d) => d === undefined)) return null;
			const merged = { ...originals[0]!, id: `merged-${state.nextId++}` };
			const gone = new Set(ids);
			state.rows = [...state.rows.filter((d) => !gone.has(d.id)), merged];
			return merged;
		},
		async replaceRows(args: {
			removeIds: string[];
			insert: Det[];
			select?: string | null;
		}) {
			const gone = new Set(args.removeIds);
			state.rows = [...state.rows.filter((d) => !gone.has(d.id)), ...args.insert];
		}
	};
	return { fake };
});

vi.mock('$lib/stores/detections.svelte', () => ({ detectionStore: fake }));
vi.mock('$lib/stores/reference-names.svelte', () => ({
	referenceNamesStore: { add: vi.fn(), remove: vi.fn() }
}));
vi.mock('$lib/stores/custom-terms.svelte', () => ({
	customTermsStore: { add: vi.fn(), remove: vi.fn() }
}));

import { undoStore, SplitCommand, MergeCommand, type Command } from './undo.svelte';

const BOX_A = [{ page: 0, x0: 0, y0: 0, x1: 5, y1: 10 }];
const BOX_B = [{ page: 0, x0: 5, y0: 0, x1: 10, y1: 10 }];

function seed(ids: string[]) {
	fake.state.rows = ids.map((id) => ({
		id,
		bounding_boxes: [{ page: 0, x0: 0, y0: 0, x1: 10, y1: 10 }],
		review_status: 'accepted'
	}));
	fake.state.error = null;
	fake.state.nextId = 0;
}

function ids(): string[] {
	return fake.state.rows.map((d) => d.id).sort();
}

beforeEach(() => {
	undoStore.clear();
	vi.useRealTimers();
});

describe('SplitCommand (#66/2)', () => {
	it('replaces the original with two halves on forward', async () => {
		seed(['det-1', 'det-2']);
		await new SplitCommand('det-1', BOX_A, BOX_B).forward();
		expect(ids()).toEqual(['det-2', 'split-0', 'split-1']);
	});

	it('undo restores the original row and drops both halves', async () => {
		seed(['det-1', 'det-2']);
		const cmd = new SplitCommand('det-1', BOX_A, BOX_B);
		await cmd.forward();
		await cmd.reverse();
		expect(ids()).toEqual(['det-1', 'det-2']);
		expect(fake.byId['det-1'].bounding_boxes).toEqual([
			{ page: 0, x0: 0, y0: 0, x1: 10, y1: 10 }
		]);
	});

	it('redo splits again after an undo', async () => {
		seed(['det-1']);
		const cmd = new SplitCommand('det-1', BOX_A, BOX_B);
		await cmd.forward();
		await cmd.reverse();
		await cmd.forward();
		expect(fake.state.rows).toHaveLength(2);
		expect(fake.state.rows.every((d) => d.id.startsWith('split-'))).toBe(true);
	});

	it('throws instead of pushing when the detection is gone', async () => {
		seed([]);
		await expect(new SplitCommand('det-1', BOX_A, BOX_B).forward()).rejects.toThrow();
	});
});

describe('MergeCommand (#66/2)', () => {
	it('replaces the inputs with one merged row on forward', async () => {
		seed(['det-1', 'det-2', 'det-3']);
		await new MergeCommand(['det-1', 'det-2']).forward();
		expect(ids()).toEqual(['det-3', 'merged-0']);
	});

	it('undo restores every original row and drops the merged one', async () => {
		seed(['det-1', 'det-2', 'det-3']);
		const cmd = new MergeCommand(['det-1', 'det-2']);
		await cmd.forward();
		await cmd.reverse();
		expect(ids()).toEqual(['det-1', 'det-2', 'det-3']);
	});

	it('redo merges again without a live multi-select', async () => {
		seed(['det-1', 'det-2']);
		const cmd = new MergeCommand(['det-1', 'det-2']);
		await cmd.forward();
		await cmd.reverse();
		await cmd.forward();
		expect(ids()).toEqual(['merged-1']);
	});
});

describe('undo stack round-trip through the store', () => {
	it('Ctrl+Z after a split reverts the split, not an earlier action', async () => {
		seed(['det-1']);
		// An unrelated command sits underneath: before split/merge were
		// commands, this is the one that got undone instead (#66/2).
		let unrelatedUndone = false;
		const unrelated: Command = {
			label: 'Iets anders',
			affectedDetectionIds: [],
			forward: async () => {},
			reverse: async () => {
				unrelatedUndone = true;
			}
		};
		await undoStore.push(unrelated);
		await undoStore.push(new SplitCommand('det-1', BOX_A, BOX_B));

		await undoStore.undo();

		expect(unrelatedUndone).toBe(false);
		expect(ids()).toEqual(['det-1']);
	});

	it('Ctrl+Z after a merge restores the merged rows', async () => {
		seed(['det-1', 'det-2']);
		await undoStore.push(new MergeCommand(['det-1', 'det-2']));
		expect(ids()).toEqual(['merged-0']);

		await undoStore.undo();

		expect(ids()).toEqual(['det-1', 'det-2']);
	});
});

describe('undoStore.push serialisation (#66/10)', () => {
	it('keeps every command pushed while an earlier one is still settling', async () => {
		const order: number[] = [];
		const slow = (n: number): Command => ({
			label: `cmd-${n}`,
			affectedDetectionIds: [],
			forward: async () => {
				await new Promise((r) => setTimeout(r, 5));
				order.push(n);
			},
			reverse: async () => {}
		});

		// Fired without awaiting, the way a reviewer hammering A/R/D does.
		const pushes = [
			undoStore.push(slow(1)),
			undoStore.push(slow(2)),
			undoStore.push(slow(3))
		];
		await Promise.all(pushes);

		expect(undoStore.undoDepth).toBe(3);
		expect(order).toEqual([1, 2, 3]);
	});

	it('a failing command does not wedge the queue or land on the stack', async () => {
		const failing: Command = {
			label: 'kapot',
			affectedDetectionIds: [],
			forward: async () => {
				throw new Error('nope');
			},
			reverse: async () => {}
		};
		const ok: Command = {
			label: 'goed',
			affectedDetectionIds: [],
			forward: async () => {},
			reverse: async () => {}
		};

		const rejected = undoStore.push(failing);
		const accepted = undoStore.push(ok);

		await expect(rejected).rejects.toThrow('nope');
		await accepted;
		expect(undoStore.undoDepth).toBe(1);
	});
});
