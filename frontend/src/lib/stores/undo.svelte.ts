/**
 * Undo/redo store (#08).
 *
 * A plain command stack: every editing action in the review page is wrapped
 * in a `Command` with `forward()` and `reverse()`, pushed here, and from
 * then on `Ctrl+Z` walks it back. State is per-document and in-memory only
 * — clearing the document (navigation, reload) clears the stacks.
 *
 * The concrete command classes live under `./undo/*.ts`; this file owns
 * only the runes-backed stacks plus a re-export facade so existing call
 * sites can keep importing everything from `$lib/stores/undo.svelte`.
 * Splitting the commands out keeps any one file small enough to reason
 * about and lets new command types land in the right neighbourhood
 * (single-detection, list mutation, sweep) without bloating the store.
 */

import type { Command } from './undo/command';

// Re-export the interface and every concrete command so the review page
// (and the unit tests) keep their existing import surface unchanged.
export type { Command };
export {
	CreateManualCommand,
	ReviewStatusCommand,
	BoundaryAdjustCommand,
	ChangeArticleCommand,
	SetSubjectRoleCommand
} from './undo/manual-commands';
export {
	AddReferenceNameCommand,
	RemoveReferenceNameCommand,
	AddCustomTermCommand,
	RemoveCustomTermCommand
} from './undo/list-commands';
export {
	SweepBlockCommand,
	SameNameSweepCommand,
	BatchCommand
} from './undo/sweep-commands';

// ---------------------------------------------------------------------------
// Stacks
// ---------------------------------------------------------------------------

const MAX_STACK = 100;

let undoStack = $state<Command[]>([]);
let redoStack = $state<Command[]>([]);
let busy = $state(false);
/** Ids to flash on the viewer after the current undo/redo settles. */
let lastAffected = $state<string[]>([]);

const canUndo = $derived(undoStack.length > 0 && !busy);
const canRedo = $derived(redoStack.length > 0 && !busy);

/**
 * Run `cmd.forward()` and, on success, push it onto the undo stack.
 * Throws if the forward fails — callers can surface the error and the
 * stack stays clean (no half-applied commands).
 */
async function push(cmd: Command): Promise<void> {
	if (busy) return;
	busy = true;
	try {
		await cmd.forward();
	} catch (e) {
		// Don't pollute the stack with a command that didn't take effect.
		throw e;
	} finally {
		busy = false;
	}
	undoStack = [...undoStack, cmd];
	if (undoStack.length > MAX_STACK) {
		undoStack = undoStack.slice(undoStack.length - MAX_STACK);
	}
	// Any new action invalidates the redo branch — standard undo semantics.
	redoStack = [];
	lastAffected = cmd.affectedDetectionIds;
}

async function undo(): Promise<void> {
	if (!canUndo) return;
	const cmd = undoStack[undoStack.length - 1];
	busy = true;
	// Set `lastAffected` *before* running reverse() so the flash effect
	// fires on the current (pre-reverse) DOM — important for
	// `CreateManualCommand` where the overlay disappears once the row is
	// deleted. Commands that delete rows pre-delay their reverse so the
	// flash actually has something to land on.
	lastAffected = cmd.affectedDetectionIds;
	try {
		await cmd.reverse();
	} finally {
		busy = false;
	}
	undoStack = undoStack.slice(0, -1);
	redoStack = [...redoStack, cmd];
}

async function redo(): Promise<void> {
	if (!canRedo) return;
	const cmd = redoStack[redoStack.length - 1];
	busy = true;
	try {
		await cmd.forward();
	} finally {
		busy = false;
	}
	redoStack = redoStack.slice(0, -1);
	undoStack = [...undoStack, cmd];
	lastAffected = cmd.affectedDetectionIds;
}

function clear() {
	undoStack = [];
	redoStack = [];
	lastAffected = [];
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const undoStore = {
	get canUndo() {
		return canUndo;
	},
	get canRedo() {
		return canRedo;
	},
	get busy() {
		return busy;
	},
	get undoDepth() {
		return undoStack.length;
	},
	get redoDepth() {
		return redoStack.length;
	},
	get lastAffected() {
		return lastAffected;
	},
	push,
	undo,
	redo,
	clear
};
