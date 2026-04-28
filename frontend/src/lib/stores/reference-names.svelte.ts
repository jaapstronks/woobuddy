/**
 * Reference-names store (#17 — per-document "publiek functionarissen" list).
 *
 * Holds the list of names the reviewer has marked as "niet lakken" for
 * the currently viewed document. Local-only since #50: every entry is a
 * client-generated row, mirrored to the IndexedDB session cache so a
 * Cmd+R restores it. The names ride along inline with the next
 * `/api/analyze` call (see `analyzePayload` consumers in the review
 * page) — the server never persists them.
 *
 * Adding or removing a name is expected to trigger a re-analysis on the
 * review page. This store exposes `add` / `remove` but does NOT itself
 * call `/api/analyze`, so that concern stays on the page where the
 * extraction and undo stack live.
 */

import {
	readSessionState,
	writeSessionStateSlice
} from '$lib/services/session-state-store';
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

async function persist(): Promise<void> {
	if (!currentDocumentId) return;
	// $state.snapshot — IDB's structured-clone algorithm rejects Svelte 5
	// $state Proxies. Snapshot to a plain array before write.
	await writeSessionStateSlice(currentDocumentId, {
		referenceNames: $state.snapshot(names)
	});
}

/**
 * Hydrate the store from the IndexedDB session cache for `documentId`.
 * Clears any prior state first so switching documents does not bleed
 * names across reviews.
 */
async function load(documentId: string): Promise<void> {
	currentDocumentId = documentId;
	loading = true;
	error = null;
	names = [];
	try {
		const state = await readSessionState(documentId);
		names = state?.referenceNames ?? [];
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
	const created: ReferenceName = {
		id: crypto.randomUUID(),
		document_id: currentDocumentId,
		display_name: trimmed,
		// Match the backend's `unicodedata.normalize('NFKC', ...).casefold()`
		// behaviour — the only consumer of `normalized_name` is the analyze
		// pipeline server-side, which renormalizes anyway, so a simple
		// casefold here is enough for local UI dedup.
		normalized_name: trimmed.normalize('NFKC').toLocaleLowerCase('nl-NL'),
		role_hint: 'publiek_functionaris',
		created_at: new Date().toISOString()
	};
	names = [...names, created];
	await persist();
	return created;
}

/**
 * Remove a name by id. Returns whether the name existed; the caller
 * then re-analyzes so previously-rejected detections by this reference
 * can flip back to `pending`.
 */
async function remove(id: string): Promise<boolean> {
	if (!currentDocumentId) return false;
	error = null;
	const before = names.length;
	names = names.filter((n) => n.id !== id);
	if (names.length === before) return false;
	await persist();
	return true;
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
