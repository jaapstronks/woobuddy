/**
 * Undo/redo store (#08).
 *
 * A plain command stack: every editing action in the review page is wrapped
 * in a `Command` with `forward()` and `reverse()`, pushed here, and from
 * then on `Ctrl+Z` walks it back. State is per-document and in-memory only
 * — clearing the document (navigation, reload) clears the stacks.
 *
 * The commands themselves talk to `detectionStore`, so this file is purely
 * about bookkeeping — it owns no API calls. That keeps the undo semantics
 * one place and makes adding new command types later (boundary adjust,
 * split/merge, search-and-redact batch) a matter of adding another class.
 */

import type { BoundingBox, DetectionTier, EntityType, ReviewStatus, WooArticleCode } from '$lib/types';
import { detectionStore } from '$lib/stores/detections.svelte';

// ---------------------------------------------------------------------------
// Command interface
// ---------------------------------------------------------------------------

export interface Command {
	/** Short Dutch label for debugging / future toasts. */
	readonly label: string;
	/** IDs of detections this command affects — used to flash overlays on (un)redo. */
	readonly affectedDetectionIds: string[];
	/** Apply the command (initial run) — used for `push` and `redo`. */
	forward(): Promise<void>;
	/** Roll the command back — used for `undo`. */
	reverse(): Promise<void>;
}

// ---------------------------------------------------------------------------
// Concrete commands
// ---------------------------------------------------------------------------

/**
 * Create a reviewer-authored redaction. Remembers the id that was assigned
 * by the server on the first `forward()` so `reverse()` can delete it and
 * a subsequent redo can re-create it through the same manual endpoint.
 */
export class CreateManualCommand implements Command {
	readonly label: string;
	private createdId: string | null = null;

	constructor(
		private readonly params: {
			documentId: string;
			bboxes: BoundingBox[];
			selectedText: string;
			entityType: EntityType;
			tier: DetectionTier;
			wooArticle: WooArticleCode;
			motivation: string;
			/** Defaults to "manual"; #09 passes "search_redact" for bulk hits. */
			source?: 'manual' | 'search_redact';
		}
	) {
		this.label = params.source === 'search_redact' ? 'Zoek & lak' : 'Handmatige lakking';
	}

	get affectedDetectionIds(): string[] {
		return this.createdId ? [this.createdId] : [];
	}

	async forward(): Promise<void> {
		const created = await detectionStore.createManual(this.params);
		if (!created) {
			// Detection store already surfaced the error; signal the undo store
			// to drop this command rather than pushing an empty entry.
			throw new Error(this.label + ' mislukt');
		}
		this.createdId = created.id;
	}

	async reverse(): Promise<void> {
		if (!this.createdId) return;
		// Let the flash animation (triggered by `undoStore.lastAffected`
		// before this reverse started) play on the real overlay before we
		// delete it — otherwise the visual cue lands on an element that no
		// longer exists.
		await new Promise((r) => setTimeout(r, 300));
		await detectionStore.remove(this.createdId);
		// Keep the id: a subsequent redo creates a *new* row, overwriting it.
	}
}

/**
 * Change a detection's review_status (accept / reject / defer). Captures
 * the previous status at construction time so `reverse()` can restore it
 * exactly, including the `auto_accepted` starting state for Tier 1 rows.
 */
export class ReviewStatusCommand implements Command {
	readonly label: string;

	constructor(
		private readonly detectionId: string,
		private readonly previousStatus: ReviewStatus,
		private readonly nextStatus: ReviewStatus,
		private readonly previousArticle?: WooArticleCode | null,
		private readonly nextArticle?: WooArticleCode | null
	) {
		this.label =
			nextStatus === 'accepted' ? 'Accepteren'
			: nextStatus === 'rejected' ? 'Afwijzen'
			: nextStatus === 'deferred' ? 'Uitstellen'
			: 'Statuswijziging';
	}

	get affectedDetectionIds(): string[] {
		return [this.detectionId];
	}

	async forward(): Promise<void> {
		await detectionStore.review(this.detectionId, {
			review_status: this.nextStatus,
			...(this.nextArticle ? { woo_article: this.nextArticle } : {})
		});
	}

	async reverse(): Promise<void> {
		await detectionStore.review(this.detectionId, {
			review_status: this.previousStatus,
			...(this.previousArticle ? { woo_article: this.previousArticle } : {})
		});
	}
}

/**
 * Wraps an array of commands as a single undo entry. Used by the "Accept
 * all Tier 1" / "Accept high-confidence Tier 2" batch actions so one
 * `Ctrl+Z` undoes the whole sweep. Children run sequentially (the review
 * endpoints are independent, but sequential keeps error handling sane)
 * and reverse in the opposite order.
 */
export class BatchCommand implements Command {
	readonly label: string;

	constructor(label: string, private readonly children: Command[]) {
		this.label = label;
	}

	get affectedDetectionIds(): string[] {
		return this.children.flatMap((c) => c.affectedDetectionIds);
	}

	async forward(): Promise<void> {
		for (const child of this.children) {
			await child.forward();
		}
	}

	async reverse(): Promise<void> {
		for (let i = this.children.length - 1; i >= 0; i--) {
			await this.children[i].reverse();
		}
	}
}

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
