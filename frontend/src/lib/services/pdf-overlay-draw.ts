/**
 * Imperative DOM-builders for the PdfViewer's overlay layers.
 *
 * Two independent layers, each rebuilt from scratch on every relevant change:
 *  1. `drawDetectionOverlays` — the clickable detection rectangles, with
 *     tier/selection styling and split/merge visual cues.
 *  2. `drawSearchHighlights` — the search-and-redact yellow hits (#09).
 *
 * Both functions own *only* DOM construction. Event wiring and the parent
 * effects that decide *when* to redraw stay in PdfViewer.svelte. Pulled out of
 * the component so the reactive `$effect`s can be one-liners and so the
 * style/branching logic for detection rectangles is testable in isolation.
 */

import type { BoundingBox, Detection } from '$lib/types';
import { isAcceptedRedaction } from '$lib/utils/review-status';

/**
 * Cosmetic slack applied to detection and search overlays at draw time.
 * Stored bboxes come from the backend's proportional-width narrowing inside
 * a pdf.js text item — for variable-width fonts that's approximate, so
 * rectangles can land a glyph-edge short of the word. Growing every rectangle
 * by 1 CSS pixel on each side hides that slop without affecting the stored
 * data; export still uses the unpadded bbox.
 */
const OVERLAY_VISUAL_PAD_PX = 1;

export interface SearchHighlight {
	id: string;
	page: number;
	bboxes: BoundingBox[];
	alreadyRedacted: boolean;
}

interface DetectionOverlayOptions {
	overlayEl: HTMLDivElement;
	detections: Detection[];
	pageNum: number;
	scale: number;
	viewportSize: { width: number; height: number };
	selectedDetectionId: string | null;
	/** Detection currently under boundary edit — skipped because Svelte renders the draft. */
	editingDetectionId: string | null;
	splitPendingId: string | null;
	mergeStagingIds: string[];
	/**
	 * Click handler. PdfViewer wraps it to dispatch boundary-edit entry,
	 * split-point clicks, or plain selection depending on mode/state.
	 */
	onOverlayClick: (event: MouseEvent, detection: Detection, bboxIndex: number) => void;
}

export function drawDetectionOverlays(opts: DetectionOverlayOptions): void {
	const {
		overlayEl,
		detections,
		pageNum,
		scale,
		viewportSize,
		editingDetectionId,
		splitPendingId,
		mergeStagingIds,
		selectedDetectionId,
		onOverlayClick
	} = opts;

	overlayEl.innerHTML = '';
	overlayEl.style.width = `${viewportSize.width}px`;
	overlayEl.style.height = `${viewportSize.height}px`;

	for (const det of detections) {
		if (!det.bounding_boxes) continue;
		// The detection currently being boundary-edited is rendered via
		// the Svelte markup block in PdfViewer (with handles + live draft
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
			const x = bbox.x0 * scale - OVERLAY_VISUAL_PAD_PX;
			const y = bbox.y0 * scale - OVERLAY_VISUAL_PAD_PX;
			const w = (bbox.x1 - bbox.x0) * scale + OVERLAY_VISUAL_PAD_PX * 2;
			const h = (bbox.y1 - bbox.y0) * scale + OVERLAY_VISUAL_PAD_PX * 2;

			// Split-target and merge-staged detections get stacked visual
			// cues on top of the tier-based style — a dashed amber outline
			// for "click here to split" and a solid accent outline for
			// "queued for merge".
			let extraStyle = '';
			if (isSplitTarget) {
				extraStyle +=
					'outline: 2px dashed rgba(243,156,18,0.9); outline-offset: 2px; cursor: crosshair;';
			} else if (isMergeStaged) {
				extraStyle += 'outline: 2px solid rgba(27,79,114,0.8); outline-offset: 2px;';
			}

			el.style.cssText = `
				position: absolute;
				left: ${x}px; top: ${y}px;
				width: ${w}px; height: ${h}px;
				cursor: pointer; pointer-events: auto;
				border-radius: 2px;
				${getOverlayStyle(det, selectedDetectionId)}
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
				onOverlayClick(e, det, bboxIdx);
			});
			overlayEl.appendChild(el);
		}
	}
}

interface SearchHighlightOptions {
	searchLayerEl: HTMLDivElement;
	searchHighlights: SearchHighlight[];
	pageNum: number;
	scale: number;
	viewportSize: { width: number; height: number };
	focusedSearchId: string | null;
}

/**
 * Draw search-and-redact highlights (#09) on their own layer, above the
 * canvas but below the detection overlay and the text layer. A distinct
 * yellow color separates them from detection rectangles so the reviewer
 * immediately sees the difference between "detected" and "search hit".
 * Already-redacted hits render with a muted style so they don't compete
 * visually with the still-actionable matches.
 */
export function drawSearchHighlights(opts: SearchHighlightOptions): void {
	const { searchLayerEl, searchHighlights, pageNum, scale, viewportSize, focusedSearchId } = opts;

	searchLayerEl.innerHTML = '';
	searchLayerEl.style.width = `${viewportSize.width}px`;
	searchLayerEl.style.height = `${viewportSize.height}px`;

	for (const hit of searchHighlights) {
		for (const bbox of hit.bboxes) {
			if (bbox.page !== pageNum) continue;
			const el = document.createElement('div');
			const x = bbox.x0 * scale - OVERLAY_VISUAL_PAD_PX;
			const y = bbox.y0 * scale - OVERLAY_VISUAL_PAD_PX;
			const w = (bbox.x1 - bbox.x0) * scale + OVERLAY_VISUAL_PAD_PX * 2;
			const h = (bbox.y1 - bbox.y0) * scale + OVERLAY_VISUAL_PAD_PX * 2;
			el.className = 'search-hit';
			if (hit.alreadyRedacted) el.classList.add('search-hit-muted');
			if (hit.id === focusedSearchId) el.classList.add('search-hit-focused');
			el.style.cssText += `left:${x}px;top:${y}px;width:${w}px;height:${h}px;`;
			el.dataset.searchHitId = hit.id;
			searchLayerEl.appendChild(el);
		}
	}
}

/**
 * Tier-based overlay styles. Exported for unit testing — the branching is
 * subtle enough that it benefits from explicit test coverage rather than
 * being buried inside a draw loop.
 */
export function getOverlayStyle(det: Detection, selectedDetectionId: string | null): string {
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
	if (det.tier === '1' || isAcceptedRedaction(det.review_status)) {
		return `background: rgba(0,0,0,0.7); color: white; ${selectedAccent}`;
	}
	if (det.tier === '2') {
		return `background: rgba(243,156,18,0.1); border: 2px solid rgba(243,156,18,0.6); ${selectedAccent}`;
	}
	return `background: rgba(27,79,114,0.05); border-left: 3px solid var(--color-primary); ${selectedAccent}`;
}
