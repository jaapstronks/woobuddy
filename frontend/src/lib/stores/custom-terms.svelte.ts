/**
 * Custom-terms store (#21 — per-document "eigen zoektermen").
 *
 * Holds the list of reviewer-typed search terms that must be redacted
 * throughout the currently viewed document. Persisted in the backend's
 * `document_custom_terms` table; this store is the frontend mirror and
 * the single source of truth for the review screen.
 *
 * The store is intentionally a near-copy of `reference-names.svelte.ts`
 * — the two features share the same persistence shape and UX pattern.
 * The only difference in intent is direction: reference names flip
 * matching detections to `rejected`, custom terms produce new
 * `accepted` detections. That asymmetry lives in the undo commands
 * and the review-page wiring; at the store layer it is just a CRUD.
 *
 * Like the reference-names store, this module does NOT call
 * `/api/analyze` itself — that concern stays on the review page where
 * the extraction and the undo stack live.
 */

import {
	createCustomTerm,
	deleteCustomTerm,
	getCustomTerms
} from '$lib/api/client';
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

async function load(documentId: string): Promise<void> {
	currentDocumentId = documentId;
	loading = true;
	error = null;
	terms = [];
	try {
		terms = await getCustomTerms(documentId);
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
 * success, `null` on failure (the error is surfaced on the store).
 * The caller is responsible for triggering a re-analysis after the
 * promise resolves so the new term's matches appear in the detection
 * list.
 */
async function add(term: string, wooArticle: string = '5.1.2e'): Promise<CustomTerm | null> {
	if (!currentDocumentId) return null;
	const trimmed = term.trim();
	if (!trimmed) return null;
	error = null;
	try {
		const created = await createCustomTerm(currentDocumentId, trimmed, wooArticle);
		// Server is authoritative — the 201 response carries the
		// normalized form and the server-assigned id, both of which
		// the undo stack needs to reverse this action cleanly.
		terms = [...terms, created];
		return created;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Zoekterm toevoegen mislukt';
		return null;
	}
}

/**
 * Remove a term by id. Returns whether the server accepted the
 * change; the caller then re-analyzes so the corresponding `custom`
 * detections disappear from the list.
 */
async function remove(id: string): Promise<boolean> {
	if (!currentDocumentId) return false;
	error = null;
	try {
		await deleteCustomTerm(currentDocumentId, id);
		terms = terms.filter((t) => t.id !== id);
		return true;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Zoekterm verwijderen mislukt';
		return false;
	}
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
