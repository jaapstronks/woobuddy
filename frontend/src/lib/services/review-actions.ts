/**
 * Detection review action helpers extracted from the review page.
 *
 * Each function encapsulates the command creation + undo-push + page-touch
 * pattern so the page component stays declarative. All functions import
 * the singleton stores directly.
 */

import { detectionStore } from '$lib/stores/detections.svelte';
import { pageReviewStore } from '$lib/stores/page-reviews.svelte';
import {
	undoStore,
	ReviewStatusCommand,
	ChangeArticleCommand,
	SetSubjectRoleCommand,
	BatchCommand,
	type Command
} from '$lib/stores/undo.svelte';
import { HIGH_CONFIDENCE_THRESHOLD } from '$lib/config/thresholds';
import type { WooArticleCode, SubjectRole } from '$lib/types';

/**
 * Nudge every page a detection touches from `unreviewed` to `in_progress`.
 * Pages already marked `complete` or `flagged` are left alone.
 */
export function touchDetectionPages(id: string): void {
	const det = detectionStore.byId[id];
	if (!det?.bounding_boxes) return;
	const pages = new Set(det.bounding_boxes.map((b) => b.page));
	for (const p of pages) void pageReviewStore.markInProgressIfUnreviewed(p);
}

/**
 * Build a ReviewStatusCommand capturing the detection's current state
 * so that undo restores it exactly.
 */
export function makeStatusCommand(
	id: string,
	nextStatus: 'accepted' | 'rejected' | 'deferred' | 'pending',
	nextArticle?: WooArticleCode
): ReviewStatusCommand | null {
	const det = detectionStore.byId[id];
	if (!det) return null;
	return new ReviewStatusCommand(
		id,
		det.review_status,
		nextStatus,
		det.woo_article ?? undefined,
		nextArticle ?? det.woo_article ?? undefined
	);
}

export function handleAccept(id: string): void {
	const cmd = makeStatusCommand(id, 'accepted');
	if (cmd) {
		undoStore.push(cmd);
		touchDetectionPages(id);
	}
}

export function handleRedactWithArticle(id: string, article: WooArticleCode): void {
	const cmd = makeStatusCommand(id, 'accepted', article);
	if (cmd) {
		undoStore.push(cmd);
		touchDetectionPages(id);
	}
}

export function handleReject(id: string): void {
	const cmd = makeStatusCommand(id, 'rejected');
	if (cmd) {
		undoStore.push(cmd);
		touchDetectionPages(id);
	}
}

export function handleDefer(id: string): void {
	const cmd = makeStatusCommand(id, 'deferred');
	if (cmd) {
		undoStore.push(cmd);
		touchDetectionPages(id);
	}
}

export function handleReopen(id: string): void {
	const cmd = makeStatusCommand(id, 'pending');
	if (cmd) {
		undoStore.push(cmd);
		touchDetectionPages(id);
	}
}

export async function handleChangeArticle(id: string, nextArticle: WooArticleCode): Promise<void> {
	const det = detectionStore.byId[id];
	if (!det) return;
	if (det.woo_article === nextArticle) return;
	const cmd = new ChangeArticleCommand(id, det.woo_article, nextArticle);
	try {
		await undoStore.push(cmd);
	} catch {
		// detectionStore.error carries the message.
	}
}

export async function handleSetSubjectRole(id: string, role: SubjectRole): Promise<void> {
	const det = detectionStore.byId[id];
	if (!det) return;
	if (det.subject_role === role) return;
	const cmd = new SetSubjectRoleCommand(
		id,
		det.subject_role ?? null,
		role,
		det.review_status
	);
	try {
		await undoStore.push(cmd);
		touchDetectionPages(id);
	} catch {
		// detectionStore.error carries the message.
	}
}

export function handleSaveMotivation(id: string, text: string): void {
	detectionStore.review(id, { review_status: 'edited', motivation_text: text });
}

function buildAcceptBatch(dets: typeof detectionStore.all): Command[] {
	return dets.map(
		(d) =>
			new ReviewStatusCommand(
				d.id,
				d.review_status,
				'accepted',
				d.woo_article ?? undefined,
				d.woo_article ?? undefined
			)
	);
}

export async function handleAcceptAllTier1(): Promise<void> {
	const children = buildAcceptBatch(
		detectionStore.all.filter((d) => d.tier === '1' && d.review_status === 'pending')
	);
	if (children.length === 0) return;
	await undoStore.push(new BatchCommand(`Accepteer alle Tier 1 (${children.length})`, children));
}

export async function handleAcceptHighConfidenceTier2(): Promise<void> {
	const children = buildAcceptBatch(
		detectionStore.all.filter(
			(d) =>
				d.tier === '2' &&
				d.review_status === 'pending' &&
				d.confidence >= HIGH_CONFIDENCE_THRESHOLD
		)
	);
	if (children.length === 0) return;
	await undoStore.push(
		new BatchCommand(`Accepteer hoge-zekerheid Tier 2 (${children.length})`, children)
	);
}
