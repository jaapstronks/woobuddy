/**
 * Commands that mutate per-document lists (the reference-name list and
 * the custom-term wordlist) and trigger a re-analysis as a side effect.
 *
 * The review page injects a `reanalyze` callback so each forward/reverse
 * triggers a fresh `/api/analyze` pass with the updated list — that's what
 * flips matched detections to `rejected` (on add) or back to `pending`
 * (on remove). Keeping that concern outside the command means we don't
 * have to thread the extraction state through the undo store.
 */

import { referenceNamesStore } from '$lib/stores/reference-names.svelte';
import { customTermsStore } from '$lib/stores/custom-terms.svelte';
import type { Command } from './command';

/**
 * Add a name to the per-document reference list (#17). The command
 * remembers the server-assigned id after the first `forward()` so
 * `reverse()` can delete that exact row and a subsequent redo can
 * recreate it (as a brand-new row — we don't try to preserve the id
 * across a delete/recreate cycle because the analyze pipeline only
 * cares about the normalized display name, not the id).
 */
export class AddReferenceNameCommand implements Command {
	readonly label = 'Naam toevoegen aan lijst';
	private createdId: string | null = null;

	constructor(
		private readonly displayName: string,
		private readonly reanalyze: () => Promise<void>
	) {}

	get affectedDetectionIds(): string[] {
		// Reference-name commands don't target a specific detection — the
		// re-analysis may touch zero or many rows depending on what's in
		// the document. Returning an empty list skips the viewer flash,
		// which is the right default here (a bulk re-analysis is not
		// localized enough to highlight meaningfully).
		return [];
	}

	async forward(): Promise<void> {
		const created = await referenceNamesStore.add(this.displayName);
		if (!created) {
			// Store already set the error; signal the undo store to drop
			// this command rather than pushing a no-op entry.
			throw new Error(this.label + ' mislukt');
		}
		this.createdId = created.id;
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		if (!this.createdId) return;
		const ok = await referenceNamesStore.remove(this.createdId);
		if (!ok) return;
		this.createdId = null;
		await this.reanalyze();
	}
}

/**
 * Remove a name from the per-document reference list (#17). Captures
 * the original row at construction time so `reverse()` can recreate it
 * with the same display name (the server assigns a new id — that's
 * fine, the normalized name is what matters for matching).
 */
export class RemoveReferenceNameCommand implements Command {
	readonly label = 'Naam verwijderen van lijst';
	private currentId: string;

	constructor(
		initialId: string,
		private readonly displayName: string,
		private readonly reanalyze: () => Promise<void>
	) {
		this.currentId = initialId;
	}

	get affectedDetectionIds(): string[] {
		return [];
	}

	async forward(): Promise<void> {
		const ok = await referenceNamesStore.remove(this.currentId);
		if (!ok) {
			throw new Error(this.label + ' mislukt');
		}
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		// Re-create under a fresh id — the normalized name is what the
		// analyze pipeline matches on, not the id.
		const recreated = await referenceNamesStore.add(this.displayName);
		if (!recreated) return;
		this.currentId = recreated.id;
		await this.reanalyze();
	}
}

/**
 * Add a term to the per-document custom wordlist (#21). Mirrors
 * `AddReferenceNameCommand`: remembers the server-assigned id on the
 * first `forward()` so `reverse()` can delete that exact row, and a
 * subsequent redo recreates it. Each forward/reverse triggers a
 * re-analysis via the injected callback so the resulting `custom`
 * detections appear or disappear in the sidebar.
 */
export class AddCustomTermCommand implements Command {
	readonly label = 'Zoekterm toevoegen';
	private createdId: string | null = null;

	constructor(
		private readonly term: string,
		private readonly wooArticle: string,
		private readonly reanalyze: () => Promise<void>
	) {}

	get affectedDetectionIds(): string[] {
		// A reanalysis may touch many detections across the document;
		// flashing all of them would be noisy. Returning an empty list
		// skips the viewer flash — the same default as the reference-
		// name commands for the same reason.
		return [];
	}

	async forward(): Promise<void> {
		const created = await customTermsStore.add(this.term, this.wooArticle);
		if (!created) {
			throw new Error(this.label + ' mislukt');
		}
		this.createdId = created.id;
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		if (!this.createdId) return;
		const ok = await customTermsStore.remove(this.createdId);
		if (!ok) return;
		this.createdId = null;
		await this.reanalyze();
	}
}

/**
 * Remove a term from the per-document custom wordlist (#21). Captures
 * the term's text + article at construction time so `reverse()` can
 * recreate it through the store (the server assigns a fresh id — the
 * matcher only cares about the normalized term, not the id).
 */
export class RemoveCustomTermCommand implements Command {
	readonly label = 'Zoekterm verwijderen';
	private currentId: string;

	constructor(
		initialId: string,
		private readonly term: string,
		private readonly wooArticle: string,
		private readonly reanalyze: () => Promise<void>
	) {
		this.currentId = initialId;
	}

	get affectedDetectionIds(): string[] {
		return [];
	}

	async forward(): Promise<void> {
		const ok = await customTermsStore.remove(this.currentId);
		if (!ok) {
			throw new Error(this.label + ' mislukt');
		}
		await this.reanalyze();
	}

	async reverse(): Promise<void> {
		const recreated = await customTermsStore.add(this.term, this.wooArticle);
		if (!recreated) return;
		this.currentId = recreated.id;
		await this.reanalyze();
	}
}
