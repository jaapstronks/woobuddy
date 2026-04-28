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
 * Flatten the accepted detections into per-bbox redaction records. Mirrors
 * the server-side `_build_redactions` helper so both sides agree on the
 * field shape; only `accepted` and `auto_accepted` rows produce
 * redactions, exactly as in the legacy DB-lookup mode.
 */
function buildRedactionList(detections: Detection[]): InlineRedaction[] {
	const redactions: InlineRedaction[] = [];
	for (const det of detections) {
		if (det.review_status !== 'accepted' && det.review_status !== 'auto_accepted') continue;
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
): Promise<Blob> {
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
	form.set('redactions', JSON.stringify(buildRedactionList(detections)));
	form.set('filename', filename);

	const response = await fetch(`${BASE}/api/export/redact-stream`, {
		method: 'POST',
		headers,
		body: form
	});

	if (!response.ok) {
		throw new Error(`Redactie mislukt: ${response.status}`);
	}

	const redactedBytes = await response.arrayBuffer();
	return new Blob([redactedBytes], { type: 'application/pdf' });
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
