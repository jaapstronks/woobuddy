/**
 * In-browser OCR for scanned PDFs (#49).
 *
 * Loaded dynamically — the `tesseract.js` bundle, its wasm core, and the
 * Dutch language model total ~5–6 MB. None of that lives in the default
 * `/try` bundle; `runOcr` must be the import entry point so the cost is
 * only paid by users who actually upload a scan.
 *
 * The output of `runOcr` is an `ExtractionResult` with the same shape as
 * `pdf-text-extractor.extractText` — same top-left-origin PDF-point
 * coordinates, same per-word `ExtractedTextItem`s — so everything
 * downstream (detection payload, `bbox-text-resolver`, `search-redact`)
 * works on OCR'd documents without any conditional plumbing.
 *
 * Trust: tesseract.js, its wasm core, and the traineddata file are all
 * served from our own origin under `/tesseract/` (populated by
 * `npm run setup:tesseract`). The worker makes zero outbound requests
 * while OCR runs.
 */
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { ExtractedTextItem, ExtractionResult, PageExtraction } from '$lib/types';

export interface OcrProgress {
	/** 1-indexed page currently being processed. */
	page: number;
	/** Total number of pages in the document. */
	totalPages: number;
	/** 0..1 progress within the current page (tesseract's own percentage). */
	pageFraction: number;
	/** Overall document progress, 0..1. */
	overall: number;
}

/**
 * Render scale in PDF-points → canvas-pixels. 2.0 is roughly 200 DPI
 * on a 72pt PDF page, which is tesseract's sweet spot for printed
 * Dutch text — higher costs CPU with minimal accuracy gain, lower
 * starts dropping thin strokes on lowercase 'l'/'i'.
 */
const RENDER_SCALE = 2.0;

/**
 * Self-hosted asset paths — kept together so an ops change (CDN
 * override, asset host move) only needs to touch one constant.
 *
 * `tesseract.js` joins `langPath` + `${lang}.traineddata.gz` when
 * `gzip: true`, and it expects `corePath` to be the *directory*
 * containing the wasm variants (it picks the right file based on
 * feature detection).
 */
const TESSERACT_BASE = '/tesseract/';

export class OcrError extends Error {
	constructor(
		message: string,
		public readonly cause?: unknown
	) {
		super(message);
		this.name = 'OcrError';
	}
}

/**
 * Run OCR on every page of a PDF and produce an ExtractionResult.
 *
 * `onProgress` is called at least once per page; the overall fraction
 * is monotonic so the UI can drive a progress bar directly. All state
 * is torn down before returning — no workers leak between runs.
 */
export async function runOcr(
	pdfDoc: PDFDocumentProxy,
	onProgress?: (p: OcrProgress) => void
): Promise<ExtractionResult> {
	// Dynamic import keeps the ~3 MB tesseract.js bundle out of the
	// landing-page chunk. Only the OCR path pays for it.
	const { createWorker } = await import('tesseract.js');

	let worker: Awaited<ReturnType<typeof createWorker>> | null = null;
	try {
		const totalPages = pdfDoc.numPages;
		onProgress?.({ page: 1, totalPages, pageFraction: 0, overall: 0 });

		let currentPage = 1;
		worker = await createWorker('nld', 1, {
			workerPath: `${TESSERACT_BASE}worker.min.js`,
			corePath: TESSERACT_BASE,
			langPath: TESSERACT_BASE,
			gzip: true,
			// Tesseract's logger fires with `{ status, progress }` from the
			// recognize phase, where `progress` is 0..1 within the current
			// page. We fold this into an overall fraction for the UI.
			logger: (m: { status: string; progress: number }) => {
				if (m.status !== 'recognizing text') return;
				const pageFraction = m.progress;
				const overall = (currentPage - 1 + pageFraction) / totalPages;
				onProgress?.({ page: currentPage, totalPages, pageFraction, overall });
			}
		});

		const pages: PageExtraction[] = [];
		const fullTextParts: string[] = [];

		for (let pageIdx = 0; pageIdx < totalPages; pageIdx++) {
			currentPage = pageIdx + 1;

			const page = await pdfDoc.getPage(currentPage);
			// Natural viewport at scale=1 gives us PDF-point dimensions; we
			// convert canvas-pixel bboxes back to points by dividing by
			// RENDER_SCALE. pdfPointWidth/Height are kept for reference but
			// the inverse (1 / RENDER_SCALE) is what the conversion uses.
			const renderViewport = page.getViewport({ scale: RENDER_SCALE });

			const canvas = document.createElement('canvas');
			canvas.width = Math.ceil(renderViewport.width);
			canvas.height = Math.ceil(renderViewport.height);
			// pdfjs v5 takes the canvas directly and manages its own 2d context.
			await page.render({ canvas, viewport: renderViewport }).promise;

			// v6 moved non-text output behind an opt-in; v7 finished the
			// migration by removing top-level `words`/`lines` entirely.
			// Passing `{ blocks: true }` gets us the full
			// block → paragraph → line → word tree we flatten below.
			const { data } = await worker.recognize(canvas, {}, { blocks: true });

			// Tesseract returns per-word bboxes in canvas pixels with
			// top-left origin — exactly the coordinate space we want for
			// the rest of the pipeline, just scaled. Divide by
			// RENDER_SCALE to get PDF points.
			const textItems: ExtractedTextItem[] = [];
			for (const block of data.blocks ?? []) {
				for (const paragraph of block.paragraphs) {
					for (const line of paragraph.lines) {
						for (const word of line.words) {
							const text = (word.text ?? '').trim();
							if (!text) continue;
							const bbox = word.bbox;
							if (!bbox) continue;
							textItems.push({
								text,
								x0: bbox.x0 / RENDER_SCALE,
								y0: bbox.y0 / RENDER_SCALE,
								x1: bbox.x1 / RENDER_SCALE,
								y1: bbox.y1 / RENDER_SCALE
							});
						}
					}
				}
			}

			// Re-assemble the page full-text using the same
			// visually-adjacent-items rule as `pdf-text-extractor`, so
			// detection on OCR'd docs behaves identically to detection on
			// digital PDFs. Tesseract's own `data.text` inserts newlines
			// between words on the same line for some inputs, which
			// breaks regex matches that cross a (tesseract-internal) line
			// boundary.
			const SAME_LINE_TOLERANCE = 2;
			const ADJACENT_X_TOLERANCE = 1.5;
			const pageFullText = textItems.reduce((acc, item, idx) => {
				if (idx === 0) return item.text;
				const prev = textItems[idx - 1];
				const sameLine = Math.abs(item.y0 - prev.y0) < SAME_LINE_TOLERANCE;
				const touching = sameLine && item.x0 - prev.x1 < ADJACENT_X_TOLERANCE;
				return acc + (touching ? '' : ' ') + item.text;
			}, '');

			pages.push({
				pageNumber: pageIdx, // 0-indexed to match PyMuPDF convention
				fullText: pageFullText,
				textItems
			});
			fullTextParts.push(pageFullText);

			// Page-complete signal (tesseract's logger only fires inside
			// the recognize phase; we need this tick to make "page N of M"
			// advance reliably even if a page finishes in one burst).
			onProgress?.({
				page: currentPage,
				totalPages,
				pageFraction: 1,
				overall: currentPage / totalPages
			});
		}

		return {
			pages,
			pageCount: totalPages,
			fullText: fullTextParts.join('\n\n').trim()
		};
	} catch (cause) {
		if (cause instanceof OcrError) throw cause;
		// Surface the underlying cause in the devtools console so we can
		// see what actually failed — the user-facing message stays friendly.
		console.error('[pdf-ocr] OCR failed:', cause);
		throw new OcrError(
			'Tekstherkenning mislukte. Controleer of de Nederlandse taalmodule is ge\u00efnstalleerd (npm run setup:tesseract).',
			cause
		);
	} finally {
		if (worker) {
			try {
				await worker.terminate();
			} catch {
				// ignore termination errors — the worker process is gone either way
			}
		}
	}
}
