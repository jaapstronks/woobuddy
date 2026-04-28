/**
 * Page reviews store (#10 — page completeness).
 *
 * Tracks per-page status (unreviewed/in_progress/complete/flagged) for
 * the currently viewed document. The store stays sparse — a missing
 * key reads as `unreviewed`, so for a 200-page document the reviewer
 * only persists the pages they've actually touched.
 *
 * Local-only since #50: every status flip is mirrored into the
 * IndexedDB session cache so a Cmd+R restores the chips. Nothing is
 * sent to the server.
 */

import {
	readSessionState,
	writeSessionStateSlice
} from '$lib/services/session-state-store';
import type { PageReviewStatus } from '$lib/types';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocumentId = $state<string | null>(null);
let statuses = $state<Record<number, PageReviewStatus>>({});
let loading = $state(false);
let error = $state<string | null>(null);

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function persist(): Promise<void> {
	if (!currentDocumentId) return;
	// $state.snapshot — IDB's structured-clone algorithm rejects Svelte 5
	// $state Proxies. Snapshot to a plain object before write.
	await writeSessionStateSlice(currentDocumentId, {
		pageReviews: $state.snapshot(statuses)
	});
}

async function load(documentId: string) {
	currentDocumentId = documentId;
	loading = true;
	error = null;
	statuses = {};
	try {
		const state = await readSessionState(documentId);
		statuses = state?.pageReviews ?? {};
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
 * Set a page's status, mirroring the change to IDB. Local-only — no
 * optimistic-vs-confirmed split: the assignment is the truth.
 */
async function setStatus(pageNumber: number, status: PageReviewStatus) {
	if (!currentDocumentId) return;
	statuses = { ...statuses, [pageNumber]: status };
	await persist();
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
