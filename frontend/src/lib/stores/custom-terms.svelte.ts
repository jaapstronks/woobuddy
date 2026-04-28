/**
 * Custom-terms store (#21 — per-document "eigen zoektermen").
 *
 * Holds the list of reviewer-typed search terms that must be redacted
 * throughout the currently viewed document. Local-only since #50:
 * every term is a client-generated row, mirrored to the IndexedDB
 * session cache. Terms ride along inline with the next `/api/analyze`
 * call via {@link analyzePayload} — the server never persists them.
 *
 * The store is intentionally a near-copy of `reference-names.svelte.ts`
 * — the two features share the same persistence shape and UX pattern.
 * The only difference in intent is direction: reference names flip
 * matching detections to `rejected`, custom terms produce new
 * `accepted` detections.
 *
 * Like the reference-names store, this module does NOT call
 * `/api/analyze` itself — that concern stays on the review page where
 * the extraction and the undo stack live.
 */

import {
	readSessionState,
	writeSessionStateSlice
} from '$lib/services/session-state-store';
import type { CustomTerm } from '$lib/types';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocumentId = $state<string | null>(null);
let terms = $state<CustomTerm[]>([]);
let loading = $state(false);
let error = $state<string | null>(null);

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function persist(): Promise<void> {
	if (!currentDocumentId) return;
	// $state.snapshot — IDB's structured-clone algorithm rejects Svelte 5
	// $state Proxies. Snapshot to a plain array before write.
	await writeSessionStateSlice(currentDocumentId, {
		customTerms: $state.snapshot(terms)
	});
}

async function load(documentId: string): Promise<void> {
	currentDocumentId = documentId;
	loading = true;
	error = null;
	terms = [];
	try {
		const state = await readSessionState(documentId);
		terms = state?.customTerms ?? [];
	} catch (e) {
		error = e instanceof Error ? e.message : 'Zoektermen laden mislukt';
	} finally {
		loading = false;
	}
}

function clear(): void {
	currentDocumentId = null;
	terms = [];
	error = null;
}

/**
 * Add a term to the custom wordlist. Returns the created row on
 * success, `null` on failure. The caller is responsible for triggering
 * a re-analysis after the promise resolves so the new term's matches
 * appear in the detection list.
 */
async function add(term: string, wooArticle: string = '5.1.2e'): Promise<CustomTerm | null> {
	if (!currentDocumentId) return null;
	const trimmed = term.trim();
	if (!trimmed) return null;
	error = null;
	const created: CustomTerm = {
		id: crypto.randomUUID(),
		document_id: currentDocumentId,
		term: trimmed,
		// Backend renormalizes server-side — local form is for UI dedup only.
		normalized_term: trimmed.normalize('NFKC').toLocaleLowerCase('nl-NL'),
		match_mode: 'exact',
		woo_article: wooArticle,
		created_at: new Date().toISOString()
	};
	terms = [...terms, created];
	await persist();
	return created;
}

/**
 * Remove a term by id. Returns whether the term existed; the caller
 * then re-analyzes so the corresponding `custom` detections disappear
 * from the list.
 */
async function remove(id: string): Promise<boolean> {
	if (!currentDocumentId) return false;
	error = null;
	const before = terms.length;
	terms = terms.filter((t) => t.id !== id);
	if (terms.length === before) return false;
	await persist();
	return true;
}

function clearError(): void {
	error = null;
}

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

/** The payload the analyze endpoint expects — one object per term, in
 *  the same shape the backend's `CustomTermPayload` validates. */
const analyzePayload = $derived(
	terms.map((t) => ({
		term: t.term,
		match_mode: t.match_mode,
		woo_article: t.woo_article
	}))
);

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const customTermsStore = {
	get terms() {
		return terms;
	},
	get analyzePayload() {
		return analyzePayload;
	},
	get count() {
		return terms.length;
	},
	get loading() {
		return loading;
	},
	get error() {
		return error;
	},
	load,
	clear,
	add,
	remove,
	clearError
};
