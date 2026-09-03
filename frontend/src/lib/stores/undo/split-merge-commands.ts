/**
 * Split and merge commands (#18) — the undo counterparts of
 * `detectionStore.split` / `detectionStore.merge`.
 *
 * Both actions delete their inputs and insert freshly generated rows, so
 * neither can be rolled back by replaying a status change: the reverse has
 * to put the captured originals back and drop the products. Until these
 * existed, `Ctrl+Z` after a split or a merge popped whatever unrelated
 * command happened to sit on top of the stack — the reviewer undid an
 * action they hadn't just performed (#66/2).
 */

import type { BoundingBox, Detection } from '$lib/types';
import { detectionStore } from '$lib/stores/detections.svelte';
import type { Command } from './command';

/**
 * Wait for the overlay flash (driven by `undoStore.lastAffected`, set
 * before `reverse()` runs) to play on the rows we are about to delete.
 * Same 300ms the manual-redaction command uses.
 */
const FLASH_MS = 300;

export class SplitCommand implements Command {
	readonly label = 'Splitsen';
	/** The row as it was before the split — the thing `reverse()` restores. */
	private original: Detection | null = null;
	/** Ids of the two halves produced by the most recent `forward()`. */
	private createdIds: string[] = [];

	constructor(
		private readonly detectionId: string,
		private readonly bboxesA: BoundingBox[],
		private readonly bboxesB: BoundingBox[]
	) {}

	get affectedDetectionIds(): string[] {
		return this.createdIds.length > 0 ? this.createdIds : [this.detectionId];
	}

	async forward(): Promise<void> {
		const before = detectionStore.byId[this.detectionId];
		if (!before) throw new Error('Splitsen mislukt: detectie niet gevonden');
		// Snapshot rather than hold the reference: the store replaces rows
		// wholesale, so the live object would drift out from under us.
		this.original = { ...before };
		const halves = await detectionStore.split(
			this.detectionId,
			this.bboxesA,
			this.bboxesB
		);
		if (!halves) throw new Error('Splitsen mislukt');
		this.createdIds = halves.map((d) => d.id);
	}

	async reverse(): Promise<void> {
		if (!this.original || this.createdIds.length === 0) return;
		await new Promise((r) => setTimeout(r, FLASH_MS));
		await detectionStore.replaceRows({
			removeIds: this.createdIds,
			insert: [this.original],
			select: this.original.id
		});
	}
}

export class MergeCommand implements Command {
	readonly label: string;
	/** The rows as they were before the merge, in click order. */
	private originals: Detection[] = [];
	/** Id of the row produced by the most recent `forward()`. */
	private mergedId: string | null = null;

	constructor(private readonly detectionIds: string[]) {
		this.label = `Samenvoegen (${detectionIds.length})`;
	}

	get affectedDetectionIds(): string[] {
		return this.mergedId ? [this.mergedId] : this.detectionIds;
	}

	async forward(): Promise<void> {
		this.originals = this.detectionIds
			.map((id) => detectionStore.byId[id])
			.filter((d): d is Detection => d !== undefined)
			.map((d) => ({ ...d }));
		if (this.originals.length !== this.detectionIds.length) {
			throw new Error('Samenvoegen mislukt: detectie niet gevonden');
		}
		// Pass the ids explicitly: on a redo the multi-select the reviewer
		// originally made is long gone.
		const merged = await detectionStore.merge(this.detectionIds);
		if (!merged) throw new Error(detectionStore.error ?? 'Samenvoegen mislukt');
		this.mergedId = merged.id;
	}

	async reverse(): Promise<void> {
		if (!this.mergedId || this.originals.length === 0) return;
		await new Promise((r) => setTimeout(r, FLASH_MS));
		await detectionStore.replaceRows({
			removeIds: [this.mergedId],
			insert: this.originals,
			select: this.originals[0].id
		});
	}
}
