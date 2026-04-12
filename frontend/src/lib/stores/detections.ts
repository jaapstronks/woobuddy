/**
 * Detections store — Svelte 5 runes-based state management for the review page.
 *
 * Manages all detections for the currently viewed document, with filtering,
 * selection, and review actions.
 */

import {
	getDetections,
	updateDetection,
	propagateName,
	triggerDetection
} from '$lib/api/client';
import type {
	Detection,
	DetectionTier,
	ReviewStatus,
	UpdateDetectionRequest,
	EntityType,
	WooArticleCode
} from '$lib/types';
import { confidenceToLevel } from '$lib/utils/tiers';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let allDetections = $state<Detection[]>([]);
let selectedId = $state<string | null>(null);
let loading = $state(false);
let error = $state<string | null>(null);

// Filters
let filterTier = $state<DetectionTier | null>(null);
let filterStatus = $state<ReviewStatus | null>(null);
let filterEntityType = $state<EntityType | null>(null);
let filterPage = $state<number | null>(null);

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const filtered = $derived.by(() => {
	let result = allDetections;
	if (filterTier !== null) result = result.filter((d) => d.tier === filterTier);
	if (filterStatus !== null) result = result.filter((d) => d.review_status === filterStatus);
	if (filterEntityType !== null) result = result.filter((d) => d.entity_type === filterEntityType);
	if (filterPage !== null)
		result = result.filter((d) => d.bounding_boxes?.some((b) => b.page === filterPage));
	return result;
});

const selected = $derived(allDetections.find((d) => d.id === selectedId) ?? null);

const counts = $derived.by(() => {
	const byTier = { 1: 0, 2: 0, 3: 0 } as Record<DetectionTier, number>;
	const reviewedByTier = { 1: 0, 2: 0, 3: 0 } as Record<DetectionTier, number>;
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
		allDetections = raw.map((d) => ({
			...d,
			confidence_level: confidenceToLevel(d.confidence)
		}));
	} catch (e) {
		error = e instanceof Error ? e.message : 'Laden mislukt';
	} finally {
		loading = false;
	}
}

async function detect(documentId: string) {
	loading = true;
	error = null;
	try {
		await triggerDetection(documentId);
		await load(documentId);
	} catch (e) {
		error = e instanceof Error ? e.message : 'Detectie mislukt';
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

async function accept(id: string, wooArticle?: WooArticleCode) {
	await review(id, { review_status: 'accepted', woo_article: wooArticle });
}

async function reject(id: string) {
	await review(id, { review_status: 'rejected' });
}

async function defer(id: string) {
	await review(id, { review_status: 'deferred' });
}

async function propagate(id: string) {
	try {
		await propagateName(id);
		// Reload to get propagated changes
		const det = allDetections.find((d) => d.id === id);
		if (det) await load(det.document_id);
	} catch (e) {
		error = e instanceof Error ? e.message : 'Propagatie mislukt';
	}
}

function setFilter(key: 'tier' | 'status' | 'entityType' | 'page', value: unknown) {
	if (key === 'tier') filterTier = value as DetectionTier | null;
	if (key === 'status') filterStatus = value as ReviewStatus | null;
	if (key === 'entityType') filterEntityType = value as EntityType | null;
	if (key === 'page') filterPage = value as number | null;
}

function clearFilters() {
	filterTier = null;
	filterStatus = null;
	filterEntityType = null;
	filterPage = null;
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const detectionStore = {
	get all() {
		return allDetections;
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
	get filters() {
		return {
			tier: filterTier,
			status: filterStatus,
			entityType: filterEntityType,
			page: filterPage
		};
	},
	load,
	detect,
	select,
	selectNext,
	selectPrevious,
	accept,
	reject,
	defer,
	review,
	propagate,
	setFilter,
	clearFilters
};
