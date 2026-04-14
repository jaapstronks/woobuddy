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

import type {
	BoundingBox,
	DetectionTier,
	EntityType,
	ReviewStatus,
	SubjectRole,
	WooArticleCode
} from '$lib/types';
import { detectionStore } from '$lib/stores/detections.svelte';
import { referenceNamesStore } from '$lib/stores/reference-names.svelte';
import { customTermsStore } from '$lib/stores/custom-terms.svelte';

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
 * Adjust a detection's bounding boxes (#11 boundary adjustment).
 *
 * Captures the pre-adjust bboxes and review_status at construction time so
 * `reverse()` can restore them exactly. On the server side the very first
 * forward() triggers a snapshot into `original_bounding_boxes`; subsequent
 * forward/reverse pairs just swap the `bounding_boxes` value back and forth
 * — the baseline snapshot is preserved across the whole session.
 */
export class BoundaryAdjustCommand implements Command {
	readonly label = 'Grenscorrectie';

	constructor(
		private readonly detectionId: string,
		private readonly previousBboxes: BoundingBox[],
		private readonly nextBboxes: BoundingBox[],
		private readonly previousStatus: ReviewStatus
	) {}

	get affectedDetectionIds(): string[] {
		return [this.detectionId];
	}

	async forward(): Promise<void> {
		// Let the server flip review_status to "edited".
		await detectionStore.adjustBoundary(this.detectionId, this.nextBboxes);
	}

	async reverse(): Promise<void> {
		// Reverting the bboxes should also revert the status to whatever the
		// detection had before the adjustment (often "accepted" / "pending" /
		// "auto_accepted") — otherwise a two-step undo would leave the row
		// stuck at "edited" after the coordinates were already rolled back.
		await detectionStore.adjustBoundary(
			this.detectionId,
			this.previousBboxes,
			{ review_status: this.previousStatus }
		);
	}
}

/**
 * Change a detection's woo_article in place (#15 Tier 2 card picker).
 *
 * Keeps the row's review_status untouched — only the article label moves —
 * and reverses to the previous article exactly. If the reviewer picks the
 * same article that is already set, the caller should skip the push rather
 * than emit a no-op command.
 */
export class ChangeArticleCommand implements Command {
	readonly label = 'Woo-grond wijzigen';

	constructor(
		private readonly detectionId: string,
		private readonly previousArticle: WooArticleCode | null,
		private readonly nextArticle: WooArticleCode
	) {}

	get affectedDetectionIds(): string[] {
		return [this.detectionId];
	}

	async forward(): Promise<void> {
		await detectionStore.review(this.detectionId, { woo_article: this.nextArticle });
	}

	async reverse(): Promise<void> {
		// `review()` sends whatever is passed; to restore a null we'd need a
		// server-side "clear" semantic. Previous article being null is vanishingly
		// rare in practice (Tier 2 rows are created with a pre-filled article),
		// so we simply skip the reverse in that edge case — the user can still
		// re-pick manually.
		if (!this.previousArticle) return;
		await detectionStore.review(this.detectionId, { woo_article: this.previousArticle });
	}
}

/**
 * Set a detection's `subject_role` (#15 Tier 2 role chips). The chip records
 * *why* the reviewer kept a detection visible (or whose data it is) — it
 * does not decide whether the row is redacted. The Lakken/Niet lakken
 * buttons are the single source of truth for `review_status`. A single
 * undo restores the previous role.
 */
export class SetSubjectRoleCommand implements Command {
	readonly label: string;

	constructor(
		private readonly detectionId: string,
		private readonly previousRole: SubjectRole | null,
		private readonly nextRole: SubjectRole,
		// Kept in the signature for call-site symmetry with other commands
		// that needed the prior status. This command no longer touches status
		// so the value is unused, but removing the parameter would churn all
		// callers and the paired undo tests for no gain.
		_previousStatus: ReviewStatus
	) {
		this.label =
			nextRole === 'publiek_functionaris'
				? 'Markeer als publiek functionaris'
				: nextRole === 'burger'
					? 'Markeer als burger'
					: 'Markeer als ambtenaar';
	}

	get affectedDetectionIds(): string[] {
		return [this.detectionId];
	}

	async forward(): Promise<void> {
		await detectionStore.review(this.detectionId, { subject_role: this.nextRole });
	}

	async reverse(): Promise<void> {
		// Reverting the role either restores the previous label or (for the
		// very first chip click) clears it back to null via the explicit
		// `clear_subject_role` flag.
		const payload: {
			subject_role?: SubjectRole;
			clear_subject_role?: boolean;
		} = {};
		if (this.previousRole) {
			payload.subject_role = this.previousRole;
		} else {
			payload.clear_subject_role = true;
		}
		await detectionStore.review(this.detectionId, payload);
	}
}

/**
 * Add a name to the per-document reference list (#17). The command
 * remembers the server-assigned id after the first `forward()` so
 * `reverse()` can delete that exact row and a subsequent redo can
 * recreate it (as a brand-new row — we don't try to preserve the id
 * across a delete/recreate cycle because the analyze pipeline only
 * cares about the normalized display name, not the id).
 *
 * The review page injects a `reanalyze` callback so that every forward
 * and reverse triggers a fresh `/api/analyze` pass with the updated
 * list — that's what flips newly-matched detections to `rejected` (on
 * add) or back to `pending` (on remove). Keeping that concern outside
 * the command means we don't have to thread the extraction state
 * through the undo store.
 */
export class AddReferenceNameCommand implements Command {
	readonly label = 'Naam toevoegen aan lijst';
	private createdId: string | null = null;

	constructor(
		private readonly displayName: string,
		private readonly reanalyze: () => Promise<void>
	) {}

	get affectedDetectionIds(): string[] {
		// Reference-name commands don't target a specific detection — the
		// re-analysis may touch zero or many rows depending on what's in
		// the document. Returning an empty list skips the viewer flash,
		// which is the right default here (a bulk re-analysis is not
		// localized enough to highlight meaningfully).
		return [];
	}

	async forward(): Promise<void> {
		const created = await referenceNamesStore.add(this.displayName);
		if (!created) {
			// Store already set the error; signal the undo store to drop
			// this command rather than pushing a no-op entry.
			throw new Error(this.label + ' mislukt');
		}
		this.createdId = created.id;
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		if (!this.createdId) return;
		const ok = await referenceNamesStore.remove(this.createdId);
		if (!ok) return;
		this.createdId = null;
		await this.reanalyze();
	}
}

/**
 * Remove a name from the per-document reference list (#17). Captures
 * the original row at construction time so `reverse()` can recreate it
 * with the same display name (the server assigns a new id — that's
 * fine, the normalized name is what matters for matching).
 */
export class RemoveReferenceNameCommand implements Command {
	readonly label = 'Naam verwijderen van lijst';
	private currentId: string;

	constructor(
		initialId: string,
		private readonly displayName: string,
		private readonly reanalyze: () => Promise<void>
	) {
		this.currentId = initialId;
	}

	get affectedDetectionIds(): string[] {
		return [];
	}

	async forward(): Promise<void> {
		const ok = await referenceNamesStore.remove(this.currentId);
		if (!ok) {
			throw new Error(this.label + ' mislukt');
		}
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		// Re-create under a fresh id — the normalized name is what the
		// analyze pipeline matches on, not the id.
		const recreated = await referenceNamesStore.add(this.displayName);
		if (!recreated) return;
		this.currentId = recreated.id;
		await this.reanalyze();
	}
}

/**
 * Add a term to the per-document custom wordlist (#21). Mirrors
 * `AddReferenceNameCommand`: remembers the server-assigned id on the
 * first `forward()` so `reverse()` can delete that exact row, and a
 * subsequent redo recreates it. Each forward/reverse triggers a
 * re-analysis via the injected callback so the resulting `custom`
 * detections appear or disappear in the sidebar.
 *
 * Unlike the reference-name variant, this command also flashes the
 * detections that the re-analysis produced. The id list is captured
 * after the re-analysis resolves because those detection ids don't
 * exist until the server has re-run the pipeline.
 */
export class AddCustomTermCommand implements Command {
	readonly label = 'Zoekterm toevoegen';
	private createdId: string | null = null;

	constructor(
		private readonly term: string,
		private readonly wooArticle: string,
		private readonly reanalyze: () => Promise<void>
	) {}

	get affectedDetectionIds(): string[] {
		// A reanalysis may touch many detections across the document;
		// flashing all of them would be noisy. Returning an empty list
		// skips the viewer flash — the same default as the reference-
		// name commands for the same reason.
		return [];
	}

	async forward(): Promise<void> {
		const created = await customTermsStore.add(this.term, this.wooArticle);
		if (!created) {
			throw new Error(this.label + ' mislukt');
		}
		this.createdId = created.id;
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		if (!this.createdId) return;
		const ok = await customTermsStore.remove(this.createdId);
		if (!ok) return;
		this.createdId = null;
		await this.reanalyze();
	}
}

/**
 * Remove a term from the per-document custom wordlist (#21). Captures
 * the term's text + article at construction time so `reverse()` can
 * recreate it through the store (the server assigns a fresh id — the
 * matcher only cares about the normalized term, not the id).
 */
export class RemoveCustomTermCommand implements Command {
	readonly label = 'Zoekterm verwijderen';
	private currentId: string;

	constructor(
		initialId: string,
		private readonly term: string,
		private readonly wooArticle: string,
		private readonly reanalyze: () => Promise<void>
	) {
		this.currentId = initialId;
	}

	get affectedDetectionIds(): string[] {
		return [];
	}

	async forward(): Promise<void> {
		const ok = await customTermsStore.remove(this.currentId);
		if (!ok) {
			throw new Error(this.label + ' mislukt');
		}
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		const recreated = await customTermsStore.add(this.term, this.wooArticle);
		if (!recreated) return;
		this.currentId = recreated.id;
		await this.reanalyze();
	}
}

/**
 * Sweep a single structure block (email header or signature block) —
 * accept every detection inside the block that is still `pending`, skip
 * the rest. One undo restores all affected detections to their previous
 * status in the reverse order they were accepted.
 *
 * The caller (#20 chip handler) has already filtered detections to "in
 * this block AND pending" before constructing the command. The command
 * captures the previous (`pending`) status at construction time so
 * reverse() is deterministic even if the document cache mutates between
 * forward and reverse runs.
 */
export class SweepBlockCommand implements Command {
	readonly label: string;
	private readonly targets: Array<{
		id: string;
		previousStatus: ReviewStatus;
		previousArticle: WooArticleCode | null;
		nextArticle: WooArticleCode | null;
	}>;

	constructor(
		blockKind: 'email_header' | 'signature_block',
		targets: Array<{
			id: string;
			previousStatus: ReviewStatus;
			previousArticle: WooArticleCode | null;
			nextArticle: WooArticleCode | null;
		}>
	) {
		this.targets = targets;
		const kindLabel =
			blockKind === 'email_header' ? 'e-mailheader' : 'handtekeningblok';
		this.label = `Lak ${kindLabel} (${targets.length})`;
	}

	get affectedDetectionIds(): string[] {
		return this.targets.map((t) => t.id);
	}

	async forward(): Promise<void> {
		for (const t of this.targets) {
			await detectionStore.review(t.id, {
				review_status: 'accepted' as ReviewStatus,
				...(t.nextArticle ? { woo_article: t.nextArticle } : {})
			});
		}
	}

	async reverse(): Promise<void> {
		for (let i = this.targets.length - 1; i >= 0; i--) {
			const t = this.targets[i];
			await detectionStore.review(t.id, {
				review_status: t.previousStatus,
				...(t.previousArticle ? { woo_article: t.previousArticle } : {})
			});
		}
	}
}

/**
 * Apply the same review decision to every detection whose normalized
 * entity_text matches a target name (#20 same-name sweep). Captures the
 * previous review_status for each affected detection so one undo
 * restores the whole set.
 *
 * The command intentionally does NOT sweep detections that already have
 * a decision different from the target's "before" state — the reviewer
 * is saying "apply this new decision to every other occurrence of this
 * name", not "overwrite whatever the reviewer had already decided
 * elsewhere". The list of target ids is curated by the caller.
 */
export class SameNameSweepCommand implements Command {
	readonly label: string;
	private readonly targets: Array<{
		id: string;
		previousStatus: ReviewStatus;
	}>;
	private readonly nextStatus: ReviewStatus;

	constructor(
		displayName: string,
		nextStatus: ReviewStatus,
		targets: Array<{ id: string; previousStatus: ReviewStatus }>
	) {
		this.targets = targets;
		this.nextStatus = nextStatus;
		const verb =
			nextStatus === 'accepted'
				? 'Lak'
				: nextStatus === 'rejected'
					? 'Niet lakken'
					: 'Wijzig';
		this.label = `${verb} '${displayName}' (${targets.length})`;
	}

	get affectedDetectionIds(): string[] {
		return this.targets.map((t) => t.id);
	}

	async forward(): Promise<void> {
		for (const t of this.targets) {
			await detectionStore.review(t.id, { review_status: this.nextStatus });
		}
	}

	async reverse(): Promise<void> {
		for (let i = this.targets.length - 1; i >= 0; i--) {
			const t = this.targets[i];
			await detectionStore.review(t.id, { review_status: t.previousStatus });
		}
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
