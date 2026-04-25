/**
 * Single-detection commands: creating a manual redaction, changing
 * review_status, adjusting bbox boundaries, swapping the woo_article,
 * and setting the subject_role chip.
 *
 * These all talk to `detectionStore` directly — undo bookkeeping lives
 * in `../undo.svelte.ts`.
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
import type { Command } from './command';

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
					: nextRole === 'geen_persoon'
						? 'Markeer als geen persoon'
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
