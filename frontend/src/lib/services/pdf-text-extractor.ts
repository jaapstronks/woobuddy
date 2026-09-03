/**
 * Client-side PDF text extraction using pdf.js.
 *
 * Produces output compatible with the backend's ExtractionResult / TextSpan
 * format (pdf_engine.py). The key difference is coordinate systems:
 *
 * - pdf.js text items: bottom-left origin, /Rotate NOT applied (user space)
 * - the rest of WOO Buddy: top-left origin, /Rotate applied (viewer space)
 *
 * Viewer space is what the overlay draws in, what area-select produces, and
 * what `apply_redactions` derotates back for PyMuPDF via
 * `page.derotation_matrix`. So every bbox here goes through the page viewport
 * transform, which is the only thing that knows about /Rotate.
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
 * Minimal shape of a pdf.js `PageViewport`. Only the point conversion is
 * needed here, and keeping it structural means tests can hand in a plain
 * object instead of constructing a real viewport.
 */
interface ViewportLike {
	convertToViewportPoint(x: number, y: number): number[];
}

interface BBox {
	x0: number;
	y0: number;
	x1: number;
	y1: number;
}

/**
 * Map a PDF-user-space rectangle onto a viewport, normalised to x0 < x1 and
 * y0 < y1.
 *
 * `convertToViewportPoint` transforms each corner independently, and at
 * /Rotate 90/180/270 that swaps or mirrors them — the "bottom-left" corner
 * can come back to the right of, or below, the "top-right" one. Everything
 * downstream (overlay hit-testing, `apply_redactions`) assumes an ordered
 * rect, so sort here rather than in five call sites.
 */
function toViewportBox(
	viewport: ViewportLike,
	x0: number,
	yBottom: number,
	x1: number,
	yTop: number
): BBox {
	const [ax, ay] = viewport.convertToViewportPoint(x0, yBottom);
	const [bx, by] = viewport.convertToViewportPoint(x1, yTop);
	return {
		x0: Math.min(ax, bx),
		y0: Math.min(ay, by),
		x1: Math.max(ax, bx),
		y1: Math.max(ay, by)
	};
}

/**
 * Extract text with bounding boxes from all pages of a PDF document.
 *
 * The returned coordinates use top-left origin to match PyMuPDF conventions,
 * which the backend NER pipeline expects.
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
		// Viewer space: /Rotate applied, top-left origin, scale 1. `getViewport`
		// defaults its rotation to the page's own /Rotate.
		const viewport = page.getViewport({ scale: 1.0 });
		// The same page with /Rotate forced off. Reading order is horizontal in
		// this space whatever the page rotation says, so the line/adjacency
		// heuristic below runs on these coordinates: at /Rotate 90 a single
		// baseline runs top-to-bottom on screen and every same-line test in
		// viewer space would fail.
		const layoutViewport = page.getViewport({ scale: 1.0, rotation: 0 });
		const textContent = await page.getTextContent();

		const textItems: ExtractedTextItem[] = [];
		const layoutBoxes: BBox[] = [];

		for (const item of textContent.items) {
			if (!('str' in item) || !item.str.trim()) continue;

			const text = item.str.trim();
			const tx = item.transform;

			// tx = [scaleX, skewY, skewX, scaleY, translateX, translateY] in PDF
			// user space (bottom-left origin, /Rotate not applied). The glyph box
			// runs from the baseline origin to (item.width, fontHeight).
			//
			// fontHeight is hypot(tx[2], tx[3]), not |tx[3]|: that is what pdf.js's
			// own TextLayer uses, and it keeps the height correct for skewed text
			// matrices where it leaks into tx[2]. For upright text tx[2] is 0 and
			// the two are identical. A *rotated* text matrix (sideways text on a
			// /Rotate 0 page) still yields a box laid out along x, so only its
			// height is right — pre-existing, and out of scope here.
			const x0 = tx[4];
			const yBottom = tx[5];
			const fontHeight = Math.hypot(tx[2], tx[3]);
			const x1 = x0 + item.width;
			const yTop = yBottom + fontHeight;

			textItems.push({ text, ...toViewportBox(viewport, x0, yBottom, x1, yTop) });
			layoutBoxes.push(toViewportBox(layoutViewport, x0, yBottom, x1, yTop));
		}

		// Build fullText by detecting visually-adjacent text items on the same
		// line and joining them WITHOUT a space. pdf.js splits long tokens
		// (URLs, IBANs, phone numbers) across multiple text items; joining
		// blindly with " " inserts a phantom space that breaks regex and NER
		// matching. If the next item starts where the previous one ended (same
		// line, touching x-coordinates), it's a continuation of the same word.
		// Measured on `layoutBoxes` (unrotated), so the tolerances below stay
		// horizontal-reading tolerances on a /Rotate 90 page too.
		const SAME_LINE_TOLERANCE = 2; // points
		const ADJACENT_X_TOLERANCE = 1.5; // points
		const fullText = textItems.reduce((acc, item, idx) => {
			if (idx === 0) return item.text;
			const box = layoutBoxes[idx];
			const prev = layoutBoxes[idx - 1];
			const sameLine = Math.abs(box.y0 - prev.y0) < SAME_LINE_TOLERANCE;
			const touching = sameLine && box.x0 - prev.x1 < ADJACENT_X_TOLERANCE;
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
