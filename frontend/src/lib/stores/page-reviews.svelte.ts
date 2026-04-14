/**
 * Page reviews store (#10 — page completeness).
 *
 * Tracks per-page status (unreviewed/in_progress/complete/flagged) for the
 * current document. The server keeps a row per touched page; missing rows
 * are treated as `unreviewed`, so this store stays sparse for long
 * documents where only a handful of pages get marked by hand.
 *
 * Status persists immediately on change — there's no explicit save. We
 * optimistically update the local map, then fire-and-forget the PUT;
 * failures roll the entry back and surface an error.
 */

import {
	getPageReviews,
	upsertPageReview,
	type PageReviewStatus
} from '$lib/api/client';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocumentId = $state<string | null>(null);
// Sparse page-number → status map. A missing key is equivalent to
// `unreviewed`, which lets us avoid writing zeros for every page of a
// 200-page document the reviewer hasn't touched yet.
let statuses = $state<Record<number, PageReviewStatus>>({});
let loading = $state(false);
let error = $state<string | null>(null);

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function load(documentId: string) {
	currentDocumentId = documentId;
	loading = true;
	error = null;
	statuses = {};
	try {
		const rows = await getPageReviews(documentId);
		const next: Record<number, PageReviewStatus> = {};
		for (const r of rows) next[r.page_number] = r.status;
		statuses = next;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Paginastatus laden mislukt';
	} finally {
		loading = false;
	}
}

function clear() {
	currentDocumentId = null;
	statuses = {};
	error = null;
}

function getStatus(pageNumber: number): PageReviewStatus {
	return statuses[pageNumber] ?? 'unreviewed';
}

/**
 * Set a page's status, persisting immediately.
 *
 * Optimistic: the local map flips right away so the indicator updates
 * instantly. If the PUT fails, the old value is restored and an error
 * string surfaces on the store — the review page shows this in the
 * existing error banner.
 */
async function setStatus(pageNumber: number, status: PageReviewStatus) {
	if (!currentDocumentId) return;
	const previous = statuses[pageNumber];
	statuses = { ...statuses, [pageNumber]: status };
	try {
		await upsertPageReview(currentDocumentId, pageNumber, status);
	} catch (e) {
		// Restore the exact prior entry (including "was missing").
		const rollback = { ...statuses };
		if (previous === undefined) delete rollback[pageNumber];
		else rollback[pageNumber] = previous;
		statuses = rollback;
		error = e instanceof Error ? e.message : 'Paginastatus opslaan mislukt';
	}
}

async function markComplete(pageNumber: number) {
	await setStatus(pageNumber, 'complete');
}

async function flag(pageNumber: number) {
	await setStatus(pageNumber, 'flagged');
}

/**
 * Move a page to `in_progress` automatically when a detection on that page
 * is reviewed (accepted/rejected/edited/deferred). We only bump the status
 * if the page is currently `unreviewed` — pages that are already
 * `complete` or `flagged` reflect a deliberate reviewer decision and must
 * not be silently downgraded.
 */
async function markInProgressIfUnreviewed(pageNumber: number) {
	const current = getStatus(pageNumber);
	if (current !== 'unreviewed') return;
	await setStatus(pageNumber, 'in_progress');
}

function clearError() {
	error = null;
}

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

function countByStatus(status: PageReviewStatus): number {
	let n = 0;
	for (const s of Object.values(statuses)) {
		if (s === status) n++;
	}
	return n;
}

const completedCount = $derived(countByStatus('complete'));
const flaggedCount = $derived(countByStatus('flagged'));

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const pageReviewStore = {
	get statuses() {
		return statuses;
	},
	get loading() {
		return loading;
	},
	get error() {
		return error;
	},
	get completedCount() {
		return completedCount;
	},
	get flaggedCount() {
		return flaggedCount;
	},
	getStatus,
	load,
	clear,
	setStatus,
	markComplete,
	flag,
	markInProgressIfUnreviewed,
	clearError
};
