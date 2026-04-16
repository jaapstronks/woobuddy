/**
 * Boundary-adjustment controller (#11) — extracted from PdfViewer.svelte.
 *
 * Owns the "reviewer is resizing an existing detection's bbox" state
 * machine: the draft bboxes, the snapshot used by Escape, the
 * mid-drag handle state, the commit/cancel flow, and the text-layer
 * Shift/Alt+click word extension.
 *
 * Kept as a class (with runes for reactive fields) rather than a
 * module-level singleton store so its lifetime is tied to a single
 * PdfViewer instance. Pure geometry lives alongside in
 * `boundary-edit-geometry.ts`; this file owns the stateful bits.
 */

import type { Detection, BoundingBox } from '$lib/types';
import {
	applyHandleDelta,
	arrowKeyToNudge,
	bboxesEqual,
	cloneBboxes,
	extendBboxToWord,
	nudgeBbox,
	shrinkBboxByWord,
	type HandleDir
} from './boundary-edit-geometry';
import { rectToBoundingBox } from './selection-bbox';

interface BoundaryEditParams {
	getDetections: () => Detection[];
	getCurrentPage: () => number;
	getScale: () => number;
	getStageEl: () => HTMLDivElement | null;
	getMode: () => 'review' | 'edit';
	onSelectDetection: (id: string) => void;
	onBoundaryAdjust?: (detectionId: string, nextBboxes: BoundingBox[]) => void;
}

export class BoundaryEditController {
	editingDetectionId = $state<string | null>(null);
	editingBboxes = $state<BoundingBox[] | null>(null);
	// Snapshot captured when edit starts — `Escape` rolls back to this.
	// Not reactive because it only drives imperative reverts.
	#editingOriginalBboxes: BoundingBox[] | null = null;
	// Handle drag state — plain field because it mutates on every mousemove
	// and doesn't need to drive reactive reads.
	#dragHandle: {
		boxIndex: number;
		dir: HandleDir;
		startClientX: number;
		startClientY: number;
		initialBbox: BoundingBox;
	} | null = null;
	#params: BoundaryEditParams;

	constructor(params: BoundaryEditParams) {
		this.#params = params;
	}

	get isEditing() {
		return this.editingDetectionId !== null;
	}

	get isDraggingHandle() {
		return this.#dragHandle !== null;
	}

	enter(detectionId: string) {
		const det = this.#params.getDetections().find((d) => d.id === detectionId);
		if (!det || !det.bounding_boxes || det.bounding_boxes.length === 0) return;
		this.editingDetectionId = detectionId;
		this.editingBboxes = cloneBboxes(det.bounding_boxes);
		this.#editingOriginalBboxes = cloneBboxes(det.bounding_boxes);
		// Also mark the detection as selected so the sidebar row highlights.
		this.#params.onSelectDetection(detectionId);
	}

	cancel() {
		this.editingDetectionId = null;
		this.editingBboxes = null;
		this.#editingOriginalBboxes = null;
		this.#dragHandle = null;
	}

	commit() {
		if (!this.editingDetectionId || !this.editingBboxes) return;
		const id = this.editingDetectionId;
		const next = cloneBboxes(this.editingBboxes);
		this.cancel();
		this.#params.onBoundaryAdjust?.(id, next);
	}

	#resetDraft() {
		if (!this.#editingOriginalBboxes) return;
		this.editingBboxes = cloneBboxes(this.#editingOriginalBboxes);
	}

	handleResizeMouseDown(e: MouseEvent, boxIndex: number, dir: HandleDir) {
		if (!this.editingBboxes) return;
		e.preventDefault();
		e.stopPropagation();
		this.#dragHandle = {
			boxIndex,
			dir,
			startClientX: e.clientX,
			startClientY: e.clientY,
			initialBbox: { ...this.editingBboxes[boxIndex] }
		};
	}

	handleDragMove(e: MouseEvent) {
		if (!this.#dragHandle || !this.editingBboxes) return;
		const scale = this.#params.getScale();
		const drag = this.#dragHandle;
		const dxPt = (e.clientX - drag.startClientX) / scale;
		const dyPt = (e.clientY - drag.startClientY) / scale;
		const updated = applyHandleDelta(drag.initialBbox, drag.dir, dxPt, dyPt);
		this.editingBboxes = this.editingBboxes.map((b, i) => (i === drag.boxIndex ? updated : b));
	}

	handleDragEnd() {
		this.#dragHandle = null;
	}

	/**
	 * Nudge the currently-editing bbox(es) with an arrow key. Operates on
	 * all bboxes of the editing detection that sit on the current page —
	 * which for nearly all single-line detections is exactly one box.
	 * Geometry lives in `boundary-edit-geometry.ts`.
	 */
	nudgeEditingBbox(
		side: 'left' | 'right' | 'top' | 'bottom',
		stepPt: number,
		shrink: boolean
	) {
		if (!this.editingBboxes) return;
		const page = this.#params.getCurrentPage();
		this.editingBboxes = this.editingBboxes.map((b) =>
			b.page === page ? nudgeBbox(b, side, stepPt, shrink) : b
		);
	}

	/**
	 * Shift+click on a word in the text layer while a detection is being
	 * edited: extend (or shrink) the editing bbox on the current page to
	 * include the clicked word's rectangle. Alt+click on a word at the
	 * current bbox edge shrinks it to exclude that word. The word rect is
	 * derived from the clicked text-layer span's bounding client rect,
	 * converted to PDF points using the same helpers as manual selection.
	 */
	handleTextLayerClick(e: MouseEvent) {
		if (this.#params.getMode() !== 'edit' || !this.editingBboxes) return;
		if (!e.shiftKey && !e.altKey) return;
		const stageEl = this.#params.getStageEl();
		if (!stageEl) return;
		const target = e.target as HTMLElement | null;
		// Text-layer glyphs are span elements; anything else (the container,
		// the endOfContent probe, whitespace) has nothing meaningful to grab.
		if (!target || target.tagName !== 'SPAN') return;
		const spanRect = target.getBoundingClientRect();
		const stageRect = stageEl.getBoundingClientRect();
		const page = this.#params.getCurrentPage();
		const scale = this.#params.getScale();
		const wordBbox = rectToBoundingBox(
			{
				left: spanRect.left,
				top: spanRect.top,
				right: spanRect.right,
				bottom: spanRect.bottom
			},
			stageRect,
			scale,
			page
		);
		e.preventDefault();
		e.stopPropagation();

		this.editingBboxes = this.editingBboxes.map((b) => {
			if (b.page !== page) return b;
			return e.shiftKey ? extendBboxToWord(b, wordBbox) : shrinkBboxByWord(b, wordBbox);
		});
	}

	/**
	 * Handle a window keydown while an edit is in progress. Returns
	 * `true` if the controller consumed the event so the caller can
	 * short-circuit any other handling; `false` if there's no active
	 * edit or the key isn't one of ours.
	 *
	 * Input/textarea targets are silently ignored so the review page's
	 * motivation textarea keeps working while a detection is being
	 * edited.
	 */
	handleKeyDown(e: KeyboardEvent): boolean {
		if (!this.editingDetectionId) return false;
		const t = e.target as HTMLElement | null;
		if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) {
			return false;
		}
		if (e.key === 'Escape') {
			e.preventDefault();
			// First Escape: revert draft to the snapshot. If the draft
			// already matches the snapshot (reviewer just wants to bail
			// out), exit boundary edit entirely.
			if (bboxesEqual(this.editingBboxes, this.#editingOriginalBboxes)) {
				this.cancel();
			} else {
				this.#resetDraft();
			}
			return true;
		}
		if (e.key === 'Enter') {
			e.preventDefault();
			this.commit();
			return true;
		}
		// Both PdfViewer and KeyboardShortcuts register window keydown
		// listeners. While a boundary edit is active the arrow keys
		// belong to us — stopImmediatePropagation prevents the
		// KeyboardShortcuts listener from also treating them as
		// next/prev detection navigation.
		const nudge = arrowKeyToNudge(e.key, e.shiftKey, e.altKey);
		if (nudge) {
			e.preventDefault();
			e.stopImmediatePropagation();
			this.nudgeEditingBbox(nudge.side, nudge.stepPt, nudge.shrink);
			return true;
		}
		return false;
	}
}
