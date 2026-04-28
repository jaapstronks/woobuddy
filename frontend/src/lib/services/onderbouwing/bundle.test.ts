import { describe, it, expect } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import { bundleOnderbouwing, deriveOnderbouwingFilename } from './bundle';
import type { Detection } from '$lib/types';

const NOW = new Date('2026-04-28T15:00:00Z');

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

describe('deriveOnderbouwingFilename', () => {
	it('uses the bare PDF filename when no CSV is bundled', () => {
		const name = deriveOnderbouwingFilename({
			originalFilename: 'Woo-besluit 2026-0042.pdf',
			includeCsv: false,
			now: NOW
		});
		expect(name).toBe('onderbouwing_Woo-besluit 2026-0042_2026-04-28.pdf');
	});

	it('switches to a zip extension when CSV is bundled', () => {
		const name = deriveOnderbouwingFilename({
			originalFilename: 'document.pdf',
			includeCsv: true,
			now: NOW
		});
		expect(name).toBe('onderbouwing_document_2026-04-28.zip');
	});

	it('strips path separators from the original filename', () => {
		const name = deriveOnderbouwingFilename({
			originalFilename: '../../etc/passwd.pdf',
			includeCsv: false,
			now: NOW
		});
		expect(name).not.toContain('/');
		expect(name).not.toContain('\\');
	});
});

describe('bundleOnderbouwing', () => {
	it('returns a bare PDF blob when CSV is not requested', () => {
		const result = bundleOnderbouwing({
			pdfBytes: new Uint8Array([0x25, 0x50, 0x44, 0x46]),
			originalFilename: 'document.pdf',
			includeCsv: false,
			detections: [makeDetection()],
			now: NOW
		});
		expect(result.blob.type).toBe('application/pdf');
		expect(result.filename).toMatch(/\.pdf$/);
	});

	it('zips PDF + CSV when CSV is requested', async () => {
		const pdfBytes = new Uint8Array([0x25, 0x50, 0x44, 0x46]);
		const result = bundleOnderbouwing({
			pdfBytes,
			originalFilename: 'document.pdf',
			includeCsv: true,
			detections: [makeDetection()],
			now: NOW
		});
		expect(result.blob.type).toBe('application/zip');
		const buf = new Uint8Array(await result.blob.arrayBuffer());
		const files = unzipSync(buf);
		const names = Object.keys(files).sort();
		expect(names).toEqual([
			'onderbouwing_document_2026-04-28.csv',
			'onderbouwing_document_2026-04-28.pdf'
		]);
		expect(strFromU8(files['onderbouwing_document_2026-04-28.csv'])).toContain(
			'#,pagina,type,trap'
		);
	});
});
