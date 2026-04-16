/**
 * Export-flow state for the review page.
 *
 * Small runes-backed store that owns the export button's busy flag,
 * the retry banner's error string, and the post-export lead-capture
 * visibility (#45). Split out of `/review/[docId]/+page.svelte` so the
 * page component doesn't have to reason about the `try/catch/finally`
 * around `fetch` alongside all the other review state.
 *
 * The store is document-agnostic — `runExport()` takes the docId, PDF
 * bytes, and filename each call, and `reset()` is invoked from the
 * page's document-change effect so a new document starts clean.
 */

import { exportRedactedPdf, downloadBlob } from '$lib/services/export-service';
import { buildDebugExport, downloadDebugExport } from '$lib/services/debug-export';
import type { Detection, Document } from '$lib/types';

let exporting = $state(false);
let exportError = $state<string | null>(null);
let showPostExportLead = $state(false);

export interface RunExportArgs {
	docId: string;
	pdfBytes: ArrayBuffer;
	filename: string;
}

async function runExport({ docId, pdfBytes, filename }: RunExportArgs): Promise<void> {
	exporting = true;
	exportError = null;
	try {
		const redacted = await exportRedactedPdf(docId, pdfBytes);
		downloadBlob(redacted, `gelakt_${filename}`);
		showPostExportLead = true;
	} catch (e) {
		exportError = e instanceof Error ? e.message : 'Export mislukt';
	} finally {
		exporting = false;
	}
}

/**
 * Client-side diagnostic dump of the analyzer's output. Pulled in here
 * so the review page has a single import surface for "export things".
 */
function runDebugExport(doc: Document | null, detections: Detection[], docId: string): void {
	const payload = buildDebugExport(doc, detections);
	const base = doc?.filename ?? `document-${docId}`;
	downloadDebugExport(payload, base);
}

function setPostExportLead(next: boolean): void {
	showPostExportLead = next;
}

function setError(message: string | null): void {
	exportError = message;
}

function clearError(): void {
	exportError = null;
}

function reset(): void {
	exporting = false;
	exportError = null;
	showPostExportLead = false;
}

export const reviewExportStore = {
	get exporting() {
		return exporting;
	},
	get exportError() {
		return exportError;
	},
	get showPostExportLead() {
		return showPostExportLead;
	},
	runExport,
	runDebugExport,
	setPostExportLead,
	setError,
	clearError,
	reset
};
