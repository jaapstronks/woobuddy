/**
 * Detections store — Svelte 5 runes-based state management for the review page.
 *
 * Manages all detections for the currently viewed document, with filtering,
 * selection, and review actions.
 */

import {
	getDetections,
	updateDetection,
	analyzeDocument,
	createManualDetection,
	deleteDetection,
	splitDetection,
	mergeDetections,
	type CreateManualDetectionRequest
} from '$lib/api/client';
import { HIGH_CONFIDENCE_THRESHOLD } from '$lib/config/thresholds';
import { structureSpansStore } from '$lib/stores/structure-spans.svelte';
import { resolveEntityTexts } from '$lib/services/bbox-text-resolver';
import type {
	BoundingBox,
	Detection,
	DetectionTier,
	ReviewStatus,
	UpdateDetectionRequest,
	EntityType,
	WooArticleCode,
	ExtractionResult
} from '$lib/types';
import { confidenceToLevel } from '$lib/utils/tiers';
import { track } from '$lib/analytics/plausible';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const isPendingTier1 = (d: Detection): boolean =>
	d.tier === '1' && d.review_status === 'pending';

const isHighConfidencePendingTier2 = (d: Detection): boolean =>
	d.tier === '2' &&
	d.review_status === 'pending' &&
	d.confidence >= HIGH_CONFIDENCE_THRESHOLD;

/**
 * Merge a server response back into the local list, preserving the
 * client-only `entity_text`. The server does not store document content,
 * so its response omits the text; without this splice the sidebar would
 * blank out on every status change or bbox nudge.
 */
function mergeServerUpdate(
	id: string,
	updated: Detection,
	preferUpdatedText: boolean
): void {
	const existingText = byId[id]?.entity_text;
	allDetections = allDetections.map((d) =>
		d.id === id
			? {
					...updated,
					entity_text: preferUpdatedText
						? updated.entity_text ?? existingText ?? d.entity_text
						: existingText ?? d.entity_text,
					confidence_level: confidenceToLevel(updated.confidence)
				}
			: d
	);
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let allDetections = $state<Detection[]>([]);
let selectedId = $state<string | null>(null);
/**
 * #18 — merge staging set. Tracks ids the reviewer Ctrl+clicked in the
 * sidebar to line up for a merge. Deliberately kept separate from
 * `selectedId` so the single-select navigation (Up/Down, card focus) and
 * the multi-select merge flow don't fight over the same state. The set is
 * cleared after a successful merge, on explicit `clearMultiSelect()`, or
 * when a new document loads.
 */
let multiSelectedIds = $state<string[]>([]);
let loading = $state(false);
let error = $state<string | null>(null);
let currentExtraction = $state<ExtractionResult | null>(null);

// Filters
let filterTier = $state<DetectionTier | null>(null);
let filterStatus = $state<ReviewStatus | null>(null);
let filterEntityType = $state<EntityType | null>(null);

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const filtered = $derived.by(() => {
	let result = allDetections;
	if (filterTier !== null) result = result.filter((d) => d.tier === filterTier);
	if (filterStatus !== null) result = result.filter((d) => d.review_status === filterStatus);
	if (filterEntityType !== null) result = result.filter((d) => d.entity_type === filterEntityType);
	return result;
});

const tier1PendingCount = $derived(allDetections.filter(isPendingTier1).length);
const tier2HighConfidencePendingCount = $derived(
	allDetections.filter(isHighConfidencePendingTier2).length
);

/**
 * O(1) id → detection lookup. Handler bodies in the review page used to
 * re-run `allDetections.find(d => d.id === id)` for every keyboard
 * shortcut and undo-replay; that's N checks per action times the number
 * of handlers. The derived map rebuilds whenever the list changes and is
 * read through `detectionStore.byId[id]` from the rest of the UI.
 */
const byId = $derived.by(() => {
	const map: Record<string, Detection> = {};
	for (const d of allDetections) map[d.id] = d;
	return map;
});

const selected = $derived(selectedId ? byId[selectedId] ?? null : null);

const counts = $derived.by(() => {
	const byTier = { '1': 0, '2': 0, '3': 0 } as Record<DetectionTier, number>;
	const reviewedByTier = { '1': 0, '2': 0, '3': 0 } as Record<DetectionTier, number>;
	const byStatus: Partial<Record<ReviewStatus, number>> = {};

	for (const d of allDetections) {
		byTier[d.tier] = (byTier[d.tier] ?? 0) + 1;
		byStatus[d.review_status] = (byStatus[d.review_status] ?? 0) + 1;
		if (d.review_status !== 'pending' && d.review_status !== 'deferred') {
			reviewedByTier[d.tier] = (reviewedByTier[d.tier] ?? 0) + 1;
		}
	}

	return { byTier, reviewedByTier, byStatus, total: allDetections.length };
});

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function load(documentId: string) {
	loading = true;
	error = null;
	// A fresh document load invalidates any in-progress merge staging: the
	// ids were scoped to the previous document and must not silently carry
	// over to this one.
	multiSelectedIds = [];
	try {
		const raw = await getDetections(documentId);
		let detections = raw.map((d) => ({
			...d,
			confidence_level: confidenceToLevel(d.confidence)
		}));
		// Resolve entity_text from local extraction if available
		if (currentExtraction) {
			detections = resolveEntityTexts(detections, currentExtraction);
		}
		allDetections = detections;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Laden mislukt';
	} finally {
		loading = false;
	}
}

function setExtraction(extraction: ExtractionResult) {
	currentExtraction = extraction;
	// Re-resolve entity texts for any already-loaded detections
	if (allDetections.length > 0 && currentExtraction) {
		allDetections = resolveEntityTexts(allDetections, currentExtraction);
	}
}

async function analyze(
	documentId: string,
	pages: ExtractionResult['pages'],
	referenceNames: string[] = [],
	customTerms: { term: string; match_mode?: 'exact'; woo_article?: string }[] = []
) {
	loading = true;
	error = null;
	try {
		// #17 — forward the per-document reference list so the server can
		// flip matching Tier 2 persoon detections to rejected before they
		// ever reach the review sidebar.
		// #21 — same for the custom wordlist: the server scans the full
		// text for every occurrence and emits `custom` detections that
		// the sidebar renders alongside the regular pipeline output.
		const analyzeResult = await analyzeDocument(
			documentId,
			pages,
			referenceNames,
			customTerms
		);
		// #20 — cache the structure spans keyed to this document so the
		// sweep-block affordances can render without re-running analyze
		// after every reload. Cleared when a different document loads.
		structureSpansStore.set(documentId, analyzeResult.structure_spans ?? []);
		await load(documentId);
	} catch (e) {
		error = e instanceof Error ? e.message : 'Analyse mislukt';
	} finally {
		loading = false;
	}
}

function select(id: string | null) {
	selectedId = id;
}

function selectNext() {
	const idx = filtered.findIndex((d) => d.id === selectedId);
	if (idx < filtered.length - 1) {
		selectedId = filtered[idx + 1].id;
	}
}

function selectPrevious() {
	const idx = filtered.findIndex((d) => d.id === selectedId);
	if (idx > 0) {
		selectedId = filtered[idx - 1].id;
	}
}

async function review(id: string, data: UpdateDetectionRequest) {
	const before = byId[id];
	try {
		const updated = await updateDetection(id, data);
		mergeServerUpdate(id, updated, /* preferUpdatedText */ true);

		// Analytics (#41). Only fire for terminal review states — "edited"
		// and "pending" are intermediate and would inflate event volume
		// without a clear product question to answer. Props are coarse
		// (tier + entity class) — never entity_text.
		if (before && (data.review_status === 'accepted' || data.review_status === 'rejected')) {
			track(
				data.review_status === 'accepted' ? 'redaction_confirmed' : 'redaction_rejected',
				{ tier: `tier${before.tier}`, entity_type: before.entity_type }
			);
		}
	} catch (e) {
		error = e instanceof Error ? e.message : 'Bijwerken mislukt';
	}
}

/**
 * Create a reviewer-authored redaction from a text selection.
 *
 * Client-first: the server receives only bbox + metadata. The selected
 * text is captured here and kept in the in-memory detection so the
 * sidebar list can show it — but it is NEVER sent back to the server.
 */
async function createManual(params: {
	documentId: string;
	bboxes: BoundingBox[];
	selectedText: string;
	entityType: EntityType;
	tier: DetectionTier;
	wooArticle: WooArticleCode;
	motivation: string;
	/** Defaults to "manual"; #09 passes "search_redact" for bulk-applied hits. */
	source?: 'manual' | 'search_redact';
}): Promise<Detection | null> {
	try {
		const payload: CreateManualDetectionRequest = {
			document_id: params.documentId,
			entity_type: params.entityType,
			tier: params.tier,
			woo_article: params.wooArticle,
			bounding_boxes: params.bboxes,
			motivation_text: params.motivation,
			source: params.source ?? 'manual'
		};
		const created = await createManualDetection(payload);
		// Splice the client-known entity_text back onto the server response
		// so the detection list can show it without another round-trip.
		const withText: Detection = {
			...created,
			entity_text: params.selectedText,
			confidence_level: confidenceToLevel(created.confidence)
		};
		allDetections = [...allDetections, withText];
		selectedId = withText.id;
		return withText;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Handmatige lakking mislukt';
		return null;
	}
}

/**
 * Delete a manual detection (server-side + local state).
 *
 * Used by the undo store to reverse a `CreateManualCommand`. The server
 * rejects deletion for non-manual detections, so callers must only invoke
 * this for rows they know to be reviewer-authored.
 */
async function remove(id: string) {
	try {
		await deleteDetection(id);
		allDetections = allDetections.filter((d) => d.id !== id);
		if (selectedId === id) selectedId = null;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Verwijderen mislukt';
		throw e;
	}
}

/**
 * Replace the bounding boxes of an existing detection (#11 boundary
 * adjustment). The server snapshots the analyzer's original boxes into
 * `original_bounding_boxes` on the very first adjust and flips
 * `review_status` to `"edited"` unless the caller passes `keepStatus`.
 * Callers pass a `keepStatus` payload via the undo stack when reverting
 * (e.g. undo restoring the previous bboxes AND the previous status at the
 * same time).
 */
async function adjustBoundary(
	id: string,
	bboxes: BoundingBox[],
	keepStatus?: { review_status: ReviewStatus }
): Promise<Detection | null> {
	try {
		const payload: UpdateDetectionRequest = { bounding_boxes: bboxes };
		if (keepStatus) payload.review_status = keepStatus.review_status;
		const updated = await updateDetection(id, payload);
		mergeServerUpdate(id, updated, /* preferUpdatedText */ false);
		return updated;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Grenscorrectie mislukt';
		return null;
	}
}

/**
 * Split a detection into two (#18).
 *
 * The caller has already computed the two bbox sets from the click
 * position in the PDF viewer. The server creates two new manual-source
 * detections inheriting the original's metadata, deletes the original,
 * and returns both halves. The local cache is updated accordingly and
 * the first half becomes the new selection.
 */
async function split(
	id: string,
	bboxesA: BoundingBox[],
	bboxesB: BoundingBox[]
): Promise<Detection[] | null> {
	try {
		const halves = await splitDetection(id, bboxesA, bboxesB);
		const withLevels = halves.map((h) => ({
			...h,
			confidence_level: confidenceToLevel(h.confidence)
		}));
		allDetections = [
			...allDetections.filter((d) => d.id !== id),
			...withLevels
		];
		selectedId = withLevels[0]?.id ?? null;
		// A split consumes the single selection, not the merge-staging set —
		// leave `multiSelectedIds` alone.
		return withLevels;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Splitsen mislukt';
		return null;
	}
}

/**
 * Merge the ids currently in `multiSelectedIds` (#18).
 *
 * Bboxes are concatenated server-side in the order the ids are passed;
 * metadata (tier, entity type, woo article, motivation) is inherited from
 * the *first* id, which matches the reviewer's "click this one first, then
 * Ctrl+click the others" mental model. The inputs are deleted; the new
 * merged row replaces them in local state and becomes the selection.
 */
async function merge(): Promise<Detection | null> {
	if (multiSelectedIds.length < 2) {
		error = 'Selecteer ten minste twee detecties om samen te voegen.';
		return null;
	}
	const ids = [...multiSelectedIds];
	try {
		const merged = await mergeDetections(ids);
		const withLevel: Detection = {
			...merged,
			confidence_level: confidenceToLevel(merged.confidence)
		};
		const idSet = new Set(ids);
		allDetections = [
			...allDetections.filter((d) => !idSet.has(d.id)),
			withLevel
		];
		selectedId = withLevel.id;
		multiSelectedIds = [];
		return withLevel;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Samenvoegen mislukt';
		return null;
	}
}

function toggleMultiSelect(id: string) {
	if (multiSelectedIds.includes(id)) {
		multiSelectedIds = multiSelectedIds.filter((x) => x !== id);
	} else {
		multiSelectedIds = [...multiSelectedIds, id];
	}
}

function clearMultiSelect() {
	multiSelectedIds = [];
}

async function accept(id: string, wooArticle?: WooArticleCode) {
	await review(id, { review_status: 'accepted', woo_article: wooArticle });
}

async function reject(id: string) {
	await review(id, { review_status: 'rejected' });
}

async function defer(id: string) {
	await review(id, { review_status: 'deferred' });
}

function setFilter(key: 'tier' | 'status' | 'entityType', value: unknown) {
	if (key === 'tier') filterTier = value as DetectionTier | null;
	if (key === 'status') filterStatus = value as ReviewStatus | null;
	if (key === 'entityType') filterEntityType = value as EntityType | null;
}

function clearFilters() {
	filterTier = null;
	filterStatus = null;
	filterEntityType = null;
}

function clearError() {
	error = null;
}

async function acceptAllPendingTier1() {
	const pending = allDetections.filter(isPendingTier1);
	for (const d of pending) {
		await accept(d.id, d.woo_article ?? undefined);
	}
}

async function acceptHighConfidenceTier2() {
	const pending = allDetections.filter(isHighConfidencePendingTier2);
	for (const d of pending) {
		await accept(d.id, d.woo_article ?? undefined);
	}
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const detectionStore = {
	get all() {
		return allDetections;
	},
	get byId() {
		return byId;
	},
	get extraction() {
		return currentExtraction;
	},
	get filtered() {
		return filtered;
	},
	get selected() {
		return selected;
	},
	get selectedId() {
		return selectedId;
	},
	get multiSelectedIds() {
		return multiSelectedIds;
	},
	get loading() {
		return loading;
	},
	get error() {
		return error;
	},
	get counts() {
		return counts;
	},
	get tier1PendingCount() {
		return tier1PendingCount;
	},
	get tier2HighConfidencePendingCount() {
		return tier2HighConfidencePendingCount;
	},
	get filters() {
		return {
			tier: filterTier,
			status: filterStatus,
			entityType: filterEntityType
		};
	},
	load,
	analyze,
	setExtraction,
	select,
	selectNext,
	selectPrevious,
	accept,
	reject,
	defer,
	review,
	createManual,
	adjustBoundary,
	remove,
	split,
	merge,
	toggleMultiSelect,
	clearMultiSelect,
	acceptAllPendingTier1,
	acceptHighConfidenceTier2,
	setFilter,
	clearFilters,
	clearError
};
