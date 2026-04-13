/**
 * Review session store — manages review page state like current document,
 * PDF zoom level, sidebar visibility, and keyboard shortcut state.
 */

import { getDocument } from '$lib/api/client';
import type { Document } from '$lib/types';

export type ReviewMode = 'review' | 'edit';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentDocument = $state<Document | null>(null);
let currentPage = $state(0);
let totalPages = $state(0);
let pdfScale = $state(1.0);
let sidebarOpen = $state(true);
let mode = $state<ReviewMode>('review');
let loading = $state(false);
let error = $state<string | null>(null);

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

function setScale(scale: number) {
	pdfScale = Math.max(0.25, Math.min(4.0, scale));
}

function zoomIn() {
	setScale(pdfScale + 0.25);
}

function zoomOut() {
	setScale(pdfScale - 0.25);
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
	zoomIn,
	zoomOut,
	toggleSidebar,
	setMode,
	toggleMode
};
