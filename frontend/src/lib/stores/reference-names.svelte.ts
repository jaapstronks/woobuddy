/**
 * Reference-names store (#17 — per-document "publiek functionarissen" list).
 *
 * Holds the list of names the reviewer has marked as "niet lakken" for
 * the currently viewed document. The backend persists them in the
 * `document_reference_names` table; this store is the frontend mirror
 * and the single source of truth for the review screen.
 *
 * Adding or removing a name is expected to trigger a re-analysis on the
 * review page — this store exposes `add` / `remove` but does NOT itself
 * call `/api/analyze`, so that concern stays on the page where the
 * extraction and undo stack live.
 */

import {
	createReferenceName,
	deleteReferenceName,
	getReferenceNames
} from '$lib/api/client';
import type { ReferenceName } from '$lib/types';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocumentId = $state<string | null>(null);
let names = $state<ReferenceName[]>([]);
let loading = $state(false);
let error = $state<string | null>(null);

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function load(documentId: string): Promise<void> {
	currentDocumentId = documentId;
	loading = true;
	error = null;
	names = [];
	try {
		names = await getReferenceNames(documentId);
	} catch (e) {
		error = e instanceof Error ? e.message : 'Referentielijst laden mislukt';
	} finally {
		loading = false;
	}
}

function clear(): void {
	currentDocumentId = null;
	names = [];
	error = null;
}

/**
 * Add a name to the reference list. Returns the created row on success,
 * `null` on failure (the error is surfaced on the store). The caller is
 * responsible for triggering a re-analysis after the promise resolves
 * so newly-matched detections flip to `rejected`.
 */
async function add(displayName: string): Promise<ReferenceName | null> {
	if (!currentDocumentId) return null;
	const trimmed = displayName.trim();
	if (!trimmed) return null;
	error = null;
	try {
		const created = await createReferenceName(currentDocumentId, trimmed);
		// Server is authoritative — even though we could optimistically
		// append, the 201 response is fast and returning the row with the
		// server-assigned id/normalized form keeps the undo stack honest.
		names = [...names, created];
		return created;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Naam toevoegen mislukt';
		return null;
	}
}

/**
 * Remove a name by id. Like `add`, returns whether the server accepted
 * the change; the caller then re-analyzes so previously-rejected
 * detections by this reference can flip back to `pending`.
 */
async function remove(id: string): Promise<boolean> {
	if (!currentDocumentId) return false;
	error = null;
	try {
		await deleteReferenceName(currentDocumentId, id);
		names = names.filter((n) => n.id !== id);
		return true;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Naam verwijderen mislukt';
		return false;
	}
}

function clearError(): void {
	error = null;
}

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

/** The list of display names, in the exact form the reviewer typed them.
 *  Used when calling `/api/analyze` — the server normalizes on its side. */
const displayNames = $derived(names.map((n) => n.display_name));

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const referenceNamesStore = {
	get names() {
		return names;
	},
	get displayNames() {
		return displayNames;
	},
	get count() {
		return names.length;
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
