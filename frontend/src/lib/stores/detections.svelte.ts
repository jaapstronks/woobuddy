/**
 * Detections store — Svelte 5 runes-based state management for the review page.
 *
 * Manages all detections for the currently viewed document, with filtering,
 * selection, and review actions. Local-only since #50: every edit is a pure
 * in-memory mutation with a client-generated UUID, and the result is mirrored
 * to IndexedDB (`session-state-store`) so a Cmd+R on the review page restores
 * the reviewer's accept/reject/manual-redact work without ever hitting the
 * server.
 */

import { analyzeDocument } from '$lib/api/client';
import { HIGH_CONFIDENCE_THRESHOLD } from '$lib/config/thresholds';
import { structureSpansStore } from '$lib/stores/structure-spans.svelte';
import {
	resolveEntityTexts,
	type UnplacedDetection
} from '$lib/services/bbox-text-resolver';
import {
	readSessionState,
	writeSessionState,
	writeSessionStateSlice
} from '$lib/services/session-state-store';
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

function withConfidenceLevel(d: Detection): Detection {
	return { ...d, confidence_level: confidenceToLevel(d.confidence) };
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocId = $state<string | null>(null);
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
/**
 * #78 — detections the server found but the client could not place on a
 * page. `resolveEntityTexts` drops them (a card with no box is not
 * actionable), and this is the record of what was dropped so the review
 * screen can name the terms and point at search-and-redact. Reset on
 * every full resolve; dismissible by the reviewer.
 */
let unplaced = $state<UnplacedDetection[]>([]);
let unplacedDismissed = $state(false);
/**
 * #85 — the rows behind `unplaced`, kept verbatim so `persistDetections`
 * can write them back alongside the placed ones. `setFromAnalyze` already
 * caches the server's full answer; without this the first accept/reject
 * narrowed the cache to the placed rows and the banner disappeared on the
 * next refresh — the same silent loss #78 set out to end. Never rendered:
 * a row with no usable box is not a card.
 */
let unplacedRows = $state<Detection[]>([]);

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
// Persistence
// ---------------------------------------------------------------------------

/**
 * Mirror the current detection list into the IndexedDB session-state
 * cache so a Cmd+R restores it. Errors degrade silently — the in-memory
 * store stays authoritative; the only consequence is that a refresh
 * loses the slice.
 *
 * `$state.snapshot()` is mandatory before handing reactive state to IDB:
 * Svelte 5 `$state` values are Proxies, and the structured-clone
 * algorithm rejects Proxies with `DataCloneError`. Snapshotting walks
 * the tree and produces a plain-object copy that IDB can serialize.
 */
async function persistDetections(): Promise<void> {
	if (!currentDocId) return;
	// Strip the client-only `entity_text` and `confidence_level` fields
	// before persisting — they're recomputed on hydration via the
	// extraction layer. Keeping them in IDB would make refresh-restored
	// state diverge subtly from a fresh analyze when the extraction
	// layer changes its resolver heuristics.
	//
	// #85 — the unplaceable rows ride along. They are not part of
	// `allDetections` (the resolver dropped them), but they *are* part of
	// what the analyzer found, and `hydrate` rebuilds the "kon niet
	// geplaatst worden" banner by re-running the resolver over whatever
	// this writes. Leaving them out let one accept erase the record.
	const persistable = [...$state.snapshot(allDetections), ...$state.snapshot(unplacedRows)];
	const sanitized: Detection[] = persistable.map((d) => {
		const { entity_text: _et, confidence_level: _cl, ...rest } = d;
		void _et;
		void _cl;
		return rest as Detection;
	});
	await writeSessionStateSlice(currentDocId, { detections: sanitized });
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

/**
 * Run the bbox → text resolution and store both halves: the placeable
 * detections and the record of what was dropped (#78). Without an
 * extraction there is nothing to resolve against, so the rows are kept
 * as-is and no claim is made about what is unplaceable.
 */
function applyResolution(detections: Detection[], mode: 'replace' | 'merge' = 'replace'): void {
	if (!currentExtraction) {
		allDetections = detections;
		if (mode === 'replace') {
			unplaced = [];
			unplacedRows = [];
		}
		return;
	}
	const result = resolveEntityTexts(detections, currentExtraction);
	allDetections = result.detections;
	if (mode === 'replace') {
		unplaced = result.unplaced;
		unplacedRows = result.dropped;
		unplacedDismissed = false;
		return;
	}
	// Merge: a re-resolve runs over rows the previous pass already
	// filtered, so it can only ever *add* to the record — replacing it
	// would silently erase what the first pass found.
	const known = new Set(unplaced.map((u) => u.id));
	const addedIdx: number[] = [];
	result.unplaced.forEach((u, i) => {
		if (u.id === null || !known.has(u.id)) addedIdx.push(i);
	});
	if (addedIdx.length > 0) {
		unplaced = [...unplaced, ...addedIdx.map((i) => result.unplaced[i])];
		unplacedRows = [...unplacedRows, ...addedIdx.map((i) => result.dropped[i])];
	}
}

/** Hide the "kon niet geplaatst worden" notice for this session. */
function dismissUnplaced(): void {
	unplacedDismissed = true;
}

/**
 * Replace the in-memory state with detections produced for `docId` and
 * write through the IDB session cache. Called by the upload flow with
 * the full {@link analyzeDocument} response.
 *
 * Discards any prior state — switching documents must not carry over
 * the previous review's selection, filters, or undo staging.
 */
async function setFromAnalyze(
	docId: string,
	detections: Detection[],
	structureSpans: import('$lib/types').StructureSpan[]
): Promise<void> {
	currentDocId = docId;
	multiSelectedIds = [];
	selectedId = null;
	const withLevels = detections.map(withConfidenceLevel);
	applyResolution(withLevels);
	structureSpansStore.set(docId, structureSpans);
	// `detections` and `structureSpans` come straight from a fetch
	// response so they are plain objects — no $state.snapshot needed
	// here. Empty arrays / objects are equally clone-safe.
	await writeSessionState({
		id: docId,
		detections, // unresolved — entity_text rebuilt on hydrate
		structureSpans,
		referenceNames: [],
		customTerms: [],
		pageReviews: {},
		storedAt: Date.now()
	});
}

/**
 * Read detections + structure spans for `docId` from the IDB session
 * cache. Used by the review page on mount/refresh to restore the
 * reviewer's prior session without re-running analyze. Returns `false`
 * if no cached state exists; the caller can then trigger a fresh
 * analyze.
 */
async function hydrate(docId: string): Promise<boolean> {
	currentDocId = docId;
	multiSelectedIds = [];
	selectedId = null;
	const state = await readSessionState(docId);
	if (!state) {
		allDetections = [];
		unplaced = [];
		unplacedRows = [];
		return false;
	}
	const withLevels = state.detections.map(withConfidenceLevel);
	applyResolution(withLevels);
	structureSpansStore.set(docId, state.structureSpans);
	return true;
}

/**
 * Run a fresh analyze for the current document and store the result.
 * Used as a fallback when {@link hydrate} returns `false` (cache miss
 * after IDB clear) and as the rerun path after a reference-list or
 * custom-term change.
 */
async function analyze(
	docId: string,
	pages: ExtractionResult['pages'],
	referenceNames: string[] = [],
	customTerms: { term: string; match_mode?: 'exact'; woo_article?: string }[] = []
): Promise<void> {
	loading = true;
	error = null;
	try {
		const result = await analyzeDocument(pages, referenceNames, customTerms);
		await setFromAnalyze(docId, result.detections, result.structure_spans);
	} catch (e) {
		error = e instanceof Error ? e.message : 'Analyse mislukt';
	} finally {
		loading = false;
	}
}

function setExtraction(extraction: ExtractionResult) {
	currentExtraction = extraction;
	// Re-resolve entity texts for any already-loaded detections. On a
	// refresh this runs *before* `hydrate()` (the review page loads the
	// PDF first) and finds an empty list, so the unplaced set is filled
	// by `hydrate()` in replace mode. The merge path is for the upload
	// flow, where the store is already populated when the review page
	// re-extracts: re-resolving there runs over rows the first pass
	// already filtered, so it can only add to the record.
	if (allDetections.length > 0) {
		applyResolution(allDetections, 'merge');
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

/**
 * Apply a review action to a single detection. Pure local mutation —
 * the corresponding server PATCH was removed in #50. The IDB session
 * cache is updated so the change survives a refresh.
 */
async function review(id: string, data: UpdateDetectionRequest) {
	const before = byId[id];
	if (!before) return;

	const next: Detection = { ...before };
	if (data.review_status !== undefined) {
		next.review_status = data.review_status;
		next.reviewed_at = new Date().toISOString();
	}
	if (data.woo_article !== undefined) {
		next.woo_article = data.woo_article;
	}
	if (data.bounding_boxes !== undefined) {
		// Boundary adjust (#11): snapshot the analyzer's original boxes the
		// first time a reviewer touches this detection, so undo can later
		// surface "what the analyzer originally produced" alongside "what
		// I last set."
		if (!next.original_bounding_boxes) {
			next.original_bounding_boxes = before.bounding_boxes;
		}
		next.bounding_boxes = data.bounding_boxes;
		// Match the server-side rule: a bbox-only edit flips status to
		// "edited" unless the same call passed an explicit status.
		if (data.review_status === undefined) {
			next.review_status = 'edited';
			next.reviewed_at = new Date().toISOString();
		}
	}
	if (data.subject_role !== undefined) {
		next.subject_role = data.subject_role;
	} else if (data.clear_subject_role) {
		next.subject_role = null;
	}
	if (data.motivation_text !== undefined) {
		// The reviewer's justification for a Tier 3 judgment call. It used
		// to be sent by `handleSaveMotivation` and dropped on the floor
		// here, so "Opslaan" only flipped the status and the typed text was
		// gone on the next render (#66/3). Stays client-side: it is part of
		// the onderbouwing, never a log line and never a request body.
		next.motivation_text = data.motivation_text;
	}

	allDetections = allDetections.map((d) => (d.id === id ? next : d));
	await persistDetections();

	// Analytics (#41). Only fire for terminal review states — "edited"
	// and "pending" are intermediate and would inflate event volume
	// without a clear product question to answer. Props are coarse
	// (tier + entity class) — never entity_text.
	if (data.review_status === 'accepted' || data.review_status === 'rejected') {
		track(
			data.review_status === 'accepted' ? 'redaction_confirmed' : 'redaction_rejected',
			{ tier: `tier${before.tier}`, entity_type: before.entity_type }
		);
	}
}

/**
 * Create a reviewer-authored redaction from a text selection.
 *
 * Generates a client-side UUID and a consistent timestamp; the result
 * shape matches what the analyze pipeline emits for `manual` rows so
 * the rest of the review UI can treat it identically.
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
	const id = crypto.randomUUID();
	const detection: Detection = {
		id,
		document_id: params.documentId,
		entity_text: params.selectedText,
		entity_type: params.entityType,
		tier: params.tier,
		confidence: 1.0, // Reviewer-authored: full confidence by definition.
		confidence_level: confidenceToLevel(1.0),
		woo_article: params.wooArticle,
		review_status: 'accepted',
		bounding_boxes: params.bboxes,
		original_bounding_boxes: null,
		reasoning: params.motivation || null,
		source: params.source ?? 'manual',
		propagated_from: null,
		reviewer_id: null,
		reviewed_at: new Date().toISOString(),
		is_environmental: false,
		subject_role: null,
		split_from: null,
		merged_from: null,
		start_char: null,
		end_char: null
	};
	allDetections = [...allDetections, detection];
	selectedId = id;
	await persistDetections();
	return detection;
}

/**
 * Delete a manual detection from local state. Mirrors the server-side
 * rule: only reviewer-authored rows (`manual`, `search_redact`) are
 * deletable — the undo stack only invokes this for those. Auto rows
 * are immutable; undoing their acceptance flips review_status back.
 */
async function remove(id: string) {
	const target = byId[id];
	if (!target) return;
	if (target.source !== 'manual' && target.source !== 'search_redact') {
		error = 'Alleen handmatige detecties kunnen worden verwijderd.';
		throw new Error(error);
	}
	allDetections = allDetections.filter((d) => d.id !== id);
	if (selectedId === id) selectedId = null;
	await persistDetections();
}

/**
 * Replace the bounding boxes of an existing detection (#11 boundary
 * adjustment). On the very first adjust we snapshot the analyzer's
 * baseline into `original_bounding_boxes` for audit. The status flips
 * to "edited" unless the caller passes `keepStatus` — that's the undo
 * stack restoring the prior bboxes AND prior status in one call.
 */
async function adjustBoundary(
	id: string,
	bboxes: BoundingBox[],
	keepStatus?: { review_status: ReviewStatus }
): Promise<Detection | null> {
	const target = byId[id];
	if (!target) return null;
	const next: Detection = {
		...target,
		bounding_boxes: bboxes,
		original_bounding_boxes:
			target.original_bounding_boxes ?? target.bounding_boxes,
		review_status: keepStatus?.review_status ?? 'edited',
		reviewed_at: new Date().toISOString()
	};
	allDetections = allDetections.map((d) => (d.id === id ? next : d));
	await persistDetections();
	return next;
}

/**
 * Split a detection into two halves (#18). Both halves inherit the
 * original's metadata and become reviewer-authored (`source: 'manual'`)
 * so the regular delete path can remove them. The original row is
 * dropped.
 */
async function split(
	id: string,
	bboxesA: BoundingBox[],
	bboxesB: BoundingBox[]
): Promise<Detection[] | null> {
	const original = byId[id];
	if (!original) return null;
	const stamp = new Date().toISOString();
	const left: Detection = {
		...original,
		id: crypto.randomUUID(),
		bounding_boxes: bboxesA,
		original_bounding_boxes: null,
		confidence: 1.0,
		confidence_level: confidenceToLevel(1.0),
		review_status: 'accepted',
		source: 'manual',
		split_from: id,
		merged_from: null,
		reviewed_at: stamp
	};
	const right: Detection = {
		...original,
		id: crypto.randomUUID(),
		bounding_boxes: bboxesB,
		original_bounding_boxes: null,
		confidence: 1.0,
		confidence_level: confidenceToLevel(1.0),
		review_status: 'accepted',
		source: 'manual',
		split_from: id,
		merged_from: null,
		reviewed_at: stamp
	};
	allDetections = [...allDetections.filter((d) => d.id !== id), left, right];
	selectedId = left.id;
	await persistDetections();
	return [left, right];
}

/**
 * Merge the ids currently in `multiSelectedIds` (#18). Bboxes are
 * concatenated in click order; metadata inherits from the first id, which
 * matches the reviewer's "click this one first, then Ctrl+click the
 * others" mental model. The originals are dropped.
 */
async function merge(explicitIds?: string[]): Promise<Detection | null> {
	// `explicitIds` lets the undo stack redo a merge after the multi-select
	// has been cleared; without it, redo silently merged nothing.
	const source = explicitIds ?? multiSelectedIds;
	if (source.length < 2) {
		error = 'Selecteer ten minste twee detecties om samen te voegen.';
		return null;
	}
	const ids = [...source];
	const ordered = ids.map((id) => byId[id]).filter((d): d is Detection => d !== undefined);
	if (ordered.length !== ids.length) {
		error = 'Detectie niet gevonden';
		return null;
	}
	const documentIds = new Set(ordered.map((d) => d.document_id));
	if (documentIds.size > 1) {
		error = 'Samenvoegen over documenten heen wordt niet ondersteund.';
		return null;
	}
	const primary = ordered[0];
	const combinedBboxes = ordered.flatMap((d) => d.bounding_boxes ?? []);
	if (combinedBboxes.length === 0) {
		error = 'Samengevoegde detecties moeten ten minste één bounding box hebben.';
		return null;
	}
	const merged: Detection = {
		...primary,
		id: crypto.randomUUID(),
		bounding_boxes: combinedBboxes,
		original_bounding_boxes: null,
		confidence: 1.0,
		confidence_level: confidenceToLevel(1.0),
		review_status: 'accepted',
		source: 'manual',
		split_from: null,
		merged_from: ids,
		reviewed_at: new Date().toISOString()
	};
	const idSet = new Set(ids);
	allDetections = [...allDetections.filter((d) => !idSet.has(d.id)), merged];
	selectedId = merged.id;
	multiSelectedIds = [];
	await persistDetections();
	return merged;
}

/**
 * Swap one set of detection rows for another in a single mutation.
 *
 * The undo counterpart of `split` and `merge` (#18): both actions delete
 * their inputs and insert freshly generated rows, so rolling them back
 * means putting the captured originals back and dropping the products.
 * Doing it as one mutation (rather than remove-then-insert) keeps
 * `allDetections` from flickering through a state where the detection
 * exists nowhere, which the overlay effect would happily paint.
 */
async function replaceRows(args: {
	removeIds: string[];
	insert: Detection[];
	select?: string | null;
}): Promise<void> {
	const gone = new Set(args.removeIds);
	allDetections = [...allDetections.filter((d) => !gone.has(d.id)), ...args.insert];
	if (args.select !== undefined) {
		selectedId = args.select;
	} else if (selectedId && gone.has(selectedId)) {
		selectedId = null;
	}
	multiSelectedIds = multiSelectedIds.filter((id) => !gone.has(id));
	await persistDetections();
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
	get unplaced() {
		return unplacedDismissed ? [] : unplaced;
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
	get docId() {
		return currentDocId;
	},
	get filters() {
		return {
			tier: filterTier,
			status: filterStatus,
			entityType: filterEntityType
		};
	},
	setFromAnalyze,
	hydrate,
	analyze,
	setExtraction,
	dismissUnplaced,
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
	replaceRows,
	toggleMultiSelect,
	clearMultiSelect,
	acceptAllPendingTier1,
	acceptHighConfidenceTier2,
	setFilter,
	clearFilters,
	clearError
};
