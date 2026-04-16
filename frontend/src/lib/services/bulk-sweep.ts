/**
 * Bulk-sweep helpers (#20) — extracted from routes/review/[docId]/+page.svelte.
 *
 * These are the real business rules behind "accept every pending row in
 * this email header / signature block" and "accept every occurrence of
 * the same name at once". The page file previously owned ~100 lines of
 * this logic alongside everything else; pulling it here keeps the page
 * focused on layout and store wiring while giving the sweeps a clean
 * unit-test seam.
 *
 * These helpers take `touchPages` as a callback so this module stays
 * independent of the page-review store — the review page already owns
 * that detail through `touchDetectionPages`, so we pass it in rather
 * than importing pageReviewStore here.
 */

import { detectionStore } from '$lib/stores/detections.svelte';
import { structureSpansStore } from '$lib/stores/structure-spans.svelte';
import {
	undoStore,
	SweepBlockCommand,
	SameNameSweepCommand
} from '$lib/stores/undo.svelte';
import {
	spanKey,
	detectionInsideSpan,
	findSameNameDetections
} from '$lib/utils/structure-matching';
import type { StructureSpan, ReviewStatus } from '$lib/types';

type TouchPagesFn = (detectionId: string) => void;

/**
 * Sweep every pending detection inside the structure span identified by
 * `key`. Detections that already have a non-pending decision are left
 * alone — the reviewer explicitly decided those and must not be
 * overwritten. Builds a single undo command covering the whole block.
 */
export async function sweepBlock(key: string, touchPages: TouchPagesFn): Promise<void> {
	const span = structureSpansStore.spans.find((s) => spanKey(s) === key);
	if (!span) return;
	if (span.kind !== 'email_header' && span.kind !== 'signature_block') return;

	// Resolve targets against the full detection list, not the filtered
	// view — the reviewer clicked "sweep this whole block" and expects
	// every pending row inside it to be accepted regardless of the
	// current sidebar filter.
	const inBlock = detectionStore.all.filter(
		(d) => d.review_status === 'pending' && detectionInsideSpan(d, span)
	);
	if (inBlock.length === 0) return;

	const targets = inBlock.map((d) => ({
		id: d.id,
		previousStatus: d.review_status,
		previousArticle: d.woo_article ?? null,
		nextArticle: d.woo_article ?? null
	}));
	const cmd = new SweepBlockCommand(span.kind, targets);
	try {
		await undoStore.push(cmd);
		for (const t of targets) touchPages(t.id);
	} catch {
		// detectionStore.error already carries the banner message.
	}
}

/**
 * Apply the selected detection's in-card decision to every other
 * occurrence of the same normalized name. The "decision" here means
 * accept: in practice the reviewer clicks the link on a pending card
 * right as they're about to accept it, and the expectation is that
 * every other identical row gets the same treatment. Rows that already
 * have an explicit non-pending decision are skipped — we never
 * overwrite a reviewer's prior choice.
 */
export async function sameNameSweep(
	detectionId: string,
	touchPages: TouchPagesFn
): Promise<void> {
	const target = detectionStore.byId[detectionId];
	if (!target || !target.entity_text) return;

	const matches = findSameNameDetections(target, detectionStore.all);
	// Only rows still awaiting a decision are swept; the target itself is
	// always included so the action feels like "click once, whole name
	// handled" even if the reviewer forgot to press A first.
	const pending = matches.filter((d) => d.review_status === 'pending');
	if (pending.length === 0) return;

	const nextStatus: ReviewStatus = 'accepted';
	const targets = pending.map((d) => ({
		id: d.id,
		previousStatus: d.review_status
	}));
	const cmd = new SameNameSweepCommand(target.entity_text, nextStatus, targets);
	try {
		await undoStore.push(cmd);
		for (const t of targets) touchPages(t.id);
	} catch {
		// detectionStore.error already carries the banner message.
	}
}

/**
 * Find the narrowest structure span of `kind` enclosing a detection.
 * Used by the Shift+H / Shift+S keyboard shortcuts so they can resolve
 * the block to sweep from the current selection alone. Returns `null`
 * when the detection is missing or not inside any matching span —
 * callers treat that as "silently do nothing".
 */
export function findEnclosingSpan(
	detectionId: string,
	kind: 'email_header' | 'signature_block'
): StructureSpan | null {
	const det = detectionStore.byId[detectionId];
	if (!det) return null;
	const candidates = structureSpansStore.spans.filter(
		(s) => s.kind === kind && detectionInsideSpan(det, s)
	);
	if (candidates.length === 0) return null;
	// Narrowest enclosing span wins — matches the sidebar chip assignment.
	return candidates.sort(
		(a, b) => a.end_char - a.start_char - (b.end_char - b.start_char)
	)[0];
}
