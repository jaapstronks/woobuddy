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
		stageEl?: HTMLDivElement | null;
		/** Search-and-redact highlights for the current document (#09). */
		searchHighlights?: SearchHighlight[];
		/** Id of the highlight the reviewer just clicked — gets the focused style. */
		focusedSearchId?: string | null;
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
		stageEl = $bindable(null),
		searchHighlights = [],
		focusedSearchId = null
	}: Props = $props();

	let canvasEl = $state<HTMLCanvasElement | null>(null);
	let overlayEl = $state<HTMLDivElement | null>(null);
	let searchLayerEl = $state<HTMLDivElement | null>(null);
	let textLayerEl = $state<HTMLDivElement | null>(null);
	let pdfDoc = $state<any>(null);
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

	// Tier-based overlay styles
	function getOverlayStyle(det: Detection): string {
		const isSelected = det.id === selectedDetectionId;
		const border = isSelected ? 'border: 2px solid var(--color-primary);' : '';

		// Area redactions (#07) are always fully opaque black on creation —
		// they are accepted the moment the form is confirmed and have no
		// "review pending" state. Keep the same look as a Tier 1 auto-redact
		// so the reviewer sees exactly what the exported PDF will cover.
		if (det.entity_type === 'area') {
			return `background: rgba(0,0,0,0.85); color: white; ${border}`;
		}
		if (det.tier === '1' || det.review_status === 'accepted' || det.review_status === 'auto_accepted') {
			return `background: rgba(0,0,0,0.7); color: white; ${border}`;
		}
		if (det.review_status === 'rejected') {
			return `background: rgba(39,174,96,0.08); border: 1px dashed rgba(39,174,96,0.4); ${border}`;
		}
		if (det.tier === '2') {
			return `background: rgba(243,156,18,0.1); border: 2px solid rgba(243,156,18,0.6); ${border}`;
		}
		return `background: rgba(27,79,114,0.05); border-left: 3px solid var(--color-primary); ${border}`;
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
			for (const bbox of det.bounding_boxes) {
				if (bbox.page !== pageNum) continue;

				const el = document.createElement('div');
				const x = bbox.x0 * scale;
				const y = bbox.y0 * scale;
				const w = (bbox.x1 - bbox.x0) * scale;
				const h = (bbox.y1 - bbox.y0) * scale;

				el.style.cssText = `
					position: absolute;
					left: ${x}px; top: ${y}px;
					width: ${w}px; height: ${h}px;
					cursor: pointer; pointer-events: auto;
					border-radius: 2px;
					${getOverlayStyle(det)}
				`;
				el.dataset.overlay = 'detection';
				el.dataset.detectionId = det.id;

				if ((det.tier === '1' || det.entity_type === 'area') && det.woo_article) {
					el.innerHTML = `<span style="font-size:8px;padding:1px 3px;">${det.woo_article}</span>`;
				}

				el.addEventListener('click', (e) => {
					e.stopPropagation();
					onSelectDetection(det.id);
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

	// Draw overlays when detections, selection, or page changes
	$effect(() => {
		void detections;
		void selectedDetectionId;
		void currentPage;
		if (pdfDoc) {
			untrack(() => drawOverlays(currentPage));
		}
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
	// any area draw that was mid-gesture.
	$effect(() => {
		if (mode === 'review') {
			untrack(() => {
				window.getSelection()?.removeAllRanges();
				cancelAreaDraw();
				onManualSelectionCleared?.();
			});
		}
	});

	// Changing pages mid-draw would strand the rectangle on a page it wasn't
	// drawn on — cancel cleanly instead.
	$effect(() => {
		void currentPage;
		untrack(() => {
			if (isDrawingArea) cancelAreaDraw();
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
			<span class="text-sm text-neutral">{currentPage + 1} / {pdfDoc?.numPages ?? '...'}</span>
			<button
				class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
				disabled={!pdfDoc || currentPage >= pdfDoc.numPages - 1}
				onclick={() => onPageChange(currentPage + 1)}
			>
				Volgende &rarr;
			</button>
		</div>
	</div>

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
				></div>
				{#if drawRect}
					<!-- Live area-draw rectangle (#07). Inert to pointer events so
					     mousemove continues to reach the window listener. -->
					<div
						class="area-draw"
						style="left: {drawRect.x}px; top: {drawRect.y}px; width: {drawRect.w}px; height: {drawRect.h}px;"
					></div>
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

	/* Detection overlays: interactive in review mode, inert in edit mode so
	   they don't eat mousedown events from text selection. */
	.overlay {
		pointer-events: none;
	}
	.pdf-stage:not(.edit-active) .overlay :global(> *) {
		pointer-events: auto;
	}
	.pdf-stage.edit-active .overlay :global(> *) {
		pointer-events: none;
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
</style>
