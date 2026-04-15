/**
 * Review session store — manages review page state like current document,
 * PDF zoom level, sidebar visibility, and keyboard shortcut state.
 */

import { getDocument } from '$lib/api/client';
import type { Document } from '$lib/types';

export type ReviewMode = 'review' | 'edit';
export type PdfFitMode = 'width' | 'page' | null;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocument = $state<Document | null>(null);
let currentPage = $state(0);
let totalPages = $state(0);
// `pdfScale` is the live scale fed to PdfViewer. It can be driven either by
// the reviewer (via zoomIn/zoomOut/setScale → fit mode cleared) or
// programmatically by `applyFit` when a fit mode is active. Default starts at
// `'width'` so the first page render fills the available column instead of
// rendering at the PDF's native 1pt-per-px size, which is hard to read on
// any modern display.
let pdfScale = $state(1.25);
let pdfFitMode = $state<PdfFitMode>('width');
let pdfPageNaturalSize = $state<{ width: number; height: number } | null>(null);
let sidebarOpen = $state(true);
let mode = $state<ReviewMode>('review');
let loading = $state(false);
let error = $state<string | null>(null);

const MIN_SCALE = 0.25;
const MAX_SCALE = 4.0;
// Padding inside the PDF scroll container — keep in sync with the `p-4` on
// the wrapper in `+page.svelte` (16px each side). Used so fit-to-width leaves
// a gap rather than touching the edges.
const FIT_PADDING = 32;

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function loadDocument(documentId: string) {
	loading = true;
	error = null;
	try {
		currentDocument = await getDocument(documentId);
		totalPages = currentDocument.page_count;
		currentPage = 0;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Document laden mislukt';
	} finally {
		loading = false;
	}
}

function setPage(page: number) {
	if (page >= 0 && page < totalPages) {
		currentPage = page;
	}
}

function clampScale(scale: number) {
	return Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
}

/** User-initiated zoom — drops any active fit mode. */
function setScale(scale: number) {
	pdfFitMode = null;
	pdfScale = clampScale(scale);
}

function zoomIn() {
	setScale(pdfScale + 0.25);
}

function zoomOut() {
	setScale(pdfScale - 0.25);
}

function setFitMode(next: PdfFitMode) {
	pdfFitMode = next;
}

function setPageNaturalSize(size: { width: number; height: number } | null) {
	pdfPageNaturalSize = size;
}

/**
 * Recompute `pdfScale` from the current fit mode and the available container
 * dimensions. Called by the review page on container resize and whenever the
 * natural page size becomes known. No-op when no fit mode is active or the
 * natural size hasn't been reported yet.
 */
function applyFit(containerWidth: number, containerHeight: number) {
	if (!pdfFitMode || !pdfPageNaturalSize) return;
	const availW = Math.max(0, containerWidth - FIT_PADDING);
	const availH = Math.max(0, containerHeight - FIT_PADDING);
	if (availW <= 0 || availH <= 0) return;

	const widthScale = availW / pdfPageNaturalSize.width;
	const heightScale = availH / pdfPageNaturalSize.height;
	const next = pdfFitMode === 'width' ? widthScale : Math.min(widthScale, heightScale);
	pdfScale = clampScale(next);
}

function toggleSidebar() {
	sidebarOpen = !sidebarOpen;
}

function setMode(next: ReviewMode) {
	mode = next;
}

function toggleMode() {
	mode = mode === 'review' ? 'edit' : 'review';
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const reviewStore = {
	get document() {
		return currentDocument;
	},
	get currentPage() {
		return currentPage;
	},
	get totalPages() {
		return totalPages;
	},
	get pdfScale() {
		return pdfScale;
	},
	get pdfFitMode() {
		return pdfFitMode;
	},
	get pdfPageNaturalSize() {
		return pdfPageNaturalSize;
	},
	get sidebarOpen() {
		return sidebarOpen;
	},
	get mode() {
		return mode;
	},
	get loading() {
		return loading;
	},
	get error() {
		return error;
	},
	loadDocument,
	setPage,
	setScale,
	zoomIn,
	zoomOut,
	setFitMode,
	setPageNaturalSize,
	applyFit,
	toggleSidebar,
	setMode,
	toggleMode
};
