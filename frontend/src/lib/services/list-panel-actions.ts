/**
 * Reference-name and custom-term panel action helpers.
 *
 * Extracted from the review page so the undo-command wiring for add/remove
 * operations on both per-document lists lives in one place.
 */

import { detectionStore } from '$lib/stores/detections.svelte';
import { referenceNamesStore } from '$lib/stores/reference-names.svelte';
import { customTermsStore } from '$lib/stores/custom-terms.svelte';
import {
	undoStore,
	AddReferenceNameCommand,
	RemoveReferenceNameCommand,
	AddCustomTermCommand,
	RemoveCustomTermCommand
} from '$lib/stores/undo.svelte';

/**
 * Re-run the analyze pipeline with the current extraction and the
 * latest reference-name + custom-term lists. Called after every
 * add/remove (and every undo/redo of those) so newly-matched
 * detections update in place. No-op if extraction isn't loaded yet.
 */
export async function reanalyzeWithLists(docId: string): Promise<void> {
	const extraction = detectionStore.extraction;
	if (!extraction) return;
	await detectionStore.analyze(
		docId,
		extraction.pages,
		referenceNamesStore.displayNames,
		customTermsStore.analyzePayload
	);
}

export async function handleAddReferenceName(
	displayName: string,
	docId: string
): Promise<void> {
	const reanalyze = () => reanalyzeWithLists(docId);
	const cmd = new AddReferenceNameCommand(displayName, reanalyze);
	try {
		await undoStore.push(cmd);
	} catch {
		// referenceNamesStore.error carries the message.
	}
}

export async function handleRemoveReferenceName(
	id: string,
	displayName: string,
	docId: string
): Promise<void> {
	const reanalyze = () => reanalyzeWithLists(docId);
	const cmd = new RemoveReferenceNameCommand(id, displayName, reanalyze);
	try {
		await undoStore.push(cmd);
	} catch {
		// referenceNamesStore.error carries the message.
	}
}

export async function handleAddCustomTerm(
	term: string,
	wooArticle: string,
	docId: string
): Promise<void> {
	const reanalyze = () => reanalyzeWithLists(docId);
	const cmd = new AddCustomTermCommand(term, wooArticle, reanalyze);
	try {
		await undoStore.push(cmd);
	} catch {
		// customTermsStore.error carries the message.
	}
}

export async function handleRemoveCustomTerm(
	id: string,
	term: string,
	docId: string
): Promise<void> {
	const reanalyze = () => reanalyzeWithLists(docId);
	const existing = customTermsStore.terms.find((t) => t.id === id);
	const wooArticle = existing?.woo_article ?? '5.1.2e';
	const cmd = new RemoveCustomTermCommand(id, term, wooArticle, reanalyze);
	try {
		await undoStore.push(cmd);
	} catch {
		// customTermsStore.error carries the message.
	}
}
