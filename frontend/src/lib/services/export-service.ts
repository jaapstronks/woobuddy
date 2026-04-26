/**
 * Client-side export service for client-first architecture.
 *
 * The client holds the PDF in IndexedDB. For export, we send the PDF to the
 * streaming redaction endpoint and get the redacted PDF back in memory. The
 * server never writes it to disk.
 */

import { PUBLIC_API_URL } from '$env/static/public';

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

/**
 * Redact a single document via the streaming endpoint. Returns a Blob
 * containing the redacted PDF, suitable for download.
 */
export async function exportRedactedPdf(
	documentId: string,
	pdfBytes: ArrayBuffer,
	options: ExportRedactedOptions = {}
): Promise<Blob> {
	const headers: Record<string, string> = { 'Content-Type': 'application/pdf' };
	const trimmedTitle = options.title?.trim();
	if (trimmedTitle) {
		headers['X-Export-Title'] = trimmedTitle;
	}
	const response = await fetch(`${BASE}/api/documents/${documentId}/export/redact-stream`, {
		method: 'POST',
		headers,
		body: pdfBytes
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
