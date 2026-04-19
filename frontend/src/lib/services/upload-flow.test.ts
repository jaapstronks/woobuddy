import { describe, it, expect, beforeEach, vi } from 'vitest';

// The upload flow talks to pdf.js, the API client, tesseract.js, and
// two IndexedDB-backed stores. For the OCR opt-in logic all we care
// about is the branching: "no text → ask → OCR runs / analyze skipped".
// Replace every dependency with a spy so the tests assert exactly which
// functions the flow calls for each reviewer decision.

vi.mock('$env/static/public', () => ({ PUBLIC_API_URL: 'http://test.invalid' }));

const { mocks, PdfErrorStub } = vi.hoisted(() => {
	class PdfErrorStub extends Error {
		kind: string;
		constructor(message: string, kind: string) {
			super(message);
			this.name = 'PdfError';
			this.kind = kind;
		}
	}
	return {
		PdfErrorStub,
		mocks: {
			verifyPdfMagicBytes: vi.fn(async () => {}),
			loadPdfDocument: vi.fn(async () => ({ numPages: 3 }) as unknown),
			extractText: vi.fn(async () => ({
				pages: [
					{ pageNumber: 0, fullText: 'hello', textItems: [{ text: 'hello', x0: 0, y0: 0, x1: 10, y1: 10 }] }
				],
				pageCount: 1,
				fullText: 'hello'
			})),
			runOcr: vi.fn(async () => ({
				pages: [
					{ pageNumber: 0, fullText: 'ocr', textItems: [{ text: 'ocr', x0: 0, y0: 0, x1: 10, y1: 10 }] },
					{ pageNumber: 1, fullText: 'two', textItems: [{ text: 'two', x0: 0, y0: 0, x1: 10, y1: 10 }] },
					{ pageNumber: 2, fullText: 'three', textItems: [{ text: 'three', x0: 0, y0: 0, x1: 10, y1: 10 }] }
				],
				pageCount: 3,
				fullText: 'ocr two three'
			})),
			registerDocument: vi.fn(async () => ({ id: 'doc-1' })),
			analyzeDocument: vi.fn(async () => undefined),
			storePdf: vi.fn(async () => {}),
			storeExtraction: vi.fn(async () => {})
		}
	};
});

vi.mock('$lib/services/pdf-text-extractor', () => ({
	verifyPdfMagicBytes: mocks.verifyPdfMagicBytes,
	loadPdfDocument: mocks.loadPdfDocument,
	extractText: mocks.extractText,
	PdfError: PdfErrorStub
}));

vi.mock('$lib/services/pdf-ocr', () => ({
	runOcr: mocks.runOcr,
	OcrError: class extends Error {}
}));

vi.mock('$lib/api/client', () => ({
	registerDocument: mocks.registerDocument,
	analyzeDocument: mocks.analyzeDocument,
	ApiError: class extends Error {}
}));

vi.mock('$lib/services/pdf-store', () => ({
	storePdf: mocks.storePdf,
	PdfStoreError: class extends Error {}
}));

vi.mock('$lib/services/extraction-store', () => ({
	storeExtraction: mocks.storeExtraction
}));

import { ingestFile } from './upload-flow';

function makeFile(name = 'scan.pdf', size = 1024): File {
	const blob = new Blob([new Uint8Array(size)], { type: 'application/pdf' });
	return new File([blob], name, { type: 'application/pdf' });
}

describe('ingestFile — OCR decision branching (#49)', () => {
	beforeEach(() => {
		for (const m of Object.values(mocks)) m.mockClear();
		// Restore the default extractText behaviour — individual tests
		// override it to simulate the no-text case.
		mocks.extractText.mockImplementation(async () => ({
			pages: [
				{ pageNumber: 0, fullText: 'hello', textItems: [] }
			],
			pageCount: 1,
			fullText: 'hello'
		}));
	});

	it('takes the digital-text path when extract succeeds — no OCR, no prompt', async () => {
		const onStep = vi.fn();
		const onNeedOcrDecision = vi.fn();

		const result = await ingestFile(makeFile(), { onStep, onNeedOcrDecision });

		expect(result.kind).toBe('ready');
		expect(onNeedOcrDecision).not.toHaveBeenCalled();
		expect(mocks.runOcr).not.toHaveBeenCalled();
		expect(mocks.storeExtraction).not.toHaveBeenCalled();
		expect(mocks.registerDocument).toHaveBeenCalledOnce();
	});

	it('prompts for OCR, runs it, and caches the result when the reviewer accepts', async () => {
		mocks.extractText.mockRejectedValueOnce(new PdfErrorStub('no text', 'no_text'));

		const onStep = vi.fn();
		const onNeedOcrDecision = vi.fn().mockResolvedValue('ocr');

		const result = await ingestFile(makeFile(), { onStep, onNeedOcrDecision });

		expect(onNeedOcrDecision).toHaveBeenCalledOnce();
		expect(mocks.runOcr).toHaveBeenCalledOnce();
		expect(mocks.registerDocument).toHaveBeenCalledOnce();
		// Storing the OCR extraction means a reload on the review page
		// can skip re-OCRing the scan.
		expect(mocks.storeExtraction).toHaveBeenCalledOnce();
		expect(result).toEqual({
			kind: 'ready',
			documentId: 'doc-1',
			pages: expect.any(Array),
			pageCount: 3,
			viaOcr: true
		});
		if (result.kind === 'ready') {
			expect(result.pages).toHaveLength(3);
		}
	});

	it('registers the doc but skips analyze when the reviewer declines OCR', async () => {
		mocks.extractText.mockRejectedValueOnce(new PdfErrorStub('no text', 'no_text'));

		const onNeedOcrDecision = vi.fn().mockResolvedValue('skip');

		const result = await ingestFile(makeFile(), { onStep: vi.fn(), onNeedOcrDecision });

		expect(result.kind).toBe('declined-ocr');
		expect(mocks.runOcr).not.toHaveBeenCalled();
		expect(mocks.storeExtraction).not.toHaveBeenCalled();
		expect(mocks.analyzeDocument).not.toHaveBeenCalled();
		// Still registers so the review page has a row to load.
		expect(mocks.registerDocument).toHaveBeenCalledOnce();
		// And stores the PDF so the review page can render it.
		expect(mocks.storePdf).toHaveBeenCalledOnce();
	});

	it('lets non-no-text extract errors bubble up unchanged', async () => {
		mocks.extractText.mockRejectedValueOnce(new PdfErrorStub('password protected', 'password'));
		const onNeedOcrDecision = vi.fn();

		await expect(
			ingestFile(makeFile(), { onStep: vi.fn(), onNeedOcrDecision })
		).rejects.toMatchObject({ kind: 'password' });

		expect(onNeedOcrDecision).not.toHaveBeenCalled();
		expect(mocks.runOcr).not.toHaveBeenCalled();
		expect(mocks.registerDocument).not.toHaveBeenCalled();
	});

	it('retains pre-#49 behaviour when no OCR handler is provided', async () => {
		// Older callers that don't know about OCR just get the original
		// PdfError thrown back, so their error UI continues to work.
		mocks.extractText.mockRejectedValueOnce(new PdfErrorStub('no text', 'no_text'));

		await expect(
			ingestFile(makeFile(), { onStep: vi.fn() })
		).rejects.toMatchObject({ kind: 'no_text' });
	});
});
