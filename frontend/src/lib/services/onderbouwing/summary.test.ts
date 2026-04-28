import { describe, it, expect } from 'vitest';
import {
	buildReportRows,
	buildReportSummary,
	articlesForToelichting,
	motivationFor,
	selectReportableDetections
} from './summary';
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

describe('selectReportableDetections', () => {
	it('keeps only accepted and auto_accepted rows', () => {
		const rows = selectReportableDetections([
			makeDetection({ id: 'a', review_status: 'accepted' }),
			makeDetection({ id: 'b', review_status: 'rejected' }),
			makeDetection({ id: 'c', review_status: 'pending' }),
			makeDetection({ id: 'd', review_status: 'auto_accepted' })
		]);
		expect(rows.map((d) => d.id).sort()).toEqual(['a', 'd']);
	});

	it('orders rows by page, then y0, then id', () => {
		const rows = selectReportableDetections([
			makeDetection({
				id: 'p2-top',
				bounding_boxes: [{ page: 1, x0: 0, y0: 50, x1: 1, y1: 60 }]
			}),
			makeDetection({
				id: 'p1-bottom',
				bounding_boxes: [{ page: 0, x0: 0, y0: 200, x1: 1, y1: 210 }]
			}),
			makeDetection({
				id: 'p1-top',
				bounding_boxes: [{ page: 0, x0: 0, y0: 50, x1: 1, y1: 60 }]
			})
		]);
		expect(rows.map((d) => d.id)).toEqual(['p1-top', 'p1-bottom', 'p2-top']);
	});
});

describe('buildReportRows', () => {
	it('numbers rows starting at 1 in document order', () => {
		const rows = buildReportRows([
			makeDetection({ id: 'a' }),
			makeDetection({
				id: 'b',
				bounding_boxes: [{ page: 1, x0: 0, y0: 0, x1: 1, y1: 1 }]
			})
		]);
		expect(rows.map((r) => r.number)).toEqual([1, 2]);
	});

	it('converts 0-indexed bbox pages to 1-indexed for display', () => {
		const rows = buildReportRows([
			makeDetection({
				bounding_boxes: [{ page: 4, x0: 0, y0: 0, x1: 1, y1: 1 }]
			})
		]);
		expect(rows[0].page).toBe(5);
	});

	it('classifies reviewer-authored rows as handmatig', () => {
		const rows = buildReportRows([
			makeDetection({ source: 'manual' }),
			makeDetection({ source: 'search_redact' }),
			makeDetection({ source: 'deduce' })
		]);
		expect(rows.map((r) => r.source)).toEqual(['handmatig', 'handmatig', 'auto']);
	});

	it('does not include entity_text in any row', () => {
		const rows = buildReportRows([
			makeDetection({ entity_text: 'Jan de Vries' })
		]);
		const json = JSON.stringify(rows);
		expect(json).not.toContain('Jan de Vries');
	});
});

describe('motivationFor', () => {
	it('expands the article into a Dutch grond label', () => {
		const text = motivationFor(makeDetection({ woo_article: '5.1.1e' }));
		expect(text).toBe('Art. 5.1.1e \u2014 Identificatienummers');
	});

	it('falls back to a generic phrase when no article is set', () => {
		const text = motivationFor(makeDetection({ woo_article: null }));
		expect(text).toContain('Geen Woo-grond');
	});
});

describe('buildReportSummary', () => {
	it('counts rows by tier, source, article, and entity type', () => {
		const summary = buildReportSummary([
			makeDetection({ tier: '1', source: 'regex', woo_article: '5.1.1e', entity_type: 'bsn' }),
			makeDetection({ tier: '2', source: 'deduce', woo_article: '5.1.2e', entity_type: 'persoon' }),
			makeDetection({ tier: '2', source: 'manual', woo_article: '5.1.2e', entity_type: 'persoon' }),
			makeDetection({ tier: '3', source: 'rule', woo_article: '5.2', entity_type: 'persoon', review_status: 'rejected' })
		]);
		expect(summary.total).toBe(3);
		expect(summary.byTier).toEqual({ '1': 1, '2': 2, '3': 0 });
		expect(summary.bySource).toEqual({ auto: 2, handmatig: 1 });
		expect(summary.byArticle).toEqual([
			{ code: '5.1.1e', count: 1 },
			{ code: '5.1.2e', count: 2 }
		]);
		expect(summary.byEntityType[0]).toEqual({ label: 'Persoon', count: 2 });
	});
});

describe('articlesForToelichting', () => {
	it('returns each present article once, sorted by code', () => {
		const rows = buildReportRows([
			makeDetection({ id: 'a', woo_article: '5.1.2e' }),
			makeDetection({ id: 'b', woo_article: '5.1.1e' }),
			makeDetection({ id: 'c', woo_article: '5.1.2e' }),
			makeDetection({ id: 'd', woo_article: null })
		]);
		expect(articlesForToelichting(rows)).toEqual(['5.1.1e', '5.1.2e']);
	});
});
