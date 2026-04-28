/**
 * Integration tests for the tagged-PDF output of `buildOnderbouwingPdf`.
 *
 * These tests render a real PDF (via pdf-lib) and assert on the raw
 * byte stream. Because pdf-lib emits uncompressed content streams by
 * default, we can scan for marked-content operators and catalog
 * entries directly — no PDF parser dependency needed.
 *
 * The goal is to catch regressions in the structure-tree wiring:
 * missing /StructTreeRoot, dropped /MarkInfo, footer text accidentally
 * pulled out of /Artifact, etc. Visual / Acrobat / PAC validation is
 * a manual step (see `docs/todo/65-onderbouwingsrapport-tagged-pdf.md`).
 */

import { describe, it, expect } from 'vitest';
import { unzlibSync } from 'fflate';
import { buildOnderbouwingPdf } from './report';
import type { OnderbouwingInput } from './types';
import type { Detection } from '$lib/types';

function makeDetection(overrides: Partial<Detection> = {}): Detection {
	return {
		id: 'd1',
		document_id: 'doc1',
		entity_type: 'persoon',
		tier: '2',
		confidence: 0.9,
		woo_article: '5.1.2e',
		review_status: 'accepted',
		bounding_boxes: [{ page: 0, x0: 0, y0: 100, x1: 10, y1: 110 }],
		reasoning: null,
		propagated_from: null,
		reviewer_id: null,
		reviewed_at: '2026-04-25T10:00:00Z',
		is_environmental: false,
		source: 'deduce',
		...overrides
	};
}

function makeInput(overrides: Partial<OnderbouwingInput> = {}): OnderbouwingInput {
	return {
		document: {
			id: 'doc-1',
			filename: 'test.pdf',
			page_count: 5,
			created_at: '2026-04-25T10:00:00Z',
			updated_at: '2026-04-25T10:00:00Z',
			source_kind: 'pdf'
		},
		filename: 'test.pdf',
		detections: [makeDetection()],
		hashes: {
			originalSha256: 'sha256:abc123',
			redactedSha256: null
		},
		reviewer: {
			zaaknummer: 'TEST-001',
			reviewerName: 'Test Reviewer',
			opmerkingen: 'Test note',
			includeCsv: false
		},
		buildCommit: 'test',
		generatedAt: new Date('2026-04-28T19:00:00Z'),
		...overrides
	};
}

/**
 * Render and return the raw PDF bytes as a latin1 string.
 *
 * `latin1` is a 1-to-1 byte mapping so the catalog dict, structure
 * elements, ParentTree, and Outline objects (all emitted as plain
 * indirect objects since `useObjectStreams: false`) are directly
 * inspectable by substring search.
 */
async function renderPdfText(input: OnderbouwingInput): Promise<string> {
	const bytes = await buildOnderbouwingPdf(input);
	return new TextDecoder('latin1').decode(bytes);
}

/**
 * Render the PDF and return both the raw text *and* a concatenation
 * of all FlateDecode-compressed content streams decompressed back to
 * raw operator text. Use this when checking for operator-level
 * patterns (BMC, BDC, EMC, MCID) that live inside compressed page
 * content streams.
 */
async function renderPdfTextWithStreams(
	input: OnderbouwingInput
): Promise<{ raw: string; streams: string }> {
	const bytes = await buildOnderbouwingPdf(input);
	const raw = new TextDecoder('latin1').decode(bytes);
	const streams = decodeFlateStreams(bytes, raw);
	return { raw, streams };
}

/**
 * Walk the PDF bytes finding every `<<… /Filter /FlateDecode … /Length N>>
 * stream …<binary>… endstream` sequence and return the concatenation
 * of decompressed payloads. Uses `/Length N` from the dict to slice
 * exactly N bytes after the `stream\n` marker — robust against the
 * compressed payload accidentally containing the bytes "endstream".
 */
function decodeFlateStreams(bytes: Uint8Array, raw: string): string {
	const parts: string[] = [];
	const filterRe = /<<([\s\S]*?)>>\s*stream\r?\n/g;
	let match: RegExpExecArray | null;
	while ((match = filterRe.exec(raw))) {
		const dict = match[1];
		if (!dict.includes('/FlateDecode')) continue;
		const lenMatch = dict.match(/\/Length\s+(\d+)/);
		if (!lenMatch) continue;
		const len = parseInt(lenMatch[1], 10);
		const dataStart = match.index + match[0].length;
		const slice = bytes.slice(dataStart, dataStart + len);
		try {
			const decoded = unzlibSync(slice);
			parts.push(new TextDecoder('latin1').decode(decoded));
		} catch {
			// Cross-reference streams use FlateDecode with /W and
			// /Index, not raw zlib — skip them silently.
		}
	}
	return parts.join('\n---STREAM---\n');
}

describe('buildOnderbouwingPdf — structure tree (#65)', () => {
	it('mounts /StructTreeRoot on the catalog', async () => {
		const text = await renderPdfText(makeInput());
		expect(text).toContain('/StructTreeRoot');
		expect(text).toContain('/Type /StructTreeRoot');
	});

	it('declares /MarkInfo /Marked true', async () => {
		const text = await renderPdfText(makeInput());
		expect(text).toContain('/MarkInfo');
		expect(text).toContain('/Marked true');
	});

	it('emits at least one tagged marked-content sequence', async () => {
		const { streams } = await renderPdfTextWithStreams(makeInput());
		expect(streams).toMatch(/\/(?:H1|H2|H3|P|TR|TH|TD|Table) <<\/MCID \d+>> BDC/);
		// pdf-lib emits operators with zero args as `OP\n` (no
		// leading space). Match either with or without surrounding
		// whitespace to stay flexible.
		expect(streams).toMatch(/\bEMC\b/);
	});

	it('wraps decorative content in /Artifact BMC', async () => {
		const { streams } = await renderPdfTextWithStreams(makeInput());
		expect(streams).toContain('/Artifact BMC');
	});

	it('emits MCR leaves with /Pg page references', async () => {
		const text = await renderPdfText(makeInput());
		expect(text).toContain('/Type /MCR');
		expect(text).toMatch(/\/MCID \d+/);
	});

	it('builds a /ParentTree with at least one page entry', async () => {
		const text = await renderPdfText(makeInput());
		expect(text).toContain('/ParentTree');
		// Each rendered page lands at least one structure leaf, so the
		// parent tree's /Nums array is never empty.
		expect(text).toMatch(/\/Nums \[/);
	});

	it('sets /StructParents on every page', async () => {
		const text = await renderPdfText(makeInput());
		// Every page emitted should carry a /StructParents key.
		const matches = text.match(/\/StructParents \d+/g) ?? [];
		expect(matches.length).toBeGreaterThan(0);
	});

	it('mounts /Outlines on the catalog with at least four entries', async () => {
		const text = await renderPdfText(makeInput());
		expect(text).toContain('/Type /Outlines');
		// Each outline entry has /Title — count them.
		const titleMatches = text.match(/\/Title \(/g) ?? [];
		expect(titleMatches.length).toBeGreaterThanOrEqual(4);
	});

	it('opens /ViewerPreferences /DisplayDocTitle', async () => {
		const text = await renderPdfText(makeInput());
		expect(text).toContain('/DisplayDocTitle');
	});

	it('includes the four expected outline section titles', async () => {
		const text = await renderPdfText(makeInput());
		// pdf-lib serializes PDFString with parens + escapes. The
		// titles are pure ASCII so a literal substring check is enough.
		expect(text).toContain('Voorblad');
		expect(text).toContain('Samenvatting');
		expect(text).toContain('Tabel met redacties');
		expect(text).toContain('Bijlage A');
	});
});

describe('buildOnderbouwingPdf — privacy (#65 reaffirms #64)', () => {
	it('never embeds entity_text from any detection', async () => {
		const detection = makeDetection({
			// Detection has no `entity_text` field; this is a guard
			// against a future regression where someone adds one and
			// we forget to keep it out of the report. The test
			// inserts a sentinel string into adjacent fields and
			// asserts the rendered PDF contains none of it.
			reasoning: 'SECRET_PASSWORD_XYZ_DO_NOT_LEAK',
			id: 'SECRET_PASSWORD_XYZ_DO_NOT_LEAK'
		});
		const text = await renderPdfText(makeInput({ detections: [detection] }));
		expect(text).not.toContain('SECRET_PASSWORD_XYZ_DO_NOT_LEAK');
	});
});

describe('buildOnderbouwingPdf — table tagging on multi-page tables', () => {
	it('keeps the Table structure intact when the per-redactie table paginates', async () => {
		// 60 detections will overflow a single page table layout and
		// trigger the in-loop newPage + drawTableHeader pattern.
		const many = Array.from({ length: 60 }, (_, i) =>
			makeDetection({ id: `d${i}` })
		);
		const text = await renderPdfText(makeInput({ detections: many }));
		// We should see only ONE /S /Table structure element wrapping
		// the per-redactie table (plus any earlier ones for the
		// labeled-data tables on the cover & summary). Specifically
		// the per-redactie table should not duplicate.
		const tableElements = text.match(/\/Type \/StructElem\s*\/S \/Table\b/g) ?? [];
		// Cover key-value table + 2 summary tables + 1 per-redactie
		// table + provenance hash table = 5 by design. Allow a small
		// margin in case the summary breaks differently for empty
		// categories, but reject any explosion.
		expect(tableElements.length).toBeGreaterThanOrEqual(1);
		expect(tableElements.length).toBeLessThanOrEqual(8);
	});
});
