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
	import { type ManualSelection } from '$lib/services/selection-bbox';
	import { readTextLayerSelection } from '$lib/services/pdf-text-selection';
	import {
		drawDetectionOverlays,
		drawSearchHighlights,
		type SearchHighlight
	} from '$lib/services/pdf-overlay-draw';
	import {
		flashOverlays,
		scrollDetectionIntoView
	} from '$lib/services/pdf-overlay-effects';
	import { loadPdfDocument, renderPdfPage } from '$lib/services/pdf-page-render';
	import PdfViewerToolbar from './PdfViewerToolbar.svelte';
	import PageStrip from './PageStrip.svelte';
	import PageReviewActions from './PageReviewActions.svelte';
	import BoundaryEditOverlay from './BoundaryEditOverlay.svelte';
	import { BoundaryEditController } from '$lib/services/boundary-edit-controller.svelte';
	import { AreaDrawController } from '$lib/services/area-draw-controller.svelte';
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

	// ---------------------------------------------------------------------
	// Interaction controllers
	//
	// Two independent gesture state machines live alongside the PDF canvas:
	//
	//  - BoundaryEditController (#11) — clicking an existing detection in
	//    Edit mode enters a draft-bbox flow with 8 resize handles per box,
	//    keyboard nudging, and Shift/Alt+click word extension. Committing
	//    emits `onBoundaryAdjust` which the parent wraps in a
	//    BoundaryAdjustCommand for undo/redo.
	//
	//  - AreaDrawController (#07) — Shift+drag on the stage draws a live
	//    rectangle and emits a manual-selection bbox when released.
	//
	// Both controllers are class-based with their own $state fields
	// (declared in their respective `.svelte.ts` files) so this component
	// stays focused on canvas rendering, overlay dispatch, and text-layer
	// handling. They read per-frame props (scale, currentPage, mode,
	// stageEl) via closures so updates always reach them without a manual
	// sync step.
	// ---------------------------------------------------------------------

	const boundaryEdit = new BoundaryEditController({
		getDetections: () => detections,
		getCurrentPage: () => currentPage,
		getScale: () => scale,
		getStageEl: () => stageEl,
		getMode: () => mode,
		onSelectDetection: (id) => onSelectDetection(id),
		onBoundaryAdjust: (id, next) => onBoundaryAdjust?.(id, next)
	});

	const areaDraw = new AreaDrawController({
		getStageEl: () => stageEl,
		getCurrentPage: () => currentPage,
		getScale: () => scale,
		onManualSelection: (selection) => onManualSelection?.(selection)
	});

	onMount(() => {
		// Area-selection listeners live on the window so a drag that leaves
		// the stage mid-gesture still finishes cleanly.
		window.addEventListener('mousemove', handleWindowMouseMove);
		window.addEventListener('mouseup', handleWindowMouseUp);
		window.addEventListener('keydown', handleWindowKeyDown);
	});

	onDestroy(() => {
		window.removeEventListener('mousemove', handleWindowMouseMove);
		window.removeEventListener('mouseup', handleWindowMouseUp);
		window.removeEventListener('keydown', handleWindowKeyDown);
	});

	// Load the pdf.js document whenever `pdfData` becomes available. Using
	// `$effect` instead of `onMount` matters: the review page sets `pdfData`
	// *after* `detectionStore.load` resolves, which can land after PdfViewer
	// has already mounted. An onMount-only load would see `pdfData === null`
	// and leave the viewer stuck at "PDF laden…".
	$effect(() => {
		if (!pdfData) return;
		const bytes = pdfData;
		let cancelled = false;
		(async () => {
			const doc = await loadPdfDocument(bytes);
			if (!cancelled) pdfDoc = doc;
		})();
		return () => {
			cancelled = true;
		};
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
			boundaryEdit.enter(det.id);
		} else {
			onSelectDetection(det.id);
		}
	}

	// Text selection handling. On mouseup we read the current native
	// Selection, optionally snap to word boundaries, and hand the
	// resulting bboxes up so the review page can open the action bar.
	function handleTextLayerMouseUp(e: MouseEvent) {
		if (areaDraw.consumeSuppressTextLayerMouseUp()) {
			// The area-draw mouseup chain emitted a selection already. Eat
			// this one so we don't immediately clear it.
			return;
		}
		if (!textLayerEl) return;
		// Defer: the browser finalizes the selection after the mouseup handler
		// has already run synchronously on a fresh click-to-clear.
		// Hybrid interaction: text-drag produces a manual redaction in both
		// Beoordelen and Bewerken. The only thing the mode gates is what a
		// click on an existing detection does (select-for-sidebar vs.
		// enter-boundary-edit) — see handleOverlayClick.
		setTimeout(() => emitSelection(e.altKey), 0);
	}

	// Window-level mouse handlers dispatch to whichever controller is
	// active. Boundary-edit resize drag takes precedence over any area
	// draw, because the two gestures are mutually exclusive (you can't be
	// mid-handle-drag while also dragging out a new rectangle).
	function handleWindowMouseMove(e: MouseEvent) {
		if (boundaryEdit.isDraggingHandle) {
			boundaryEdit.handleDragMove(e);
			return;
		}
		areaDraw.handleWindowMouseMove(e);
	}

	function handleWindowMouseUp() {
		if (boundaryEdit.isDraggingHandle) {
			boundaryEdit.handleDragEnd();
			return;
		}
		areaDraw.handleWindowMouseUp();
	}

	function handleWindowKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape' && areaDraw.isDrawing) {
			areaDraw.cancel();
			return;
		}
		boundaryEdit.handleKeyDown(e);
	}

	function emitSelection(altKey: boolean) {
		if (!textLayerEl || !onManualSelection) return;
		const payload = readTextLayerSelection({ textLayerEl, scale, currentPage, altKey });
		if (payload === null) {
			onManualSelectionCleared?.();
			return;
		}
		onManualSelection(payload);
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
	// re-runs when the boundary-edit target toggles so the editing
	// detection's DOM-built overlay disappears (and the Svelte-driven
	// draft overlay takes its place).
	$effect(() => {
		void detections;
		void selectedDetectionId;
		void currentPage;
		void boundaryEdit.editingDetectionId;
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
			const editingId = boundaryEdit.editingDetectionId;
			untrack(() => {
				drawDetectionOverlays({
					overlayEl: overlayEl!,
					detections,
					pageNum: currentPage,
					scale: renderedScale,
					viewportSize,
					selectedDetectionId,
					editingDetectionId: editingId,
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
			scrollDetectionIntoView(overlayEl, id, 'overlay-selected-pulse');
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

	// Leaving Bewerken cancels any in-progress boundary edit — that flow
	// is the one interaction that's mode-specific (entered by click-on-
	// detection in Bewerken) and has no representation in Beoordelen. Text
	// selections and in-progress area draws are left alone: under the
	// hybrid model they're valid in both modes.
	$effect(() => {
		if (mode === 'review') {
			untrack(() => {
				boundaryEdit.cancel();
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
			if (areaDraw.isDrawing) areaDraw.cancel();
			if (boundaryEdit.isEditing) boundaryEdit.cancel();
		});
	});

	// If the detection being edited disappears from the store (e.g. undo
	// removed it) or no longer exists, drop the edit state so we don't
	// render handles over nothing.
	$effect(() => {
		void detections;
		untrack(() => {
			const id = boundaryEdit.editingDetectionId;
			if (id && !detections.some((d) => d.id === id)) {
				boundaryEdit.cancel();
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
		flashOverlays(overlayEl, ids, 'overlay-flash');
	}
</script>

<div
	class="relative overflow-auto rounded-lg border border-gray-200 bg-white"
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
				class:drawing-area={areaDraw.drawingAreaClass}
				onmousedown={(e) => areaDraw.handleStageMouseDown(e)}
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
					onclick={(e) => boundaryEdit.handleTextLayerClick(e)}
				></div>
				<!-- Boundary adjustment draft overlay (#11). Rendered above
				     the text layer so its handles are clickable; the box
				     itself is inert to pointer events, so mousedowns inside
				     the box (but outside a handle) still reach the text
				     layer for Shift/Alt+click word extension. -->
				{#if boundaryEdit.editingBboxes}
					<BoundaryEditOverlay
						editingBboxes={boundaryEdit.editingBboxes}
						{currentPage}
						{scale}
						onHandleMouseDown={(e, boxIndex, dir) =>
							boundaryEdit.handleResizeMouseDown(e, boxIndex, dir)}
						onCommit={() => boundaryEdit.commit()}
						onCancel={() => boundaryEdit.cancel()}
					/>
				{/if}
				{#if areaDraw.drawRect}
					<!-- Live area-draw rectangle (#07). Inert to pointer events so
					     mousemove continues to reach the window listener. -->
					<div
						class="area-draw"
						style="left: {areaDraw.drawRect.x}px; top: {areaDraw.drawRect.y}px; width: {areaDraw.drawRect.w}px; height: {areaDraw.drawRect.h}px;"
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
	/* Text layer is interactive in both modes — a drag produces a manual
	   redaction whether the reviewer is in Beoordelen or Bewerken. The mode
	   only affects what clicking an existing detection does (see
	   handleOverlayClick). */
	.pdf-stage .textLayer {
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
