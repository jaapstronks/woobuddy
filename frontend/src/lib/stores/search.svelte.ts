/**
 * Search-and-Redact store (#09).
 *
 * Owns the search UI state: open/closed, query string, selected-occurrence
 * set, and a "focused" occurrence id for visual emphasis on the PDF. The
 * occurrence list itself is derived directly from the detection store's
 * extraction + live detection set, so typing into the input reactively
 * updates results and any redaction that lands during a search session
 * automatically re-flags overlapping matches as `alreadyRedacted`.
 *
 * The store deliberately does NOT own the redaction side effect. The
 * review page builds a `BatchCommand` from the selected occurrences and
 * pushes it onto the undo stack — same pattern as the accept-all batches
 * — so search-redact rows participate in undo/redo just like any other
 * manual detection.
 */

import { detectionStore } from '$lib/stores/detections.svelte';
import { searchDocument, type SearchOccurrence } from '$lib/services/search-redact';

let open = $state(false);
let query = $state('');
let selectedIds = $state<Set<string>>(new Set());
let focusedId = $state<string | null>(null);

const results = $derived.by<SearchOccurrence[]>(() =>
	searchDocument(query, detectionStore.extraction, detectionStore.all)
);

/**
 * Results partitioned so the UI can show "already redacted" in a separate,
 * greyed-out group. Keeping the split here avoids re-filtering twice in
 * the component (list + count).
 */
const redactable = $derived(results.filter((r) => !r.alreadyRedacted));
const alreadyRedacted = $derived(results.filter((r) => r.alreadyRedacted));

/**
 * `selectedIds` is a raw set the reviewer writes into; `effectiveSelected`
 * re-intersects it with the live `redactable` list so stale ids (from a
 * narrowed query, or from occurrences that just got redacted) can't leak
 * into the bulk redaction. We can't use `$effect` here — this file is a
 * module, not a component — so the intersection is a `$derived` that the
 * UI reads for counts and for the "Lak geselecteerde" trigger.
 */
const effectiveSelected = $derived.by(() => {
	const valid = new Set(redactable.map((r) => r.id));
	const next: SearchOccurrence[] = [];
	for (const r of redactable) {
		if (selectedIds.has(r.id) && valid.has(r.id)) next.push(r);
	}
	return next;
});

function setOpen(value: boolean) {
	open = value;
	if (!value) {
		// Closing the panel resets transient state but KEEPS the query so
		// Ctrl+F → Escape → Ctrl+F feels like a toggle, not a reset.
		selectedIds = new Set();
		focusedId = null;
	}
}

function toggle() {
	setOpen(!open);
}

function setQuery(next: string) {
	query = next;
	// Any edit invalidates the focused occurrence — it may no longer exist.
	focusedId = null;
}

function toggleSelected(id: string) {
	const next = new Set(selectedIds);
	if (next.has(id)) next.delete(id);
	else next.add(id);
	selectedIds = next;
}

function selectAll() {
	selectedIds = new Set(redactable.map((r) => r.id));
}

function clearSelection() {
	selectedIds = new Set();
}

function focus(id: string | null) {
	focusedId = id;
}

/** Returns the currently-selected occurrences in list order. */
function getSelectedOccurrences(): SearchOccurrence[] {
	return effectiveSelected;
}

export const searchStore = {
	get open() {
		return open;
	},
	get query() {
		return query;
	},
	get results() {
		return results;
	},
	get redactable() {
		return redactable;
	},
	get alreadyRedacted() {
		return alreadyRedacted;
	},
	get selectedIds() {
		return selectedIds;
	},
	get effectiveSelectedCount() {
		return effectiveSelected.length;
	},
	get focusedId() {
		return focusedId;
	},
	setOpen,
	toggle,
	setQuery,
	toggleSelected,
	selectAll,
	clearSelection,
	focus,
	getSelectedOccurrences
};
