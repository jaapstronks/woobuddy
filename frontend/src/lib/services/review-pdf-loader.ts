/**
 * Loading helpers for the review page's PDF column.
 *
 * Extracted from `/review/[docId]/+page.svelte` so the IndexedDB ↔
 * pdf.js ↔ detection-store plumbing can be reused and tested without
 * a component harness. The page component still owns the reactive
 * variables (`pdfData`, `needsPdf`); these helpers just wrap the
 * async steps around those assignments.
 */

import { getPdf, storePdf } from '$lib/services/pdf-store';
import { extractText, loadPdfDocument, PdfError } from '$lib/services/pdf-text-extractor';
import { getExtraction } from '$lib/services/extraction-store';
import { detectionStore } from '$lib/stores/detections.svelte';

export interface PdfLoadResult {
	/** The bytes from IndexedDB, or null if we didn't find a stored copy. */
	pdfBytes: ArrayBuffer | null;
}

/**
 * Look up the stored PDF bytes for this document and, if present,
 * re-extract the text layer (or pull the cached OCR extraction for
 * scanned docs) so the review sidebar's text-layer features work on
 * reload. Detections are loaded regardless.
 *
 * Returns the bytes so the page can wire them into the PdfViewer, plus
 * a flag for whether a file-upload fallback is needed.
 */
export async function loadPdfAndDetections(documentId: string): Promise<PdfLoadResult> {
	const stored = await getPdf(documentId);
	const pdfBytes = stored?.pdfBytes ?? null;
	if (pdfBytes) {
		await hydrateExtractionText(documentId, pdfBytes);
	}
	await detectionStore.load(documentId);
	return { pdfBytes };
}

/**
 * Store a freshly uploaded PDF, hydrate the extraction cache, and
 * reload detections. Used by the "PDF niet gevonden" recovery flow
 * when the browser cache was cleared.
 */
export async function attachUploadedPdf(
	documentId: string,
	filename: string,
	bytes: ArrayBuffer
): Promise<void> {
	await storePdf(documentId, filename, bytes);
	await hydrateExtractionText(documentId, bytes);
	await detectionStore.load(documentId);
}

/**
 * Populate `detectionStore.extraction` from either the cached OCR
 * result (scanned docs) or a fresh pdf.js text-layer extraction
 * (digital docs). Swallows `no_text` errors because they indicate a
 * scan where the reviewer declined OCR — the review view stays usable
 * with manual area selection.
 */
async function hydrateExtractionText(documentId: string, bytes: ArrayBuffer): Promise<void> {
	try {
		const cached = await getExtraction(documentId);
		if (cached) {
			detectionStore.setExtraction(cached);
			return;
		}
	} catch (e) {
		console.warn('Review page: extraction cache lookup failed', e);
	}

	try {
		const doc = await loadPdfDocument(bytes);
		const extraction = await extractText(doc);
		detectionStore.setExtraction(extraction);
	} catch (e) {
		if (e instanceof PdfError && e.kind === 'no_text') return;
		console.warn('Review page: could not re-extract text from PDF', e);
	}
}

/**
 * Open the browser's native file picker for PDF selection.
 * Resolves with the chosen file, or `null` if the picker was
 * dismissed without a selection.
 */
export function pickPdfFile(): Promise<File | null> {
	return new Promise((resolve) => {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = '.pdf';
		input.onchange = () => {
			const file = input.files?.[0] ?? null;
			resolve(file);
		};
		input.click();
	});
}
