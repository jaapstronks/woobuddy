/**
 * Bulk commands: sweeping a structure block, sweeping all occurrences
 * of the same name, and a generic batch wrapper that bundles arbitrary
 * children under a single undo entry.
 */

import type { ReviewStatus, WooArticleCode } from '$lib/types';
import { detectionStore } from '$lib/stores/detections.svelte';
import type { Command } from './command';

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
