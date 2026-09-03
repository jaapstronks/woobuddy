import { describe, it, expect, vi } from 'vitest';

vi.mock('$env/static/public', () => ({ PUBLIC_API_URL: 'http://test.invalid' }));

import { buildRedactionList } from './export-service';
import { isAcceptedRedaction } from '$lib/utils/review-status';
import type { BoundingBox, Detection, ReviewStatus } from '$lib/types';

const ALL_STATUSES: ReviewStatus[] = [
	'pending',
	'accepted',
	'auto_accepted',
	'rejected',
	'deferred',
	'edited'
];

function bbox(page: number): BoundingBox {
	return { page, x0: 1, y0: 2, x1: 3, y1: 4 };
}

function detection(status: ReviewStatus, id: string): Detection {
	return {
		id,
		document_id: 'doc-1',
		entity_type: 'persoon',
		tier: '2',
		confidence: 0.9,
		woo_article: '5.1.2e',
		review_status: status,
		bounding_boxes: [bbox(0)],
		reasoning: null,
		propagated_from: null,
		reviewer_id: null,
		reviewed_at: null,
		is_environmental: false
	};
}

describe('buildRedactionList (#66/9)', () => {
	/**
	 * The gate: export is the one place where a hand-rolled "is this
	 * accepted?" predicate changes what actually gets burned into the PDF.
	 * It must agree with `isAcceptedRedaction` for every status, forever.
	 */
	it('redacts exactly the detections isAcceptedRedaction accepts', () => {
		const detections = ALL_STATUSES.map((s, i) => detection(s, `det-${i}`));
		const expected = detections.filter((d) => isAcceptedRedaction(d.review_status));

		const list = buildRedactionList(detections);

		expect(list).toHaveLength(expected.length);
		expect(expected.map((d) => d.review_status).sort()).toEqual(
			['accepted', 'auto_accepted'].sort()
		);
	});

	it('emits one record per bounding box, carrying the woo_article', () => {
		const det = detection('accepted', 'det-multi');
		det.bounding_boxes = [bbox(0), bbox(2)];

		const list = buildRedactionList([det]);

		expect(list.map((r) => r.page)).toEqual([0, 2]);
		expect(list.every((r) => r.woo_article === '5.1.2e')).toBe(true);
	});

	it('falls back to an empty article rather than dropping the box', () => {
		const det = detection('accepted', 'det-no-article');
		det.woo_article = null;

		expect(buildRedactionList([det])).toEqual([
			{ page: 0, x0: 1, y0: 2, x1: 3, y1: 4, woo_article: '' }
		]);
	});
});
