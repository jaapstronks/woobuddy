/**
 * Area-selection draw controller (#07) — extracted from PdfViewer.svelte.
 *
 * Owns the "Shift+drag on the stage" gesture: live rectangle state,
 * start/current coordinates, the min-size misclick filter, and the
 * one-shot `suppressNextTextLayerMouseUp` flag that prevents the
 * trailing text-layer mouseup from wiping the selection we just
 * pushed upstream.
 *
 * Class-based rather than a module-level singleton so its lifetime is
 * tied to a single PdfViewer instance — matches BoundaryEditController.
 */

import { computeRectAnchor, rectToBoundingBox, type ManualSelection } from './selection-bbox';

// Minimum rectangle size (pixels) — anything smaller is treated as an
// accidental click and silently dropped (area selections are coarse by
// nature; a <6px "draw" is overwhelmingly a misclick).
const AREA_MIN_SIZE_PX = 6;

interface AreaDrawParams {
	getStageEl: () => HTMLDivElement | null;
	getCurrentPage: () => number;
	getScale: () => number;
	onManualSelection?: (selection: ManualSelection) => void;
}

export class AreaDrawController {
	/** Live draw rectangle in stage-local pixels; rendered declaratively. */
	drawRect = $state<{ x: number; y: number; w: number; h: number } | null>(null);
	/** Reactive class toggle for the stage div (cursor + text-layer disable). */
	drawingAreaClass = $state(false);
	#isDrawing = false;
	#startX = 0;
	#startY = 0;
	#currentX = 0;
	#currentY = 0;
	// When a Shift+drag ends, the same mouse gesture also fires a mouseup on
	// the text layer. Suppressing exactly one text-layer mouseup after the
	// area draw prevents that bubble from clearing the selection we just
	// pushed to the manual-selection store.
	#suppressNextTextLayerMouseUp = false;
	#params: AreaDrawParams;

	constructor(params: AreaDrawParams) {
		this.#params = params;
	}

	get isDrawing() {
		return this.#isDrawing;
	}

	/**
	 * One-shot read: returns whether the next text-layer mouseup should
	 * be ignored (because it's the trailing edge of a completed area
	 * draw). Clears the flag as a side effect.
	 */
	consumeSuppressTextLayerMouseUp(): boolean {
		if (!this.#suppressNextTextLayerMouseUp) return false;
		this.#suppressNextTextLayerMouseUp = false;
		return true;
	}

	cancel() {
		this.#isDrawing = false;
		this.drawRect = null;
		this.drawingAreaClass = false;
	}

	handleStageMouseDown(e: MouseEvent) {
		// Area draw works in both modes — the Shift modifier is the explicit
		// signal, so there's no ambiguity with review-mode clicks.
		if (!e.shiftKey) return;
		const stageEl = this.#params.getStageEl();
		if (!stageEl) return;
		// Ignore mousedowns that land on existing detection overlays.
		const target = e.target as HTMLElement | null;
		if (target?.dataset?.overlay === 'detection') return;

		// Kill the native text selection that would otherwise start when the
		// mousedown bubbles through the text layer.
		e.preventDefault();
		window.getSelection()?.removeAllRanges();

		const stageRect = stageEl.getBoundingClientRect();
		this.#startX = e.clientX - stageRect.left;
		this.#startY = e.clientY - stageRect.top;
		this.#currentX = this.#startX;
		this.#currentY = this.#startY;
		this.#isDrawing = true;
		this.drawingAreaClass = true;
		this.drawRect = { x: this.#startX, y: this.#startY, w: 0, h: 0 };
	}

	handleWindowMouseMove(e: MouseEvent) {
		if (!this.#isDrawing) return;
		const stageEl = this.#params.getStageEl();
		if (!stageEl) return;
		const stageRect = stageEl.getBoundingClientRect();
		this.#currentX = e.clientX - stageRect.left;
		this.#currentY = e.clientY - stageRect.top;
		this.drawRect = {
			x: Math.min(this.#startX, this.#currentX),
			y: Math.min(this.#startY, this.#currentY),
			w: Math.abs(this.#currentX - this.#startX),
			h: Math.abs(this.#currentY - this.#startY)
		};
	}

	handleWindowMouseUp() {
		if (!this.#isDrawing) return;
		const stageEl = this.#params.getStageEl();
		if (!stageEl) {
			this.cancel();
			return;
		}
		this.#isDrawing = false;
		stageEl.classList.remove('drawing-area');
		this.drawingAreaClass = false;

		const w = Math.abs(this.#currentX - this.#startX);
		const h = Math.abs(this.#currentY - this.#startY);
		this.drawRect = null;

		if (w < AREA_MIN_SIZE_PX || h < AREA_MIN_SIZE_PX) {
			// Misclick — drop silently. Don't suppress the text-layer mouseup
			// either; there's no selection to protect.
			return;
		}

		const left = Math.min(this.#startX, this.#currentX);
		const top = Math.min(this.#startY, this.#currentY);
		const stageRect = stageEl.getBoundingClientRect();
		// Reconstruct a viewport-space rect so the shared helpers in
		// selection-bbox.ts (which operate in absolute viewport coords) can
		// convert it to a PDF-point bbox and an anchor the same way the
		// text-selection flow does.
		const rectViewport = {
			left: stageRect.left + left,
			top: stageRect.top + top,
			right: stageRect.left + left + w,
			bottom: stageRect.top + top + h
		};

		const page = this.#params.getCurrentPage();
		const scale = this.#params.getScale();
		const bbox = rectToBoundingBox(rectViewport, stageRect, scale, page);
		const anchor = computeRectAnchor(rectViewport, stageRect, scale, page);

		this.#suppressNextTextLayerMouseUp = true;
		this.#params.onManualSelection?.({
			page,
			text: '',
			bboxes: [bbox],
			anchor
		});
	}
}
