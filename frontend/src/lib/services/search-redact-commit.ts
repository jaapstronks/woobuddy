/**
 * Search-and-redact commit helper (#09) — extracted from
 * routes/review/[docId]/+page.svelte.
 *
 * Wraps the "reviewer picked an article + motivation and wants to redact
 * all matching occurrences at once" flow. The page file previously owned
 * ~30 lines of command-building here; moving it out of the route keeps
 * the page focused on layout and gives this batch action a clean
 * unit-test seam.
 */

import type { SearchOccurrence } from './search-redact';
import type { WooArticleCode, EntityType, DetectionTier } from '$lib/types';
import {
	undoStore,
	BatchCommand,
	CreateManualCommand,
	type Command
} from '$lib/stores/undo.svelte';

export interface RedactOccurrencesPayload {
	occurrences: SearchOccurrence[];
	article: WooArticleCode;
	entityType: EntityType;
	tier: DetectionTier;
	motivation: string;
}

/**
 * Build a BatchCommand from the given occurrences and push it onto the
 * undo stack. No-op on an empty list. Errors surface through
 * `detectionStore.error` — the caller's banner shows the message, so we
 * swallow the exception here rather than re-throwing.
 */
export async function redactSearchOccurrences(
	documentId: string,
	payload: RedactOccurrencesPayload
): Promise<void> {
	if (payload.occurrences.length === 0) return;
	const children: Command[] = payload.occurrences.map(
		(occ) =>
			new CreateManualCommand({
				documentId,
				bboxes: occ.bboxes,
				// `matchText` is client-only — kept in the in-memory detection
				// so the sidebar can show it, never sent to the server.
				selectedText: occ.matchText,
				entityType: payload.entityType,
				tier: payload.tier,
				wooArticle: payload.article,
				motivation: payload.motivation,
				source: 'search_redact'
			})
	);
	try {
		await undoStore.push(new BatchCommand(`Zoek & lak (${children.length})`, children));
	} catch {
		// detectionStore.error already carries the message — the banner
		// above the viewer will render it.
	}
}
