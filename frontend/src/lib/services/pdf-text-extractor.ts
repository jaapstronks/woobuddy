/**
 * Client-side PDF text extraction using pdf.js.
 *
 * Produces output compatible with the backend's ExtractionResult / TextSpan
 * format (pdf_engine.py). The key difference is coordinate systems:
 *
 * - pdf.js: bottom-left origin (standard PDF coordinate space)
 * - PyMuPDF: top-left origin
 *
 * This module flips Y-coordinates so the backend NER pipeline receives
 * bounding boxes in the same coordinate space as PyMuPDF would produce.
 */

import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { ExtractionResult, ExtractedTextItem, PageExtraction } from '$lib/types';

/**
 * Typed PDF error so UI code can show a specific Dutch message per failure mode
 * instead of rethrowing raw pdf.js exceptions.
 */
export type PdfErrorKind =
	| 'not_pdf' // magic bytes don't match %PDF- (e.g., JPEG renamed to .pdf)
	| 'invalid' // pdf.js could not parse the file
	| 'password' // encrypted with a password
	| 'no_text'; // loaded, but no selectable text (scanned)

export class PdfError extends Error {
	constructor(
		message: string,
		public readonly kind: PdfErrorKind,
		public readonly cause?: unknown
	) {
		super(message);
		this.name = 'PdfError';
	}
}

/**
 * Verify that a file starts with the PDF magic bytes (`%PDF-`).
 *
 * Checking magic bytes is defense-in-depth: the file picker is already
 * filtered to `.pdf`, but a malicious or confused user can rename any file
 * to `.pdf`. This runs entirely in the browser so we reject the file before
 * it ever touches pdf.js, and a clearer Dutch error reaches the UI.
 */
export async function verifyPdfMagicBytes(bytes: ArrayBuffer): Promise<void> {
	// A valid PDF header is at most 8 bytes (`%PDF-1.7` etc.). Reading the
	// first 5 is enough to reject non-PDFs without allocating anything big.
	const header = new Uint8Array(bytes, 0, Math.min(5, bytes.byteLength));
	const expected = [0x25, 0x50, 0x44, 0x46, 0x2d]; // %PDF-
	if (header.length < expected.length) {
		throw new PdfError(
			'Dit bestand is te klein om een geldig PDF te zijn.',
			'not_pdf'
		);
	}
	for (let i = 0; i < expected.length; i++) {
		if (header[i] !== expected[i]) {
			throw new PdfError(
				'Dit bestand is geen PDF. Alleen PDF-bestanden worden ondersteund.',
				'not_pdf'
			);
		}
	}
}

/**
 * Load a PDF from raw bytes and categorize failures into friendly Dutch
 * messages. pdf.js throws `PasswordException`, `InvalidPDFException`, etc.;
 * we wrap them in `PdfError` so `/try` can react without sniffing strings.
 */
export async function loadPdfDocument(bytes: ArrayBuffer): Promise<PDFDocumentProxy> {
	const pdfjsLib = await import('pdfjs-dist');
	pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
		'pdfjs-dist/build/pdf.worker.mjs',
		import.meta.url
	).toString();

	try {
		// Clone the buffer — pdf.js takes ownership of the Uint8Array it receives.
		return await pdfjsLib.getDocument({ data: new Uint8Array(bytes.slice(0)) }).promise;
	} catch (cause) {
		const name = (cause as { name?: string })?.name ?? '';
		if (name === 'PasswordException') {
			throw new PdfError(
				'Dit PDF-bestand is met een wachtwoord beveiligd. WOO Buddy kan beveiligde PDF\u2019s niet verwerken.',
				'password',
				cause
			);
		}
		throw new PdfError(
			'Het PDF-bestand kon niet worden gelezen. Mogelijk is het beschadigd of geen geldig PDF.',
			'invalid',
			cause
		);
	}
}

/**
 * Extract text with bounding boxes from all pages of a PDF document.
 *
 * The returned coordinates use top-left origin to match PyMuPDF conventions,
 * which the backend NER/LLM pipeline expects.
 *
 * Throws `PdfError` with kind `"no_text"` when the document yields zero
 * selectable characters (most likely a scanned PDF). Callers should block
 * analysis and suggest manual redaction instead.
 */
export async function extractText(
	pdfDoc: PDFDocumentProxy,
	onProgress?: (page: number, total: number) => void
): Promise<ExtractionResult> {
	const pages: PageExtraction[] = [];
	const allTextParts: string[] = [];
	const totalPages = pdfDoc.numPages;

	// Report an initial 0/total so the UI can render the first page-of-N
	// message without a flicker.
	onProgress?.(0, totalPages);

	for (let pageIdx = 0; pageIdx < totalPages; pageIdx++) {
		const page = await pdfDoc.getPage(pageIdx + 1); // pdf.js pages are 1-indexed
		const viewport = page.getViewport({ scale: 1.0 });
		const pageHeight = viewport.height;
		const textContent = await page.getTextContent();

		const textItems: ExtractedTextItem[] = [];

		for (const item of textContent.items) {
			if (!('str' in item) || !item.str.trim()) continue;

			const text = item.str.trim();
			const tx = item.transform;

			// tx = [scaleX, skewY, skewX, scaleY, translateX, translateY]
			// In PDF coordinate space (bottom-left origin):
			//   x0 = translateX
			//   y_bottom = translateY
			//   fontSize ~ |scaleY| (for horizontal text)
			//   width = item.width
			const x0 = tx[4];
			const yBottom = tx[5];
			const fontSize = Math.abs(tx[3]);
			const width = item.width;

			// Flip to top-left origin (PyMuPDF convention)
			const y0 = pageHeight - yBottom - fontSize;
			const x1 = x0 + width;
			const y1 = pageHeight - yBottom;

			textItems.push({ text, x0, y0, x1, y1 });
		}

		// Build fullText by detecting visually-adjacent text items on the same
		// line and joining them WITHOUT a space. pdf.js splits long tokens
		// (URLs, IBANs, phone numbers) across multiple text items; joining
		// blindly with " " inserts a phantom space that breaks regex and NER
		// matching. If the next item starts where the previous one ended (same
		// line, touching x-coordinates), it's a continuation of the same word.
		const SAME_LINE_TOLERANCE = 2; // points
		const ADJACENT_X_TOLERANCE = 1.5; // points
		const fullText = textItems.reduce((acc, item, idx) => {
			if (idx === 0) return item.text;
			const prev = textItems[idx - 1];
			const sameLine = Math.abs(item.y0 - prev.y0) < SAME_LINE_TOLERANCE;
			const touching = sameLine && item.x0 - prev.x1 < ADJACENT_X_TOLERANCE;
			return acc + (touching ? '' : ' ') + item.text;
		}, '');
		pages.push({
			pageNumber: pageIdx, // 0-indexed to match PyMuPDF convention
			fullText,
			textItems
		});
		allTextParts.push(fullText);
		onProgress?.(pageIdx + 1, totalPages);
	}

	const combined = allTextParts.join('\n\n').trim();
	if (combined.length === 0) {
		throw new PdfError(
			'Dit document bevat geen selecteerbare tekst (waarschijnlijk een gescande PDF). Automatische detectie werkt alleen op PDF\u2019s met tekst.',
			'no_text'
		);
	}

	return {
		pages,
		pageCount: pdfDoc.numPages,
		fullText: combined
	};
}
