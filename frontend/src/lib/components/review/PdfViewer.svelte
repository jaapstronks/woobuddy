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

	/**
	 * Lightweight shape for search-and-redact overlays (#09). The PdfViewer
	 * doesn't need the full `SearchOccurrence` — only the id, page, bboxes
	 * and whether it's already-redacted (for the muted style). Declaring a
	 * local interface keeps the viewer's import surface narrow.
	 */
	export interface SearchHighlight {
		id: string;
		page: number;
		bboxes: BoundingBox[];
		alreadyRedacted: boolean;
	}

	/**
	 * Page completeness (#10). The parent passes a sparse map of
	 * page-number → status; any page not in the map is treated as
	 * `unreviewed`. The viewer renders a compact strip of numbered circles
	 * across the toolbar and a corner "Pagina beoordeeld" button on the
	 * current page — both drive the same two callbacks.
	 */
	export type PageReviewStatusValue =
		| 'unreviewed'
		| 'in_progress'
		| 'complete'
		| 'flagged';

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

	function getPageStatus(page: number): PageReviewStatusValue {
		return pageStatuses[page] ?? 'unreviewed';
	}

	function pageStatusLabel(status: PageReviewStatusValue): string {
		switch (status) {
			case 'unreviewed':
				return 'Nog niet beoordeeld';
			case 'in_progress':
				return 'In behandeling';
			case 'complete':
				return 'Beoordeeld';
			case 'flagged':
				return 'Gemarkeerd';
		}
	}

	let canvasEl = $state<HTMLCanvasElement | null>(null);
	let overlayEl = $state<HTMLDivElement | null>(null);
	let searchLayerEl = $state<HTMLDivElement | null>(null);
	let textLayerEl = $state<HTMLDivElement | null>(null);
	let pdfDoc = $state<any>(null);

	const currentPageStatus = $derived(getPageStatus(currentPage));
	const totalPages = $derived(pdfDoc?.numPages ?? 0);
	let rendering = false; // not reactive — just a guard flag
	let viewportSize = { width: 0, height: 0 };
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
	// bboxes are cloned into `editingBboxes` and rendered via Svelte
	// markup with 8 resize handles per box; `drawOverlays` hides the
	// original overlay for the editing detection so the two don't double up.
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
	type HandleDir = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
	const HANDLE_DIRS: HandleDir[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
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
		const updated = applyHandleDelta(
			dragHandle.initialBbox,
			dragHandle.dir,
			dxPt,
			dyPt
		);
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

	// Tier-based overlay styles
	function getOverlayStyle(det: Detection): string {
		const isSelected = det.id === selectedDetectionId;
		// Selected overlays get a thick primary outline placed *outside* the
		// rectangle so the underlying tier styling stays intact and the
		// reviewer can spot the active row at a glance.
		const selectedAccent = isSelected
			? 'outline: 3px solid var(--color-primary); outline-offset: 3px; box-shadow: 0 0 0 6px rgba(27,79,114,0.18);'
			: '';

		// Rejected detections render the same way regardless of tier — they
		// are visible in the export, so the preview must show the underlying
		// text rather than a black box. (Previously Tier 1 short-circuited
		// to a black box even after "Ontlakken", which made the action look
		// like a no-op.)
		if (det.review_status === 'rejected') {
			return `background: rgba(39,174,96,0.10); border: 1px dashed rgba(39,174,96,0.55); ${selectedAccent}`;
		}
		// Area redactions (#07) are always fully opaque black on creation —
		// they are accepted the moment the form is confirmed and have no
		// "review pending" state. Keep the same look as a Tier 1 auto-redact
		// so the reviewer sees exactly what the exported PDF will cover.
		if (det.entity_type === 'area') {
			return `background: rgba(0,0,0,0.85); color: white; ${selectedAccent}`;
		}
		if (det.tier === '1' || det.review_status === 'accepted' || det.review_status === 'auto_accepted') {
			return `background: rgba(0,0,0,0.7); color: white; ${selectedAccent}`;
		}
		if (det.tier === '2') {
			return `background: rgba(243,156,18,0.1); border: 2px solid rgba(243,156,18,0.6); ${selectedAccent}`;
		}
		return `background: rgba(27,79,114,0.05); border-left: 3px solid var(--color-primary); ${selectedAccent}`;
	}

	onMount(async () => {
		// Area-selection listeners live on the window so a drag that leaves
		// the stage mid-gesture still finishes cleanly.
		window.addEventListener('mousemove', handleWindowMouseMove);
		window.addEventListener('mouseup', handleWindowMouseUp);
		window.addEventListener('keydown', handleWindowKeyDown);

		const pdfjsLib = await import('pdfjs-dist');
		pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
			'pdfjs-dist/build/pdf.worker.mjs',
			import.meta.url
		).toString();

		// Client-first: PDF comes from the in-memory ArrayBuffer only.
		// .slice(0) copies the buffer so pdf.js Worker transfer doesn't detach the original.
		if (!pdfData) return;
		const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(pdfData.slice(0)) });
		pdfDoc = await loadingTask.promise;
	});

	onDestroy(() => {
		window.removeEventListener('mousemove', handleWindowMouseMove);
		window.removeEventListener('mouseup', handleWindowMouseUp);
		window.removeEventListener('keydown', handleWindowKeyDown);
	});

	async function renderPdf(pageNum: number) {
		if (!pdfDoc || !canvasEl || rendering) return;
		rendering = true;

		try {
			const page = await pdfDoc.getPage(pageNum + 1);
			// Report the unscaled page size so the parent can compute fit-to-width /
			// fit-to-page scales. Done before applying `scale` so the math is
			// independent of whatever scale the parent currently has.
			const baseViewport = page.getViewport({ scale: 1 });
			onPageNaturalSize?.({ width: baseViewport.width, height: baseViewport.height });
			const viewport = page.getViewport({ scale });
			viewportSize = { width: viewport.width, height: viewport.height };

			canvasEl.width = viewport.width;
			canvasEl.height = viewport.height;

			const ctx = canvasEl.getContext('2d')!;
			await page.render({ canvasContext: ctx, viewport }).promise;

			await renderTextLayer(page, viewport);
		} finally {
			rendering = false;
		}
	}

	async function renderTextLayer(page: any, viewport: any) {
		if (!textLayerEl) return;
		// Cancel any previous render — switching pages quickly can leave a
		// stale TextLayer half-painted if we don't explicitly abort.
		currentTextLayer?.cancel();
		textLayerEl.innerHTML = '';
		textLayerEl.style.width = `${viewport.width}px`;
		textLayerEl.style.height = `${viewport.height}px`;
		// pdf.js expects this CSS var to equal 1x scale so it can size glyphs.
		textLayerEl.style.setProperty('--scale-factor', String(scale));

		const pdfjsLib = await import('pdfjs-dist');
		const textContent = await page.getTextContent();
		const textLayer = new pdfjsLib.TextLayer({
			textContentSource: textContent,
			container: textLayerEl,
			viewport
		});
		currentTextLayer = textLayer;
		try {
			await textLayer.render();
		} catch {
			// pdf.js throws on cancel — nothing to do.
		}
	}

	/**
	 * Draw search-and-redact highlights (#09) on their own layer, above the
	 * canvas but below the detection overlay and the text layer. A distinct
	 * yellow color separates them from detection rectangles so the reviewer
	 * immediately sees the difference between "detected" and "search hit".
	 * Already-redacted hits render with a muted style so they don't compete
	 * visually with the still-actionable matches.
	 */
	function drawSearchHighlights(pageNum: number) {
		if (!searchLayerEl) return;
		searchLayerEl.innerHTML = '';
		searchLayerEl.style.width = `${viewportSize.width}px`;
		searchLayerEl.style.height = `${viewportSize.height}px`;

		for (const hit of searchHighlights) {
			for (const bbox of hit.bboxes) {
				if (bbox.page !== pageNum) continue;
				const el = document.createElement('div');
				const x = bbox.x0 * scale;
				const y = bbox.y0 * scale;
				const w = (bbox.x1 - bbox.x0) * scale;
				const h = (bbox.y1 - bbox.y0) * scale;
				el.className = 'search-hit';
				if (hit.alreadyRedacted) el.classList.add('search-hit-muted');
				if (hit.id === focusedSearchId) el.classList.add('search-hit-focused');
				el.style.cssText += `left:${x}px;top:${y}px;width:${w}px;height:${h}px;`;
				el.dataset.searchHitId = hit.id;
				searchLayerEl.appendChild(el);
			}
		}
	}

	function drawOverlays(pageNum: number) {
		if (!overlayEl) return;

		overlayEl.innerHTML = '';
		overlayEl.style.width = `${viewportSize.width}px`;
		overlayEl.style.height = `${viewportSize.height}px`;

		for (const det of detections) {
			if (!det.bounding_boxes) continue;
			// The detection currently being boundary-edited is rendered via
			// the Svelte markup block below (with handles + live draft
			// bboxes), not here. Skip it to avoid a ghost overlay beneath
			// the draft.
			if (det.id === editingDetectionId) continue;
			const bboxes = det.bounding_boxes;
			const isSplitTarget = splitPendingId !== null && splitPendingId === det.id;
			const isMergeStaged = mergeStagingIds.includes(det.id);
			for (let bboxIdx = 0; bboxIdx < bboxes.length; bboxIdx++) {
				const bbox = bboxes[bboxIdx];
				if (bbox.page !== pageNum) continue;

				const el = document.createElement('div');
				const x = bbox.x0 * scale;
				const y = bbox.y0 * scale;
				const w = (bbox.x1 - bbox.x0) * scale;
				const h = (bbox.y1 - bbox.y0) * scale;

				// Split-target and merge-staged detections get stacked visual
				// cues on top of the tier-based style — a dashed amber outline
				// for "click here to split" and a solid accent outline for
				// "queued for merge".
				let extraStyle = '';
				if (isSplitTarget) {
					extraStyle += 'outline: 2px dashed rgba(243,156,18,0.9); outline-offset: 2px; cursor: crosshair;';
				} else if (isMergeStaged) {
					extraStyle += 'outline: 2px solid rgba(27,79,114,0.8); outline-offset: 2px;';
				}

				el.style.cssText = `
					position: absolute;
					left: ${x}px; top: ${y}px;
					width: ${w}px; height: ${h}px;
					cursor: pointer; pointer-events: auto;
					border-radius: 2px;
					${getOverlayStyle(det)}
					${extraStyle}
				`;
				el.dataset.overlay = 'detection';
				el.dataset.detectionId = det.id;
				el.dataset.bboxIndex = String(bboxIdx);

				if ((det.tier === '1' || det.entity_type === 'area') && det.woo_article) {
					el.innerHTML = `<span style="font-size:8px;padding:1px 3px;">${det.woo_article}</span>`;
				}

				el.addEventListener('click', (e) => {
					e.stopPropagation();
					// #18 — split pending: clicking the target detection's
					// bbox reports a PDF-space click position instead of the
					// usual boundary-edit entry. Fires only for the pending
					// detection; clicks on other detections fall through to
					// their normal behavior.
					if (isSplitTarget && onSplitPointClick && stageEl) {
						const stageRect = stageEl.getBoundingClientRect();
						const pdfX = (e.clientX - stageRect.left) / scale;
						const pdfY = (e.clientY - stageRect.top) / scale;
						onSplitPointClick({
							detectionId: det.id,
							bboxIndex: bboxIdx,
							pdfX,
							pdfY
						});
						return;
					}
					// Edit mode: clicking an existing detection enters the
					// boundary-edit flow instead of just highlighting it.
					// Review mode keeps the classic select-for-sidebar
					// behavior.
					if (mode === 'edit') {
						enterBoundaryEdit(det.id);
					} else {
						onSelectDetection(det.id);
					}
				});
				overlayEl.appendChild(el);
			}
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
			if (
				t?.tagName === 'INPUT' ||
				t?.tagName === 'TEXTAREA' ||
				t?.isContentEditable
			) {
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
		if (pdfDoc) {
			untrack(() => drawOverlays(currentPage));
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
		void scale;
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
	// changes. Kept separate from `drawOverlays` so typing in the search box
	// doesn't force a detection re-render.
	$effect(() => {
		void searchHighlights;
		void focusedSearchId;
		void currentPage;
		void scale;
		if (pdfDoc) {
			untrack(() => drawSearchHighlights(currentPage));
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
				el.addEventListener(
					'animationend',
					() => el.classList.remove('overlay-flash'),
					{ once: true }
				);
			}
		}
	}
</script>

<div
	class="relative overflow-auto rounded-lg border border-gray-200 bg-white"
	class:edit-mode={mode === 'edit'}
>
	<!-- Toolbar: mode toggle + page navigation -->
	<div
		class="sticky top-0 z-10 flex items-center justify-between gap-3 border-b bg-white/95 px-4 py-2 backdrop-blur-sm"
		class:toolbar-edit={mode === 'edit'}
	>
		<div class="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5" role="group" aria-label="Modus">
			<button
				type="button"
				class="mode-btn"
				class:mode-btn-active={mode === 'review'}
				aria-pressed={mode === 'review'}
				title="Beoordelen (M)"
				onclick={() => onModeChange('review')}
			>
				Beoordelen
			</button>
			<button
				type="button"
				class="mode-btn"
				class:mode-btn-active={mode === 'edit'}
				aria-pressed={mode === 'edit'}
				title="Bewerken (M)"
				onclick={() => onModeChange('edit')}
			>
				Bewerken
			</button>
		</div>

		<div class="flex items-center gap-3">
			<button
				class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
				disabled={currentPage <= 0}
				onclick={() => onPageChange(currentPage - 1)}
			>
				&larr; Vorige
			</button>
			<span class="flex items-center gap-1.5 text-sm text-neutral">
				<!-- Inline indicator beside the page counter so the reviewer
				     always sees the current page's status, regardless of
				     whether the page strip is scrolled into view. -->
				<span
					class="page-status-dot"
					class:status-unreviewed={currentPageStatus === 'unreviewed'}
					class:status-in-progress={currentPageStatus === 'in_progress'}
					class:status-complete={currentPageStatus === 'complete'}
					class:status-flagged={currentPageStatus === 'flagged'}
					aria-hidden="true"
				></span>
				{currentPage + 1} / {pdfDoc?.numPages ?? '...'}
			</span>
			<button
				class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
				disabled={!pdfDoc || currentPage >= pdfDoc.numPages - 1}
				onclick={() => onPageChange(currentPage + 1)}
			>
				Volgende &rarr;
			</button>
		</div>
	</div>

	<!-- Page strip (#10). A horizontally-scrolling row of numbered circles,
	     one per page, showing per-page review status at a glance. The active
	     page gets an outlined ring so the reviewer can find their place even
	     in a long document. -->
	{#if pdfDoc && totalPages > 1}
		<div class="page-strip flex items-center gap-1 overflow-x-auto border-b border-gray-200 bg-white px-4 py-2">
			{#each Array.from({ length: totalPages }, (_, i) => i) as p (p)}
				{@const st = getPageStatus(p)}
				<button
					type="button"
					class="page-chip"
					class:chip-unreviewed={st === 'unreviewed'}
					class:chip-in-progress={st === 'in_progress'}
					class:chip-complete={st === 'complete'}
					class:chip-flagged={st === 'flagged'}
					class:chip-current={p === currentPage}
					title={`Pagina ${p + 1} — ${pageStatusLabel(st)}`}
					onclick={() => onPageChange(p)}
				>
					{#if st === 'complete'}
						&#10003;
					{:else if st === 'flagged'}
						&#9873;
					{:else}
						{p + 1}
					{/if}
				</button>
			{/each}
		</div>
	{/if}

	<!-- PDF canvas + overlay + text layer -->
	<div class="relative flex justify-center p-4">
		{#if !pdfDoc}
			<div class="flex h-96 items-center justify-center text-neutral">
				PDF laden...
			</div>
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
					{#each editingBboxes as b, i (i)}
						{#if b.page === currentPage}
							<div
								class="edit-box"
								style="left: {b.x0 * scale}px; top: {b.y0 * scale}px; width: {(b.x1 - b.x0) * scale}px; height: {(b.y1 - b.y0) * scale}px;"
							>
								{#each HANDLE_DIRS as dir (dir)}
									<button
										type="button"
										class="edit-handle handle-{dir}"
										aria-label="Grens aanpassen ({dir})"
										onmousedown={(e) => handleResizeMouseDown(e, i, dir)}
									></button>
								{/each}
							</div>
						{/if}
					{/each}
					{@const primary = editingBboxes.find((b) => b.page === currentPage)}
					{#if primary}
						<div
							class="edit-toolbar"
							style="left: {primary.x0 * scale}px; top: {Math.max(0, primary.y0 * scale - 34)}px;"
						>
							<button
								type="button"
								class="edit-toolbar-btn edit-toolbar-save"
								title="Opslaan (Enter)"
								onclick={commitBoundaryEdit}
							>
								Opslaan
							</button>
							<button
								type="button"
								class="edit-toolbar-btn"
								title="Annuleren (Escape)"
								onclick={cancelBoundaryEdit}
							>
								Annuleren
							</button>
						</div>
					{/if}
				{/if}
				{#if drawRect}
					<!-- Live area-draw rectangle (#07). Inert to pointer events so
					     mousemove continues to reach the window listener. -->
					<div
						class="area-draw"
						style="left: {drawRect.x}px; top: {drawRect.y}px; width: {drawRect.w}px; height: {drawRect.h}px;"
					></div>
				{/if}
				<!-- Floating per-page completeness actions (#10). Anchored to
				     the top-right of the rendered page so it follows zoom and
				     stays out of the bottom where pagination controls live. -->
				{#if onMarkPageReviewed || onFlagPage}
					<div class="page-review-actions">
						{#if currentPageStatus === 'complete'}
							<button
								type="button"
								class="page-action-btn page-action-done"
								title="Beoordeling ongedaan maken"
								onclick={() => onMarkPageReviewed?.(currentPage)}
							>
								&#10003; Beoordeeld
							</button>
						{:else}
							<button
								type="button"
								class="page-action-btn page-action-mark"
								title="Pagina beoordeeld (P)"
								onclick={() => onMarkPageReviewed?.(currentPage)}
							>
								Pagina beoordeeld
							</button>
						{/if}
						<button
							type="button"
							class="page-action-btn"
							class:page-action-flagged={currentPageStatus === 'flagged'}
							title="Later terugkomen (F)"
							onclick={() => onFlagPage?.(currentPage)}
						>
							&#9873;
						</button>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	.edit-mode {
		border-top: 2px solid var(--color-primary, #1b4f72);
	}
	.toolbar-edit {
		box-shadow: inset 0 2px 0 0 var(--color-primary, #1b4f72);
	}
	.mode-btn {
		padding: 0.25rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: #4b5563;
		border-radius: 0.25rem;
		transition: background-color 120ms, color 120ms;
	}
	.mode-btn:hover {
		background-color: rgba(0, 0, 0, 0.04);
	}
	.mode-btn-active {
		background-color: white;
		color: var(--color-primary, #1b4f72);
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
		/* #23 — brief background flash when the toggle flips. The
		   animation runs once each time the element acquires the
		   active class, then settles back to white. */
		animation: mode-toggle-pulse 220ms ease-out;
	}
	@media (prefers-reduced-motion: reduce) {
		.mode-btn,
		.mode-btn-active {
			animation: none;
			transition: none;
		}
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

	/* Page completeness (#10). Compact strip of numbered circles, one per
	   page, showing per-page review status. The strip scrolls horizontally
	   on long documents so it never forces the toolbar to wrap. */
	.page-strip {
		scrollbar-width: thin;
	}
	.page-chip {
		flex: 0 0 auto;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.75rem;
		height: 1.75rem;
		padding: 0 0.375rem;
		border-radius: 9999px;
		border: 1px solid #d1d5db;
		background: white;
		font-size: 0.7rem;
		font-weight: 500;
		color: #4b5563;
		transition: transform 120ms, box-shadow 120ms, background-color 120ms;
	}
	.page-chip:hover {
		transform: translateY(-1px);
	}
	.chip-unreviewed {
		background: white;
		color: #6b7280;
	}
	.chip-in-progress {
		background: #fef3c7;
		border-color: #f59e0b;
		color: #78350f;
	}
	.chip-complete {
		background: #10b981;
		border-color: #059669;
		color: white;
	}
	.chip-flagged {
		background: #fbbf24;
		border-color: #d97706;
		color: #78350f;
	}
	.chip-current {
		box-shadow: 0 0 0 2px var(--color-primary, #1b4f72);
	}

	/* Inline dot beside the toolbar's page counter — mirrors the chip
	   colors so the reviewer recognises the state language. */
	.page-status-dot {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 9999px;
		border: 1px solid #d1d5db;
		background: white;
	}
	.page-status-dot.status-in-progress {
		background: #f59e0b;
		border-color: #b45309;
	}
	.page-status-dot.status-complete {
		background: #10b981;
		border-color: #059669;
	}
	.page-status-dot.status-flagged {
		background: #fbbf24;
		border-color: #d97706;
	}

	/* Floating corner button — stacked above the PDF canvas on the top
	   right of the current page. Kept small so it doesn't cover document
	   content; the page strip is the primary overview. */
	.page-review-actions {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		display: flex;
		gap: 0.25rem;
		z-index: 4;
	}
	.page-action-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.3rem 0.6rem;
		border-radius: 9999px;
		border: 1px solid rgba(0, 0, 0, 0.08);
		background: rgba(255, 255, 255, 0.92);
		backdrop-filter: blur(4px);
		font-size: 0.75rem;
		font-weight: 500;
		color: #374151;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
		cursor: pointer;
		transition: background-color 120ms, transform 120ms;
	}
	.page-action-btn:hover {
		background: white;
		transform: translateY(-1px);
	}
	.page-action-mark:hover {
		background: #ecfdf5;
		color: #065f46;
		border-color: #10b981;
	}
	.page-action-done {
		background: #10b981;
		color: white;
		border-color: #059669;
	}
	.page-action-done:hover {
		background: #059669;
	}
	.page-action-flagged {
		background: #fbbf24;
		color: #78350f;
		border-color: #d97706;
	}

	/* Boundary adjustment (#11). The draft box sits above the text layer
	   and above detection overlays so its handles are always hit-testable.
	   The box itself is inert (pointer-events: none) — only the handles
	   capture mouse events, so Shift/Alt+click on words underneath the
	   box (for text-based extend/shrink) still reaches the text layer. */
	.edit-box {
		position: absolute;
		z-index: 5;
		pointer-events: none;
		border: 2px solid var(--color-primary, #1b4f72);
		background: rgba(27, 79, 114, 0.08);
		border-radius: 2px;
	}
	.edit-handle {
		position: absolute;
		width: 10px;
		height: 10px;
		padding: 0;
		margin: 0;
		background: white;
		border: 2px solid var(--color-primary, #1b4f72);
		border-radius: 1px;
		pointer-events: auto;
		box-sizing: border-box;
	}
	/* Corner handles. Each handle is nudged so its center sits exactly on
	   the box corner (half the handle size = 5px). */
	.handle-nw { left: -6px; top: -6px; cursor: nwse-resize; }
	.handle-ne { right: -6px; top: -6px; cursor: nesw-resize; }
	.handle-se { right: -6px; bottom: -6px; cursor: nwse-resize; }
	.handle-sw { left: -6px; bottom: -6px; cursor: nesw-resize; }
	/* Edge handles — positioned on the midpoint of each edge. */
	.handle-n {
		left: 50%;
		top: -6px;
		transform: translateX(-50%);
		cursor: ns-resize;
	}
	.handle-s {
		left: 50%;
		bottom: -6px;
		transform: translateX(-50%);
		cursor: ns-resize;
	}
	.handle-e {
		right: -6px;
		top: 50%;
		transform: translateY(-50%);
		cursor: ew-resize;
	}
	.handle-w {
		left: -6px;
		top: 50%;
		transform: translateY(-50%);
		cursor: ew-resize;
	}
	/* Floating Save/Cancel toolbar above the primary draft bbox. */
	.edit-toolbar {
		position: absolute;
		z-index: 6;
		display: inline-flex;
		gap: 0.25rem;
		padding: 0.25rem;
		border-radius: 0.375rem;
		background: white;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
	}
	.edit-toolbar-btn {
		padding: 0.25rem 0.6rem;
		font-size: 0.72rem;
		font-weight: 600;
		border-radius: 0.25rem;
		border: 1px solid #d1d5db;
		background: white;
		color: #374151;
		cursor: pointer;
	}
	.edit-toolbar-btn:hover {
		background: #f3f4f6;
	}
	.edit-toolbar-save {
		background: var(--color-primary, #1b4f72);
		color: white;
		border-color: var(--color-primary, #1b4f72);
	}
	.edit-toolbar-save:hover {
		background: #143a57;
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
			box-shadow: 0 0 0 0 rgba(27, 79, 114, 0.7), 0 0 0 0 rgba(27, 79, 114, 0.45);
		}
		60% {
			box-shadow: 0 0 0 6px rgba(27, 79, 114, 0.0), 0 0 0 14px rgba(27, 79, 114, 0.18);
		}
		100% {
			box-shadow: 0 0 0 6px rgba(27, 79, 114, 0.18);
		}
	}
</style>
