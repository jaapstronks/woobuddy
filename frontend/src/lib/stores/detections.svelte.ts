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
	type CreateManualDetectionRequest
} from '$lib/api/client';
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

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let allDetections = $state<Detection[]>([]);
let selectedId = $state<string | null>(null);
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

const HIGH_CONFIDENCE_TIER2_THRESHOLD = 0.85;

const tier1PendingCount = $derived(
	allDetections.filter((d) => d.tier === '1' && d.review_status === 'pending').length
);
const tier2HighConfidencePendingCount = $derived(
	allDetections.filter(
		(d) =>
			d.tier === '2' &&
			d.review_status === 'pending' &&
			d.confidence >= HIGH_CONFIDENCE_TIER2_THRESHOLD
	).length
);

const selected = $derived(allDetections.find((d) => d.id === selectedId) ?? null);

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

async function analyze(documentId: string, pages: ExtractionResult['pages']) {
	loading = true;
	error = null;
	try {
		await analyzeDocument(documentId, pages);
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
	try {
		const updated = await updateDetection(id, data);
		allDetections = allDetections.map((d) =>
			d.id === id ? { ...updated, confidence_level: confidenceToLevel(updated.confidence) } : d
		);
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
	const pending = allDetections.filter(
		(d) => d.tier === '1' && d.review_status === 'pending'
	);
	for (const d of pending) {
		await accept(d.id, d.woo_article ?? undefined);
	}
}

async function acceptHighConfidenceTier2() {
	const pending = allDetections.filter(
		(d) =>
			d.tier === '2' &&
			d.review_status === 'pending' &&
			d.confidence >= HIGH_CONFIDENCE_TIER2_THRESHOLD
	);
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
	remove,
	acceptAllPendingTier1,
	acceptHighConfidenceTier2,
	setFilter,
	clearFilters,
	clearError
};
