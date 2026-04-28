/**
 * Upload flow — extract text, generate a local docId, run analyze.
 *
 * Extracted from the Hero component so the step-machine + pipeline can
 * be exercised without pulling in a DOM renderer. The component layer
 * still owns UI state (`files`, `uploading`, button visibility); this
 * module owns the *flow* (step transitions, error shape, retry shape).
 *
 * The flow has three possible shapes:
 *
 * 1. Digital PDF — pdf.js extracts a text layer, normal analyze.
 * 2. Scanned PDF, reviewer accepts OCR (#49) — tesseract.js produces
 *    an `ExtractionResult` in the browser, which is cached in
 *    IndexedDB and then fed to analyze exactly like the digital path.
 * 3. Scanned PDF, reviewer declines OCR — the document is stored
 *    locally (so the review page can show it) but analyze is skipped;
 *    the reviewer lands on an empty detection list and redacts with
 *    manual area selection (#07).
 *
 * Anonymous-only (#50): no document is ever registered on the server.
 * `docId` is generated client-side via `crypto.randomUUID()` and used
 * as the IndexedDB key for both `pdf-store` and `session-state-store`.
 */

import { analyzeDocument, ApiError, type AnalyzeResponse } from '$lib/api/client';
import { storePdf, PdfStoreError } from '$lib/services/pdf-store';
import {
	extractText,
	loadPdfDocument,
	verifyPdfMagicBytes,
	PdfError
} from '$lib/services/pdf-text-extractor';
import { runOcr, OcrError } from '$lib/services/pdf-ocr';
import { storeExtraction } from '$lib/services/extraction-store';
import type { Step } from '$lib/components/shared/ProgressSteps.svelte';
import type { ExtractionResult, PageExtraction } from '$lib/types';

export const LARGE_PDF_BYTES = 20 * 1024 * 1024;
export const LARGE_PDF_PAGES = 100;

export type StepId = 'load' | 'extract' | 'analyze';

export const INITIAL_STEPS: Step[] = [
	{ id: 'load', label: 'PDF laden', status: 'pending' },
	{ id: 'extract', label: 'Tekst extraheren (in je browser)', status: 'pending' },
	{ id: 'analyze', label: 'Persoonsgegevens detecteren', status: 'pending' }
];

export function cloneInitialSteps(): Step[] {
	return INITIAL_STEPS.map((s) => ({ ...s }));
}

export function advanceTo(
	id: StepId,
	detail: string | null = null,
	percent: number | null = null,
	labelOverride: string | null = null
): Step[] {
	const idx = INITIAL_STEPS.findIndex((s) => s.id === id);
	return INITIAL_STEPS.map((s, i) => {
		if (i < idx) return { ...s, status: 'done' };
		if (i === idx) {
			const label = labelOverride ?? s.label;
			return { ...s, label, status: 'active', detail, percent };
		}
		return { ...s, status: 'pending' };
	});
}

export function allDone(): Step[] {
	return INITIAL_STEPS.map((s) => ({ ...s, status: 'done' }));
}

export function describeError(e: unknown): string {
	if (e instanceof PdfError) return e.message;
	if (e instanceof PdfStoreError) return e.message;
	if (e instanceof OcrError) return e.message;
	if (e instanceof ApiError) return e.message;
	if (e instanceof Error) return e.message;
	return 'Er ging iets mis';
}

/**
 * Reviewer's answer to the OCR opt-in dialog for #49.
 *
 * - `ocr`: run tesseract.js on the document before proceeding.
 * - `skip`: store the document locally without detection so the reviewer
 *   can go straight to manual redaction.
 */
export type OcrDecision = 'ocr' | 'skip';

/**
 * Callbacks the component uses to drive its own rendering as the flow
 * progresses. Kept narrow so the flow doesn't reach into Svelte state.
 *
 * `onNeedOcrDecision` is invoked exactly once, only when the document
 * has no selectable text. If omitted, a no-text document throws a
 * `PdfError('no_text')` — matching the pre-#49 behaviour — so callers
 * that don't know about OCR keep working.
 */
export interface UploadFlowHandlers {
	onStep: (
		id: StepId,
		detail?: string | null,
		percent?: number | null,
		labelOverride?: string | null
	) => void;
	onNeedOcrDecision?: () => Promise<OcrDecision>;
}

export type IngestResult =
	| {
			kind: 'ready';
			documentId: string;
			filename: string;
			pages: PageExtraction[];
			pageCount: number;
			viaOcr: boolean;
	  }
	| { kind: 'declined-ocr'; documentId: string; filename: string; pageCount: number; viaOcr: false };

const OCR_STEP_LABEL = 'Tekst herkennen (OCR, in je browser)';

/**
 * Ingest a file: extract (or OCR) text, generate a local docId, store
 * the PDF locally in IndexedDB, and — if OCR ran — cache the
 * ExtractionResult so the review page can reuse it on reload without
 * re-running OCR.
 *
 * No server calls. The PDF and its text never leave the browser at this
 * stage; analyze is a separate step the caller invokes via {@link runAnalyze}.
 *
 * Errors are not caught here — the caller owns the error UI.
 */
export async function ingestFile(
	file: File,
	handlers: UploadFlowHandlers
): Promise<IngestResult> {
	const isLarge = file.size >= LARGE_PDF_BYTES;
	handlers.onStep(
		'load',
		isLarge ? 'Dit is een groot bestand, dit kan even duren.' : null
	);

	const bytes = await file.arrayBuffer();
	await verifyPdfMagicBytes(bytes);
	const pdfDoc = await loadPdfDocument(bytes);

	const totalPages = pdfDoc.numPages;
	const extractDetail =
		totalPages >= LARGE_PDF_PAGES ? `Dit document heeft ${totalPages} pagina’s.` : null;

	let extraction: ExtractionResult | null = null;
	let viaOcr = false;

	handlers.onStep('extract', extractDetail, 0);
	try {
		extraction = await extractText(pdfDoc, (page, total) => {
			const percent = total === 0 ? 0 : Math.round((page / total) * 100);
			handlers.onStep(
				'extract',
				`Pagina ${page} van ${total}${extractDetail ? ' · ' + extractDetail : ''}`,
				percent
			);
		});
	} catch (e) {
		// A PDF with no selectable text is our cue to offer OCR. Any
		// other extract error (password, corrupt, etc.) bubbles up.
		const isNoText = e instanceof PdfError && e.kind === 'no_text';
		if (!isNoText || !handlers.onNeedOcrDecision) throw e;

		const decision = await handlers.onNeedOcrDecision();

		if (decision === 'skip') {
			// Decline path: still store the document locally so the review
			// page has a PDF to render, but skip analyze entirely.
			const docId = crypto.randomUUID();
			await storePdf(docId, file.name, bytes);
			return {
				kind: 'declined-ocr',
				documentId: docId,
				filename: file.name,
				pageCount: totalPages,
				viaOcr: false
			};
		}

		// Accept path: re-use the extract step's slot in the step list,
		// but override the label so the reviewer sees "tekst herkennen"
		// rather than "tekst extraheren".
		handlers.onStep('extract', null, 0, OCR_STEP_LABEL);
		extraction = await runOcr(pdfDoc, (p) => {
			const percent = Math.round(p.overall * 100);
			handlers.onStep(
				'extract',
				`Pagina ${p.page} van ${p.totalPages}`,
				percent,
				OCR_STEP_LABEL
			);
		});
		viaOcr = true;
	}

	// Past this point `extraction` is set for both digital and OCR paths.
	// Generate the local docId and persist the PDF to IndexedDB. There is
	// no server registration step — the docId is a pure client construct.
	const docId = crypto.randomUUID();
	await storePdf(docId, file.name, bytes);
	if (viaOcr) {
		// Cache so the review page's own `extractAndSetText` pass can
		// skip re-running OCR. A fresh tab reload on a scanned doc is
		// otherwise a 30–90 second cliff.
		await storeExtraction(docId, extraction);
	}

	return {
		kind: 'ready',
		documentId: docId,
		filename: file.name,
		pages: extraction.pages,
		pageCount: extraction.pageCount,
		viaOcr
	};
}

/**
 * Run analyze on a document that's already been ingested. Split from
 * `ingestFile` so the Hero can expose a retry button that re-runs just
 * this step without re-extracting.
 *
 * Returns the full {@link AnalyzeResponse} so callers can stash the
 * detection list into the detection store before navigating to the
 * review page — the server holds nothing, so the response is the only
 * source of truth for this analysis.
 */
export async function runAnalyze(
	pages: PageExtraction[],
	handlers: UploadFlowHandlers
): Promise<AnalyzeResponse> {
	handlers.onStep('analyze');
	return analyzeDocument(pages);
}
