/**
 * Structure-spans store (#20 bulk sweeps).
 *
 * Holds the `structure_spans` returned by `/api/analyze` for the currently
 * reviewed document — email headers, signature blocks, and salutations
 * found by the backend `structure_engine` (#14). The sidebar uses them to
 * render bulk-sweep chips that accept every pending detection inside one
 * block in a single undo-stack command.
 *
 * The spans are session-scoped, not persisted on the Detection record:
 * they disappear when the browser tab closes. To survive a soft reload
 * (Cmd-R) we cache the spans in `sessionStorage` keyed by document id —
 * analyze isn't re-run on reload, and without this the sweep affordances
 * would vanish the moment the reviewer refreshes.
 */

import type { StructureSpan } from '$lib/types';

const STORAGE_PREFIX = 'woobuddy:structure-spans:';

function storageKey(documentId: string): string {
	return `${STORAGE_PREFIX}${documentId}`;
}

function readFromStorage(documentId: string): StructureSpan[] {
	if (typeof sessionStorage === 'undefined') return [];
	try {
		const raw = sessionStorage.getItem(storageKey(documentId));
		if (!raw) return [];
		const parsed = JSON.parse(raw) as StructureSpan[];
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		// Corrupt blob — behave as if there were no spans. The sweep
		// affordances will simply not show until the next analyze run.
		return [];
	}
}

function writeToStorage(documentId: string, spans: StructureSpan[]): void {
	if (typeof sessionStorage === 'undefined') return;
	try {
		sessionStorage.setItem(storageKey(documentId), JSON.stringify(spans));
	} catch {
		// Storage full / disabled — the in-memory value is still
		// authoritative for this session, so just swallow the error.
	}
}

function clearStorage(documentId: string): void {
	if (typeof sessionStorage === 'undefined') return;
	try {
		sessionStorage.removeItem(storageKey(documentId));
	} catch {
		/* noop */
	}
}

let currentDocId = $state<string | null>(null);
let spans = $state<StructureSpan[]>([]);

function load(documentId: string) {
	currentDocId = documentId;
	spans = readFromStorage(documentId);
}

function set(documentId: string, nextSpans: StructureSpan[]) {
	currentDocId = documentId;
	spans = [...nextSpans];
	writeToStorage(documentId, nextSpans);
}

function clear() {
	if (currentDocId) clearStorage(currentDocId);
	currentDocId = null;
	spans = [];
}

export const structureSpansStore = {
	get spans() {
		return spans;
	},
	get documentId() {
		return currentDocId;
	},
	load,
	set,
	clear
};
