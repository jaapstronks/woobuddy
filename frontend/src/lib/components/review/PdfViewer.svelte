<script lang="ts" module>
	// Re-exported so existing call sites that import these from PdfViewer
	// keep working after the Phase 1/2 refactor.
	export type { SearchHighlight } from '$lib/services/pdf-overlay-draw';
	export type { PageReviewStatusValue } from './page-review-status';
</script>

<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import type { Detection, BoundingBox } from '$lib/types';
	import type { ReviewMode } from '$lib/stores/review.svelte';
	import {
		computeRectAnchor,
		computeSelectionAnchor,
		rangeToBoundingBoxes,
		rectToBoundingBox,
		snapRangeToWordBoundaries,
		type ManualSelection
	} from '$lib/services/selection-bbox';
	import {
		drawDetectionOverlays,
		drawSearchHighlights,
		type SearchHighlight
	} from '$lib/services/pdf-overlay-draw';
	import { loadPdfDocument, renderPdfPage } from '$lib/services/pdf-page-render';
	import PdfViewerToolbar from './PdfViewerToolbar.svelte';
	import PageStrip from './PageStrip.svelte';
	import PageReviewActions from './PageReviewActions.svelte';
	import BoundaryEditOverlay, { type HandleDir } from './BoundaryEditOverlay.svelte';
	import type { PageReviewStatusValue } from './page-review-status';

	interface Props {
		pdfData: ArrayBuffer | null;
		detections: Detection[];
		selectedDetectionId: string | null;
		currentPage: number;
		scale: number;
		mode: ReviewMode;
		onSelectDetection: (id: string) => void;
		onDeselect?: () => void;
		onPageChange: (page: number) => void;
		onModeChange: (mode: ReviewMode) => void;
		onManualSelection?: (selection: ManualSelection) => void;
		onManualSelectionCleared?: () => void;
		/**
		 * Boundary adjustment (#11). Fired when the reviewer commits an edit
		 * (Enter / Opslaan button). The parent wraps this in a
		 * `BoundaryAdjustCommand` so Ctrl+Z rolls it back. PdfViewer owns
		 * the editing state internally — this callback is the only hand-off.
		 */
		onBoundaryAdjust?: (detectionId: string, nextBboxes: BoundingBox[]) => void;
		/**
		 * Split mode (#18). When set, the detection with this id enters
		 * "awaiting split point" mode: the next click on one of its bboxes
		 * is intercepted (instead of the usual boundary-edit entry) and
		 * reported via `onSplitPointClick` as a PDF-space coordinate. The
		 * parent derives the two bbox sets and calls the server.
		 */
		splitPendingId?: string | null;
		/**
		 * Fired when the reviewer clicks inside `splitPendingId`'s overlay.
		 * `bboxIndex` is the index of the clicked bbox in the detection's
		 * `bounding_boxes`; `pdfX` / `pdfY` are the PDF-point coordinates of
		 * the click.
		 */
		onSplitPointClick?: (args: {
			detectionId: string;
			bboxIndex: number;
			pdfX: number;
			pdfY: number;
		}) => void;
		/**
		 * #18 — sidebar multi-select staging for merge. Bboxes whose detection
		 * id appears here get a secondary highlight so the reviewer can see
		 * which rows are queued for merging.
		 */
		mergeStagingIds?: string[];
		stageEl?: HTMLDivElement | null;
		/** Search-and-redact highlights for the current document (#09). */
		searchHighlights?: SearchHighlight[];
		/** Id of the highlight the reviewer just clicked — gets the focused style. */
		focusedSearchId?: string | null;
		/** Sparse map of page-number → status (#10). Missing ⇒ unreviewed. */
		pageStatuses?: Record<number, PageReviewStatusValue>;
		onMarkPageReviewed?: (page: number) => void;
		onFlagPage?: (page: number) => void;
		/**
		 * Reports the unscaled (PDF-point) dimensions of the current page after
		 * each render. The review page uses this to compute fit-to-width /
		 * fit-to-page scales without having to peek inside pdf.js itself.
		 */
		onPageNaturalSize?: (size: { width: number; height: number }) => void;
	}

	let {
		pdfData,
		detections,
		selectedDetectionId,
		currentPage,
		scale,
		mode,
		onSelectDetection,
		onDeselect,
		onPageChange,
		onModeChange,
		onManualSelection,
		onManualSelectionCleared,
		onBoundaryAdjust,
		splitPendingId = null,
		onSplitPointClick,
		mergeStagingIds = [],
		stageEl = $bindable(null),
		searchHighlights = [],
		focusedSearchId = null,
		pageStatuses = {},
		onMarkPageReviewed,
		onFlagPage,
		onPageNaturalSize
	}: Props = $props();

	let canvasEl = $state<HTMLCanvasElement | null>(null);
	let overlayEl = $state<HTMLDivElement | null>(null);
	let searchLayerEl = $state<HTMLDivElement | null>(null);
	let textLayerEl = $state<HTMLDivElement | null>(null);
	let pdfDoc = $state<any>(null);

	const currentPageStatus = $derived<PageReviewStatusValue>(
		pageStatuses[currentPage] ?? 'unreviewed'
	);
	const totalPages = $derived(pdfDoc?.numPages ?? 0);
	let rendering = false; // not reactive — just a guard flag
	// Reactive so the overlay/search-highlight effects re-run once renderPdf
	// finishes and updates the current viewport dimensions. Without this the
	// overlays would read stale container sizes after a zoom or resize.
	let viewportSize = $state({ width: 0, height: 0 });
	// Scale actually painted onto the canvas. Distinct from the `scale` prop,
	// which can be a frame ahead of the canvas when fit-to-width recomputes
	// mid-render. Overlays must read THIS value — not the live prop — or they
	// get drawn at coordinates that don't yet match the canvas paint, which
	// manifests as rectangles landing a few pixels off on initial load and
	// only "snapping" when a later resize forces another full render cycle.
	let renderedScale = $state(0);
	let currentTextLayer: { cancel: () => void } | null = null;

	// Area-selection draw state (#07). The live rectangle is reactive so it
	// renders declaratively alongside canvas/overlay; the start/current coords
	// are plain module-scoped variables because they change on every
	// mousemove and don't need to drive other reactive reads.
	let drawRect = $state<{ x: number; y: number; w: number; h: number } | null>(null);
	let drawingAreaClass = $state(false);
	let isDrawingArea = false;
	let drawStartX = 0;
	let drawStartY = 0;
	let drawCurrentX = 0;
	let drawCurrentY = 0;
	// When a Shift+drag ends, the same mouse gesture also fires a mouseup on
	// the text layer. Suppressing exactly one text-layer mouseup after the
	// area draw prevents that bubble from clearing the selection we just
	// pushed to the manual-selection store.
	let suppressNextTextLayerMouseUp = false;
	// Minimum rectangle size (pixels) — anything smaller is treated as an
	// accidental click and silently dropped (area selections are coarse by
	// nature; a <6px "draw" is overwhelmingly a misclick).
	const AREA_MIN_SIZE_PX = 6;

	// ---------------------------------------------------------------------
	// Boundary adjustment state (#11)
	//
	// When the reviewer clicks an existing detection in Edit mode, the
	// component enters a "boundary edit" state for that detection. Draft
	// bboxes are cloned into `editingBboxes` and rendered via the
	// BoundaryEditOverlay child with 8 resize handles per box;
	// drawDetectionOverlays hides the original overlay for the editing
	// detection so the two don't double up.
	//
	// Committing the edit (Enter or the floating Opslaan button) emits
	// `onBoundaryAdjust` to the parent, which wraps it in a
	// `BoundaryAdjustCommand` for undo/redo. Escape reverts the draft to
	// the snapshot taken when editing started.
	//
	// Per-bbox minimum size in PDF points: kept small because inline
	// redactions (e.g. a four-character date) are genuinely tiny. The
	// `BBOX_MIN_PT` floor just prevents degenerate zero/negative rects
	// when dragging handles past each other.
	// ---------------------------------------------------------------------
	const BBOX_MIN_PT = 2;
	// Keyboard nudge: pixels per Arrow keypress (no modifier) and Alt+Arrow
	// for sub-point precision. Values are in PDF points so they stay
	// zoom-independent on screen.
	const ARROW_NUDGE_PT = 3;
	const ARROW_NUDGE_FINE_PT = 0.5;

	let editingDetectionId = $state<string | null>(null);
	let editingBboxes = $state<BoundingBox[] | null>(null);
	// Snapshot captured when edit starts — `Escape` rolls back to this.
	// Not reactive because it only drives imperative reverts.
	let editingOriginalBboxes: BoundingBox[] | null = null;

	// Handle drag state — plain vars because they mutate on every mousemove.
	let dragHandle: {
		boxIndex: number;
		dir: HandleDir;
		startClientX: number;
		startClientY: number;
		initialBbox: BoundingBox;
	} | null = null;

	function cloneBboxes(bboxes: BoundingBox[]): BoundingBox[] {
		return bboxes.map((b) => ({ ...b }));
	}

	function enterBoundaryEdit(detectionId: string) {
		const det = detections.find((d) => d.id === detectionId);
		if (!det || !det.bounding_boxes || det.bounding_boxes.length === 0) return;
		editingDetectionId = detectionId;
		editingBboxes = cloneBboxes(det.bounding_boxes);
		editingOriginalBboxes = cloneBboxes(det.bounding_boxes);
		// Also mark the detection as selected so the sidebar row highlights.
		onSelectDetection(detectionId);
	}

	function cancelBoundaryEdit() {
		editingDetectionId = null;
		editingBboxes = null;
		editingOriginalBboxes = null;
		dragHandle = null;
	}

	function commitBoundaryEdit() {
		if (!editingDetectionId || !editingBboxes) return;
		const id = editingDetectionId;
		const next = cloneBboxes(editingBboxes);
		cancelBoundaryEdit();
		onBoundaryAdjust?.(id, next);
	}

	function resetBoundaryEditDraft() {
		if (!editingOriginalBboxes) return;
		editingBboxes = cloneBboxes(editingOriginalBboxes);
	}

	/** Apply a handle drag delta (in px) to the initial bbox. */
	function applyHandleDelta(
		initial: BoundingBox,
		dir: HandleDir,
		dxPt: number,
		dyPt: number
	): BoundingBox {
		let { x0, y0, x1, y1 } = initial;
		if (dir.includes('w')) x0 = Math.min(x1 - BBOX_MIN_PT, x0 + dxPt);
		if (dir.includes('e')) x1 = Math.max(x0 + BBOX_MIN_PT, x1 + dxPt);
		if (dir.includes('n')) y0 = Math.min(y1 - BBOX_MIN_PT, y0 + dyPt);
		if (dir.includes('s')) y1 = Math.max(y0 + BBOX_MIN_PT, y1 + dyPt);
		return { page: initial.page, x0, y0, x1, y1 };
	}

	function handleResizeMouseDown(e: MouseEvent, boxIndex: number, dir: HandleDir) {
		if (!editingBboxes) return;
		e.preventDefault();
		e.stopPropagation();
		dragHandle = {
			boxIndex,
			dir,
			startClientX: e.clientX,
			startClientY: e.clientY,
			initialBbox: { ...editingBboxes[boxIndex] }
		};
	}

	function handleBoundaryDragMove(e: MouseEvent) {
		if (!dragHandle || !editingBboxes) return;
		const dxPt = (e.clientX - dragHandle.startClientX) / scale;
		const dyPt = (e.clientY - dragHandle.startClientY) / scale;
		const updated = applyHandleDelta(dragHandle.initialBbox, dragHandle.dir, dxPt, dyPt);
		editingBboxes = editingBboxes.map((b, i) => (i === dragHandle!.boxIndex ? updated : b));
	}

	function handleBoundaryDragEnd() {
		dragHandle = null;
	}

	/**
	 * Nudge the currently-editing bbox(es) with an arrow key. Shift+Arrow
	 * shrinks the matching side (inward), plain Arrow extends outward.
	 * Alt+Arrow uses the fine step. Operates on all bboxes of the editing
	 * detection that sit on the current page — which for nearly all
	 * single-line detections is exactly one box.
	 */
	function nudgeEditingBbox(
		side: 'left' | 'right' | 'top' | 'bottom',
		stepPt: number,
		shrink: boolean
	) {
		if (!editingBboxes) return;
		const sign = shrink ? -1 : 1;
		editingBboxes = editingBboxes.map((b) => {
			if (b.page !== currentPage) return b;
			const nb = { ...b };
			if (side === 'left') nb.x0 = Math.min(nb.x1 - BBOX_MIN_PT, nb.x0 - sign * stepPt);
			if (side === 'right') nb.x1 = Math.max(nb.x0 + BBOX_MIN_PT, nb.x1 + sign * stepPt);
			if (side === 'top') nb.y0 = Math.min(nb.y1 - BBOX_MIN_PT, nb.y0 - sign * stepPt);
			if (side === 'bottom') nb.y1 = Math.max(nb.y0 + BBOX_MIN_PT, nb.y1 + sign * stepPt);
			return nb;
		});
	}

	/**
	 * Shift+click on a word in the text layer while a detection is being
	 * edited: extend (or shrink) the editing bbox on the current page to
	 * include the clicked word's rectangle. Alt+click on a word at the
	 * current bbox edge shrinks it to exclude that word. The word rect is
	 * derived from the clicked text-layer span's bounding client rect,
	 * converted to PDF points using the same helpers as manual selection.
	 */
	function handleTextLayerClick(e: MouseEvent) {
		if (mode !== 'edit' || !editingBboxes || !stageEl) return;
		if (!e.shiftKey && !e.altKey) return;
		const target = e.target as HTMLElement | null;
		// Text-layer glyphs are span elements; anything else (the container,
		// the endOfContent probe, whitespace) has nothing meaningful to grab.
		if (!target || target.tagName !== 'SPAN') return;
		const spanRect = target.getBoundingClientRect();
		const stageRect = stageEl.getBoundingClientRect();
		const wordBbox = rectToBoundingBox(
			{
				left: spanRect.left,
				top: spanRect.top,
				right: spanRect.right,
				bottom: spanRect.bottom
			},
			stageRect,
			scale,
			currentPage
		);
		e.preventDefault();
		e.stopPropagation();

		editingBboxes = editingBboxes.map((b) => {
			if (b.page !== currentPage) return b;
			if (e.shiftKey) {
				// Extend: union of current bbox and clicked word.
				return {
					page: b.page,
					x0: Math.min(b.x0, wordBbox.x0),
					y0: Math.min(b.y0, wordBbox.y0),
					x1: Math.max(b.x1, wordBbox.x1),
					y1: Math.max(b.y1, wordBbox.y1)
				};
			}
			// Alt+click: shrink to exclude the clicked word. We shrink along
			// whichever horizontal edge the word occupies. For a word on the
			// right edge, cap `x1` to the word's left; on the left edge, cap
			// `x0` to the word's right. Words in the middle are left alone
			// (mid-bbox exclusion would produce a gap we can't represent).
			const mid = (b.x0 + b.x1) / 2;
			const wMid = (wordBbox.x0 + wordBbox.x1) / 2;
			if (wMid >= mid) {
				const nx1 = Math.max(b.x0 + BBOX_MIN_PT, wordBbox.x0);
				return { ...b, x1: nx1 };
			}
			const nx0 = Math.min(b.x1 - BBOX_MIN_PT, wordBbox.x1);
			return { ...b, x0: nx0 };
		});
	}

	onMount(async () => {
		// Area-selection listeners live on the window so a drag that leaves
		// the stage mid-gesture still finishes cleanly.
		window.addEventListener('mousemove', handleWindowMouseMove);
		window.addEventListener('mouseup', handleWindowMouseUp);
		window.addEventListener('keydown', handleWindowKeyDown);

		// Client-first: PDF comes from the in-memory ArrayBuffer only.
		if (!pdfData) return;
		pdfDoc = await loadPdfDocument(pdfData);
	});

	onDestroy(() => {
		window.removeEventListener('mousemove', handleWindowMouseMove);
		window.removeEventListener('mouseup', handleWindowMouseUp);
		window.removeEventListener('keydown', handleWindowKeyDown);
	});

	async function renderPdf(pageNum: number) {
		if (!pdfDoc || !canvasEl || rendering) return;
		rendering = true;
		// Snapshot the scale we're about to paint so later `renderedScale`
		// update matches what actually landed on the canvas — reading `scale`
		// again after the await could return a newer value if the reviewer
		// zoomed mid-render.
		const activeScale = scale;
		try {
			const result = await renderPdfPage({
				pdfDoc,
				pageNum,
				scale: activeScale,
				canvas: canvasEl,
				textLayerEl,
				previousTextLayer: currentTextLayer
			});
			viewportSize = { width: result.width, height: result.height };
			renderedScale = activeScale;
			currentTextLayer = result.textLayer;
			// Report the unscaled page size so the parent can compute
			// fit-to-width / fit-to-page scales without peeking into pdf.js.
			onPageNaturalSize?.({ width: result.naturalWidth, height: result.naturalHeight });
		} finally {
			rendering = false;
		}
	}

	/**
	 * Click handler passed into drawDetectionOverlays. Routes the click to
	 * split-point reporting, boundary-edit entry, or plain selection
	 * depending on the current mode and split-pending state.
	 */
	function handleOverlayClick(e: MouseEvent, det: Detection, bboxIdx: number) {
		// #18 — split pending: clicking the target detection's bbox reports a
		// PDF-space click position instead of the usual boundary-edit entry.
		// Fires only for the pending detection; clicks on other detections
		// fall through to their normal behavior.
		if (splitPendingId === det.id && onSplitPointClick && stageEl) {
			const stageRect = stageEl.getBoundingClientRect();
			const pdfX = (e.clientX - stageRect.left) / scale;
			const pdfY = (e.clientY - stageRect.top) / scale;
			onSplitPointClick({ detectionId: det.id, bboxIndex: bboxIdx, pdfX, pdfY });
			return;
		}
		// Edit mode: clicking an existing detection enters the
		// boundary-edit flow instead of just highlighting it. Review mode
		// keeps the classic select-for-sidebar behavior.
		if (mode === 'edit') {
			enterBoundaryEdit(det.id);
		} else {
			onSelectDetection(det.id);
		}
	}

	// Text selection handling — only active in edit mode. On mouseup we read
	// the current native Selection, optionally snap to word boundaries, and
	// hand the resulting bboxes up so the review page can open the action bar.
	function handleTextLayerMouseUp(e: MouseEvent) {
		if (suppressNextTextLayerMouseUp) {
			// The area-draw mouseup chain emitted a selection already. Eat
			// this one so we don't immediately clear it.
			suppressNextTextLayerMouseUp = false;
			return;
		}
		if (mode !== 'edit' || !textLayerEl) return;
		// Defer: the browser finalizes the selection after the mouseup handler
		// has already run synchronously on a fresh click-to-clear.
		setTimeout(() => emitSelection(e.altKey), 0);
	}

	// ---------------------------------------------------------------------
	// Area selection (#07)
	//
	// In edit mode, Shift + mousedown on the PDF stage starts drawing a
	// rectangle. We use window-level mousemove/mouseup so drags that leave
	// the stage mid-gesture still finish cleanly. Text-layer selection is
	// suppressed by preventing the default on mousedown; a dedicated
	// `drawing-area` class also disables user-select on the text layer so
	// the two interactions never interleave visually.
	// ---------------------------------------------------------------------

	function cancelAreaDraw() {
		isDrawingArea = false;
		drawRect = null;
		drawingAreaClass = false;
	}

	function handleStageMouseDown(e: MouseEvent) {
		if (mode !== 'edit' || !e.shiftKey || !stageEl) return;
		// Ignore mousedowns that land on existing detection overlays.
		const target = e.target as HTMLElement | null;
		if (target?.dataset?.overlay === 'detection') return;

		// Kill the native text selection that would otherwise start when the
		// mousedown bubbles through the text layer.
		e.preventDefault();
		window.getSelection()?.removeAllRanges();

		const stageRect = stageEl.getBoundingClientRect();
		drawStartX = e.clientX - stageRect.left;
		drawStartY = e.clientY - stageRect.top;
		drawCurrentX = drawStartX;
		drawCurrentY = drawStartY;
		isDrawingArea = true;
		drawingAreaClass = true;
		drawRect = { x: drawStartX, y: drawStartY, w: 0, h: 0 };
	}

	function handleWindowMouseMove(e: MouseEvent) {
		// Boundary-edit resize drag takes precedence over any area draw,
		// because the two gestures are mutually exclusive (you can't be
		// mid-handle-drag while also dragging out a new rectangle).
		if (dragHandle) {
			handleBoundaryDragMove(e);
			return;
		}
		if (!isDrawingArea || !stageEl) return;
		const stageRect = stageEl.getBoundingClientRect();
		drawCurrentX = e.clientX - stageRect.left;
		drawCurrentY = e.clientY - stageRect.top;
		drawRect = {
			x: Math.min(drawStartX, drawCurrentX),
			y: Math.min(drawStartY, drawCurrentY),
			w: Math.abs(drawCurrentX - drawStartX),
			h: Math.abs(drawCurrentY - drawStartY)
		};
	}

	function handleWindowMouseUp() {
		if (dragHandle) {
			handleBoundaryDragEnd();
			return;
		}
		if (!isDrawingArea || !stageEl) return;
		isDrawingArea = false;
		stageEl.classList.remove('drawing-area');

		const w = Math.abs(drawCurrentX - drawStartX);
		const h = Math.abs(drawCurrentY - drawStartY);
		drawRect = null;

		if (w < AREA_MIN_SIZE_PX || h < AREA_MIN_SIZE_PX) {
			// Misclick — drop silently. Don't suppress the text-layer mouseup
			// either; there's no selection to protect.
			return;
		}

		const left = Math.min(drawStartX, drawCurrentX);
		const top = Math.min(drawStartY, drawCurrentY);
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

		const bbox = rectToBoundingBox(rectViewport, stageRect, scale, currentPage);
		const anchor = computeRectAnchor(rectViewport, stageRect, scale, currentPage);

		suppressNextTextLayerMouseUp = true;
		onManualSelection?.({
			page: currentPage,
			text: '',
			bboxes: [bbox],
			anchor
		});
	}

	function handleWindowKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape' && isDrawingArea) {
			cancelAreaDraw();
			return;
		}
		if (editingDetectionId) {
			// Don't interfere with typing in a form field (unlikely while
			// boundary-editing, but the review page has textareas for
			// motivations).
			const t = e.target as HTMLElement | null;
			if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) {
				return;
			}
			if (e.key === 'Escape') {
				e.preventDefault();
				// First Escape: revert draft to the snapshot. If the draft
				// already matches the snapshot (reviewer just wants to bail
				// out), exit boundary edit entirely.
				const draft = editingBboxes;
				const orig = editingOriginalBboxes;
				const matches =
					draft &&
					orig &&
					draft.length === orig.length &&
					draft.every(
						(b, i) =>
							b.x0 === orig[i].x0 &&
							b.y0 === orig[i].y0 &&
							b.x1 === orig[i].x1 &&
							b.y1 === orig[i].y1
					);
				if (matches) {
					cancelBoundaryEdit();
				} else {
					resetBoundaryEditDraft();
				}
				return;
			}
			if (e.key === 'Enter') {
				e.preventDefault();
				commitBoundaryEdit();
				return;
			}
			const stepPt = e.altKey ? ARROW_NUDGE_FINE_PT : ARROW_NUDGE_PT;
			// Shift inverts the gesture: shrink instead of extend.
			const shrink = e.shiftKey;
			// Both PdfViewer and KeyboardShortcuts register window keydown
			// listeners. While a boundary edit is active the arrow keys
			// belong to us — stopImmediatePropagation prevents the
			// KeyboardShortcuts listener from also treating them as
			// next/prev detection navigation.
			if (e.key === 'ArrowLeft') {
				e.preventDefault();
				e.stopImmediatePropagation();
				nudgeEditingBbox(shrink ? 'right' : 'left', stepPt, shrink);
				return;
			}
			if (e.key === 'ArrowRight') {
				e.preventDefault();
				e.stopImmediatePropagation();
				nudgeEditingBbox(shrink ? 'left' : 'right', stepPt, shrink);
				return;
			}
			if (e.key === 'ArrowUp') {
				e.preventDefault();
				e.stopImmediatePropagation();
				nudgeEditingBbox(shrink ? 'bottom' : 'top', stepPt, shrink);
				return;
			}
			if (e.key === 'ArrowDown') {
				e.preventDefault();
				e.stopImmediatePropagation();
				nudgeEditingBbox(shrink ? 'top' : 'bottom', stepPt, shrink);
				return;
			}
		}
	}

	function emitSelection(altKey: boolean) {
		if (!textLayerEl || !onManualSelection) return;
		const sel = window.getSelection();
		if (!sel || sel.rangeCount === 0) {
			onManualSelectionCleared?.();
			return;
		}
		const range = sel.getRangeAt(0);
		if (range.collapsed) {
			onManualSelectionCleared?.();
			return;
		}
		// Only accept selections that are inside the current page's text layer.
		// Invariant: we render one page at a time, so the browser cannot extend
		// a native selection across pages — there is nothing else in the
		// scroller for it to reach into. If we ever move to a virtual/paginated
		// scroller that keeps multiple pages in the DOM, this guard becomes
		// necessary-but-insufficient: the commonAncestorContainer could sit in
		// a shared parent and still span pages. Revisit this check before that
		// change lands.
		if (!textLayerEl.contains(range.commonAncestorContainer)) {
			onManualSelectionCleared?.();
			return;
		}

		if (!altKey) snapRangeToWordBoundaries(range);

		const text = range.toString().trim();
		if (!text) {
			onManualSelectionCleared?.();
			return;
		}

		const bboxes = rangeToBoundingBoxes(range, textLayerEl, scale, currentPage);
		if (bboxes.length === 0) {
			onManualSelectionCleared?.();
			return;
		}

		const anchor = computeSelectionAnchor(range, textLayerEl, scale, currentPage);
		if (!anchor) {
			onManualSelectionCleared?.();
			return;
		}

		onManualSelection({ page: currentPage, text, bboxes, anchor });
	}

	// Render PDF when page, doc, or scale changes — untrack internal state reads
	$effect(() => {
		// Reference reactive inputs so the effect reruns on change.
		void currentPage;
		void scale;
		if (pdfDoc) {
			untrack(() => renderPdf(currentPage));
		}
	});

	// Draw overlays when detections, selection, or page changes. Also
	// re-runs when `editingDetectionId` toggles so the editing detection's
	// DOM-built overlay disappears (and the Svelte-driven draft overlay
	// takes its place).
	$effect(() => {
		void detections;
		void selectedDetectionId;
		void currentPage;
		void editingDetectionId;
		// #18 — re-draw so split/merge visual cues appear the moment the
		// parent flips these props.
		void splitPendingId;
		void mergeStagingIds;
		// Zoom/resize: `renderedScale` + `viewportSize` are written together
		// at the end of `renderPdf`, so reading them here guarantees the
		// overlays always use the same scale that was actually painted onto
		// the canvas. Reading the live `scale` prop used to be the bug — it
		// could be one render ahead, leaving rectangles at the new scale on
		// top of the old canvas paint until a later resize forced another
		// full render cycle.
		void renderedScale;
		void viewportSize;
		if (pdfDoc && overlayEl && renderedScale > 0) {
			untrack(() => {
				drawDetectionOverlays({
					overlayEl: overlayEl!,
					detections,
					pageNum: currentPage,
					scale: renderedScale,
					viewportSize,
					selectedDetectionId,
					editingDetectionId,
					splitPendingId,
					mergeStagingIds,
					onOverlayClick: handleOverlayClick
				});
			});
		}
	});

	// Scroll the selected detection's overlay into view and pulse it briefly
	// so the reviewer can spot the matching rectangle in the PDF the moment
	// they click a sidebar row. Only re-runs when the selection or current
	// page changes — accepting/rejecting detections also re-draws the
	// overlay layer, but we don't want to keep re-scrolling on every status
	// change while the user is reviewing the same selection.
	let lastScrolledKey: string | null = null;
	$effect(() => {
		const id = selectedDetectionId;
		void currentPage;
		void renderedScale;
		if (!overlayEl || !id) {
			lastScrolledKey = null;
			return;
		}
		const key = `${id}::${currentPage}`;
		if (lastScrolledKey === key) return;
		lastScrolledKey = key;
		// Defer so the overlay DOM is in place after drawOverlays runs.
		// requestAnimationFrame, not queueMicrotask: drawOverlays runs in
		// its own effect and we need the appendChild calls to have flushed.
		requestAnimationFrame(() => {
			if (!overlayEl) return;
			const el = overlayEl.querySelector<HTMLElement>(
				`[data-detection-id="${CSS.escape(id)}"]`
			);
			if (!el) return;
			el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
			el.classList.remove('overlay-selected-pulse');
			void el.offsetWidth;
			el.classList.add('overlay-selected-pulse');
			el.addEventListener(
				'animationend',
				() => el.classList.remove('overlay-selected-pulse'),
				{ once: true }
			);
		});
	});

	// Draw search highlights whenever the result set, focus, page, or scale
	// changes. Kept separate from the detection overlay redraw so typing in
	// the search box doesn't force a detection re-render.
	$effect(() => {
		void searchHighlights;
		void focusedSearchId;
		void currentPage;
		void renderedScale;
		void viewportSize;
		if (pdfDoc && searchLayerEl && renderedScale > 0) {
			untrack(() => {
				drawSearchHighlights({
					searchLayerEl: searchLayerEl!,
					searchHighlights,
					pageNum: currentPage,
					scale: renderedScale,
					viewportSize,
					focusedSearchId
				});
			});
		}
	});

	// Leaving edit mode clears any in-progress native selection so the
	// browser's blue highlight doesn't linger into Review mode. Also aborts
	// any area draw that was mid-gesture, and cancels any boundary edit in
	// progress (Review mode has no concept of it).
	$effect(() => {
		if (mode === 'review') {
			untrack(() => {
				window.getSelection()?.removeAllRanges();
				cancelAreaDraw();
				cancelBoundaryEdit();
				onManualSelectionCleared?.();
			});
		}
	});

	// Changing pages mid-draw would strand the rectangle on a page it wasn't
	// drawn on — cancel cleanly instead. A page change mid-boundary-edit
	// also drops the draft (the editing detection is probably on a
	// different page anyway).
	$effect(() => {
		void currentPage;
		untrack(() => {
			if (isDrawingArea) cancelAreaDraw();
			if (editingDetectionId) cancelBoundaryEdit();
		});
	});

	// If the detection being edited disappears from the store (e.g. undo
	// removed it) or no longer exists, drop the edit state so we don't
	// render handles over nothing.
	$effect(() => {
		void detections;
		untrack(() => {
			if (editingDetectionId && !detections.some((d) => d.id === editingDetectionId)) {
				cancelBoundaryEdit();
			}
		});
	});

	/**
	 * Briefly flash the overlays for the given detection ids so the reviewer
	 * can see what an undo/redo just touched. The animation is driven by a
	 * CSS keyframe (`.overlay-flash`) and removes itself on `animationend`
	 * — no JS timers beyond the class toggle. Ids that aren't on the current
	 * page are silently skipped; a detection being deleted by undo won't
	 * exist in the overlay layer anymore, which is fine (the sidebar list
	 * row disappearing is signal enough that the action took effect).
	 */
	export function flashDetections(ids: string[]) {
		if (!overlayEl || ids.length === 0) return;
		for (const id of ids) {
			const els = overlayEl.querySelectorAll<HTMLElement>(
				`[data-detection-id="${CSS.escape(id)}"]`
			);
			for (const el of els) {
				// Restart the animation if the class is already on — removing
				// and re-adding inside a rAF cycle forces the keyframe to
				// play again.
				el.classList.remove('overlay-flash');
				void el.offsetWidth;
				el.classList.add('overlay-flash');
				el.addEventListener('animationend', () => el.classList.remove('overlay-flash'), {
					once: true
				});
			}
		}
	}
</script>

<div
	class="relative overflow-auto rounded-lg border border-gray-200 bg-white"
	class:edit-mode={mode === 'edit'}
>
	<PdfViewerToolbar
		{mode}
		{currentPage}
		{totalPages}
		{currentPageStatus}
		{onModeChange}
		{onPageChange}
	/>

	<!-- Page strip (#10): horizontally-scrolling row of numbered chips -->
	{#if pdfDoc && totalPages > 1}
		<PageStrip {totalPages} {currentPage} {pageStatuses} {onPageChange} />
	{/if}

	<!-- PDF canvas + overlay + text layer -->
	<div class="relative flex justify-center p-4">
		{#if !pdfDoc}
			<div class="flex h-96 items-center justify-center text-neutral">PDF laden...</div>
		{:else}
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				bind:this={stageEl}
				class="pdf-stage relative"
				class:cursor-pointer={mode === 'review'}
				class:edit-active={mode === 'edit'}
				class:drawing-area={drawingAreaClass}
				onmousedown={handleStageMouseDown}
				onclick={(e) => {
					// Clicks on overlays stopPropagation, so reaching here means empty space.
					if ((e.target as HTMLElement)?.dataset.overlay === 'detection') return;
					if (mode === 'review') onDeselect?.();
				}}
			>
				<canvas bind:this={canvasEl}></canvas>
				<div bind:this={searchLayerEl} class="search-layer absolute top-0 left-0"></div>
				<div bind:this={overlayEl} class="overlay absolute top-0 left-0"></div>
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					bind:this={textLayerEl}
					class="textLayer absolute top-0 left-0"
					onmouseup={handleTextLayerMouseUp}
					onclick={handleTextLayerClick}
				></div>
				<!-- Boundary adjustment draft overlay (#11). Rendered above
				     the text layer so its handles are clickable; the box
				     itself is inert to pointer events, so mousedowns inside
				     the box (but outside a handle) still reach the text
				     layer for Shift/Alt+click word extension. -->
				{#if editingBboxes}
					<BoundaryEditOverlay
						{editingBboxes}
						{currentPage}
						{scale}
						onHandleMouseDown={handleResizeMouseDown}
						onCommit={commitBoundaryEdit}
						onCancel={cancelBoundaryEdit}
					/>
				{/if}
				{#if drawRect}
					<!-- Live area-draw rectangle (#07). Inert to pointer events so
					     mousemove continues to reach the window listener. -->
					<div
						class="area-draw"
						style="left: {drawRect.x}px; top: {drawRect.y}px; width: {drawRect.w}px; height: {drawRect.h}px;"
					></div>
				{/if}
				{#if onMarkPageReviewed || onFlagPage}
					<PageReviewActions
						{currentPage}
						{currentPageStatus}
						{onMarkPageReviewed}
						{onFlagPage}
					/>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	.edit-mode {
		border-top: 2px solid var(--color-primary, #1b4f72);
	}

	/* Live area-draw rectangle (#07). Sits on top of the text layer so the
	   reviewer can see what they're about to redact; inert to pointer
	   events so the window-level mousemove/mouseup still fire. */
	.area-draw {
		position: absolute;
		background: rgba(27, 79, 114, 0.12);
		border: 1px solid var(--color-primary, #1b4f72);
		pointer-events: none;
		z-index: 3;
	}
	/* While an area draw is in progress, suppress text-layer selection so
	   the two interactions don't interleave visually. */
	.pdf-stage.drawing-area .textLayer {
		user-select: none;
		cursor: crosshair;
	}
	.pdf-stage.drawing-area {
		cursor: crosshair;
	}

	/* Search-and-redact highlights (#09). A dedicated layer under the
	   detection overlay so search hits can't steal clicks from existing
	   detections and vice versa. Inert to pointer events — the reviewer
	   acts on search hits through the sidebar list, not by clicking
	   through the PDF. */
	.search-layer {
		position: absolute;
		inset: 0;
		pointer-events: none;
		z-index: 1;
	}
	.search-layer :global(.search-hit) {
		position: absolute;
		background: rgba(250, 204, 21, 0.3);
		border: 1px solid rgba(202, 138, 4, 0.7);
		border-radius: 2px;
	}
	.search-layer :global(.search-hit-focused) {
		background: rgba(250, 204, 21, 0.55);
		border-color: #a16207;
		box-shadow: 0 0 0 2px rgba(250, 204, 21, 0.9);
	}
	.search-layer :global(.search-hit-muted) {
		background: rgba(156, 163, 175, 0.18);
		border: 1px dashed rgba(107, 114, 128, 0.6);
	}

	/* Detection overlays: clickable in both modes so reviewers can enter
	   boundary edit by clicking an existing detection in Edit mode (#11).
	   The container itself is pass-through so mousedowns on the gaps
	   between detection rectangles still reach the text layer. */
	.overlay {
		pointer-events: none;
		z-index: 2;
	}
	.overlay :global(> *) {
		pointer-events: auto;
	}

	/* Minimal subset of pdfjs-dist/web/pdf_viewer.css for the text layer.
	   We only need selection-capable transparent spans; highlights and the
	   end-of-content probe aren't used here. */
	.textLayer {
		text-align: initial;
		overflow: clip;
		opacity: 1;
		line-height: 1;
		transform-origin: 0 0;
		user-select: none;
		pointer-events: none;
		z-index: 1;
	}
	.pdf-stage.edit-active .textLayer {
		user-select: text;
		pointer-events: auto;
		cursor: text;
	}
	.textLayer :global(span),
	.textLayer :global(br) {
		color: transparent;
		position: absolute;
		white-space: pre;
		cursor: inherit;
		transform-origin: 0% 0%;
	}
	.textLayer :global(.endOfContent) {
		display: block;
		position: absolute;
		inset: 100% 0 0;
		z-index: -1;
		cursor: default;
		user-select: none;
	}
	.textLayer :global(::selection) {
		background: rgba(27, 79, 114, 0.35);
	}

	/* Undo/redo flash (#08). A short yellow pulse applied to a detection
	   overlay by `flashDetections()`. CSS-only — the class removes itself
	   on animationend, no JS timer bookkeeping. */
	.overlay :global(.overlay-flash) {
		animation: overlay-flash 300ms ease-out;
		box-shadow: 0 0 0 2px rgba(250, 204, 21, 0.9);
	}
	@keyframes overlay-flash {
		0% {
			box-shadow: 0 0 0 0 rgba(250, 204, 21, 0);
			background-color: rgba(250, 204, 21, 0.55);
		}
		60% {
			box-shadow: 0 0 0 4px rgba(250, 204, 21, 0.9);
			background-color: rgba(250, 204, 21, 0.35);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(250, 204, 21, 0);
			background-color: transparent;
		}
	}

	/* Sidebar-click pulse. Triggered when the reviewer selects a detection
	   from the sidebar — pairs with `scrollIntoView` to draw the eye to the
	   matching rectangle. Distinct from `.overlay-flash` (which marks
	   undo/redo): this uses the primary brand color so it reads as "this is
	   the one you just clicked", not "something just changed". */
	.overlay :global(.overlay-selected-pulse) {
		animation: overlay-selected-pulse 700ms ease-out;
	}
	@keyframes overlay-selected-pulse {
		0% {
			box-shadow:
				0 0 0 0 rgba(27, 79, 114, 0.7),
				0 0 0 0 rgba(27, 79, 114, 0.45);
		}
		60% {
			box-shadow:
				0 0 0 6px rgba(27, 79, 114, 0),
				0 0 0 14px rgba(27, 79, 114, 0.18);
		}
		100% {
			box-shadow: 0 0 0 6px rgba(27, 79, 114, 0.18);
		}
	}
</style>
