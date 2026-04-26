import { describe, it, expect } from 'vitest';
import { buildRedactionLogCsv } from './csv';
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
		bounding_boxes: [{ page: 1, x0: 0, y0: 0, x1: 10, y1: 10 }],
		reasoning: null,
		propagated_from: null,
		reviewer_id: null,
		reviewed_at: '2026-04-25T10:00:00Z',
		is_environmental: false,
		source: 'deduce',
		...overrides
	};
}

describe('buildRedactionLogCsv', () => {
	it('emits a header row matching the redaction-log column order', () => {
		const csv = buildRedactionLogCsv([]);
		const firstLine = csv.split('\n')[0];
		expect(firstLine).toBe(
			'#,pagina,type,trap,woo_artikel,grond,status,bron,beoordeeld_op,bbox_count,motivatie'
		);
	});

	it('only includes accepted and auto_accepted rows', () => {
		const csv = buildRedactionLogCsv([
			makeDetection({ id: 'a', review_status: 'accepted' }),
			makeDetection({ id: 'b', review_status: 'rejected' }),
			makeDetection({ id: 'c', review_status: 'auto_accepted' }),
			makeDetection({ id: 'd', review_status: 'pending' })
		]);
		const dataLines = csv.split('\n').slice(1).filter(Boolean);
		expect(dataLines).toHaveLength(2);
	});

	it('quotes values containing commas, newlines, or quotes', () => {
		const csv = buildRedactionLogCsv([
			makeDetection({ source: 'manual', reviewed_at: 'a, b' })
		]);
		expect(csv).toContain('"a, b"');
	});

	it('expands the article code into the Dutch motivation', () => {
		const csv = buildRedactionLogCsv([
			makeDetection({ woo_article: '5.1.1e' })
		]);
		expect(csv).toContain('Art. 5.1.1e — Identificatienummers');
	});

	it('survives a missing woo_article without throwing', () => {
		const csv = buildRedactionLogCsv([
			makeDetection({ woo_article: null, source: 'manual' })
		]);
		expect(csv).toContain('Geen Woo-artikel gekoppeld');
	});
});
