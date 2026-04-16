/**
 * Split & merge (#18) — extracted from routes/review/[docId]/+page.svelte.
 *
 * Owns the single-source state for the detection-splitting flow:
 * `pendingId` is the id of the detection waiting for a split-point
 * click on the PDF, or null. Merging has no intermediate state — it
 * operates directly on the detection store's multi-select — so it
 * lives here as a thin action alongside split for symmetry.
 */

import { detectionStore } from './detections.svelte';
import { computeSplitBboxes } from '$lib/services/boundary-edit-geometry';

let pendingId = $state<string | null>(null);

function startSplit() {
	const selected = detectionStore.selected;
	if (!selected || !selected.bounding_boxes?.length) return;
	pendingId = selected.id;
}

function cancelSplit() {
	pendingId = null;
}

/**
 * The reviewer clicked inside the split-target detection's overlay.
 * `computeSplitBboxes` derives the two new bbox sets from the target
 * bbox and the clicked x-coordinate; we forward them to the store.
 */
async function commitSplit(args: {
	detectionId: string;
	bboxIndex: number;
	pdfX: number;
	pdfY: number;
}) {
	const det = detectionStore.byId[args.detectionId];
	if (!det || !det.bounding_boxes?.length) {
		pendingId = null;
		return;
	}
	const split = computeSplitBboxes(det.bounding_boxes, args.bboxIndex, args.pdfX);
	if (!split) {
		pendingId = null;
		return;
	}

	// Clear pending state before the async call — if the request fails
	// the reviewer should be able to re-trigger split without being stuck
	// in a stale pending mode.
	pendingId = null;
	await detectionStore.split(args.detectionId, split.bboxesA, split.bboxesB);
}

async function confirmMerge() {
	await detectionStore.merge();
}

export const splitMergeStore = {
	get pendingId() {
		return pendingId;
	},
	startSplit,
	cancelSplit,
	commitSplit,
	confirmMerge
};
