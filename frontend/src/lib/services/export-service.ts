/**
 * Client-side export service for client-first architecture.
 *
 * The client holds the PDF in IndexedDB and the detection list in
 * memory + IndexedDB session cache (#50). For export we send the PDF
 * and the accepted detections in a single multipart request to the
 * inline-redactions endpoint; the server redacts in memory and streams
 * the redacted PDF back. Nothing is written to disk on either side.
 */

import { PUBLIC_API_URL } from '$env/static/public';
import type { Detection } from '$lib/types';
import { isAcceptedRedaction } from '$lib/utils/review-status';

const BASE = PUBLIC_API_URL ?? 'http://localhost:8000';

export interface ExportRedactedOptions {
	/**
	 * Optional human-readable title to write into the redacted PDF's XMP
	 * `dc:title` metadata. Surfaces in DMS title columns and screen
	 * readers. Sent as the `X-Export-Title` header (deliberately not a
	 * query parameter) so it stays out of access logs and proxy URLs.
	 */
	title?: string;
}

interface InlineRedaction {
	page: number;
	x0: number;
	y0: number;
	x1: number;
	y1: number;
	woo_article: string;
}

/**
 * Flatten the accepted detections into per-bbox redaction records.
 *
 * "Accepted" is decided by `isAcceptedRedaction`, the same predicate the
 * redaction log and the card UI use. This function used to re-implement
 * it inline, and this is the one place in the app where drift changes
 * what actually gets burned into the PDF (#66/9).
 */
export function buildRedactionList(detections: Detection[]): InlineRedaction[] {
	const redactions: InlineRedaction[] = [];
	for (const det of detections) {
		if (!isAcceptedRedaction(det.review_status)) continue;
		if (!det.bounding_boxes) continue;
		for (const bbox of det.bounding_boxes) {
			redactions.push({
				page: bbox.page,
				x0: bbox.x0,
				y0: bbox.y0,
				x1: bbox.x1,
				y1: bbox.y1,
				woo_article: det.woo_article ?? ''
			});
		}
	}
	return redactions;
}

export interface RedactedExport {
	/** The redacted PDF, ready for download. */
	blob: Blob;
	/** Rectangles the server actually burned in. */
	applied: number;
	/**
	 * Rectangles the server dropped because their page index fell outside
	 * the document. Non-zero means the download is missing black boxes and
	 * the reviewer has to be told (#66/5). Zero when the server predates
	 * the counting headers.
	 */
	skipped: number;
}

/**
 * Redact a single document via the inline-redactions endpoint. Sends
 * the PDF bytes alongside the accepted detection list as multipart
 * form data, gets the redacted PDF back as a Blob suitable for
 * download.
 */
export async function exportRedactedPdf(
	pdfBytes: ArrayBuffer,
	filename: string,
	detections: Detection[],
	options: ExportRedactedOptions = {}
): Promise<RedactedExport> {
	const headers: Record<string, string> = {};
	const trimmedTitle = options.title?.trim();
	if (trimmedTitle) {
		headers['X-Export-Title'] = trimmedTitle;
	}

	const form = new FormData();
	form.set(
		'pdf',
		new Blob([pdfBytes], { type: 'application/pdf' }),
		filename
	);
	const requested = buildRedactionList(detections);
	form.set('redactions', JSON.stringify(requested));
	form.set('filename', filename);

	const response = await fetch(`${BASE}/api/export/redact-stream`, {
		method: 'POST',
		headers,
		body: form
	});

	if (!response.ok) {
		throw new Error(`Redactie mislukt: ${response.status}`);
	}

	const skipped = readCountHeader(response, 'X-Redactions-Skipped', 0);
	const applied = readCountHeader(
		response,
		'X-Redactions-Applied',
		requested.length - skipped
	);

	const redactedBytes = await response.arrayBuffer();
	return {
		blob: new Blob([redactedBytes], { type: 'application/pdf' }),
		applied,
		skipped
	};
}

/** Read a non-negative integer response header, or `fallback`. */
function readCountHeader(response: Response, name: string, fallback: number): number {
	const raw = response.headers.get(name);
	if (raw === null) return fallback;
	const parsed = Number.parseInt(raw, 10);
	return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

/**
 * Trigger a browser download for a Blob.
 */
export function downloadBlob(blob: Blob, filename: string): void {
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}
