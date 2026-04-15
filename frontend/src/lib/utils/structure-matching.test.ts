import { describe, it, expect } from 'vitest';

import {
	spanKey,
	detectionInsideSpan,
	groupDetectionsBySpan,
	normalizeDetectionName,
	findSameNameDetections
} from './structure-matching';
import type { Detection, StructureSpan } from '$lib/types';

// ---------------------------------------------------------------------------
// Minimal Detection factory. The helpers only look at a handful of fields;
// the rest of the Detection shape is filled with inert defaults so tests
// don't have to care about unrelated data.
// ---------------------------------------------------------------------------

function det(overrides: Partial<Detection>): Detection {
	return {
		id: 'd',
		document_id: 'doc',
		entity_type: 'persoon',
		entity_text: '',
		tier: '2',
		woo_article: null,
		confidence: 0.8,
		confidence_level: 'medium',
		review_status: 'pending',
		bounding_boxes: [],
		reasoning: null,
		motivation_text: null,
		source: 'deduce',
		created_at: '',
		updated_at: '',
		is_environmental: false,
		subject_role: null,
		...overrides
	} as Detection;
}

const header: StructureSpan = {
	kind: 'email_header',
	start_char: 0,
	end_char: 100,
	confidence: 0.9,
	evidence: 'Van: ...'
};

const signature: StructureSpan = {
	kind: 'signature_block',
	start_char: 200,
	end_char: 300,
	confidence: 0.9,
	evidence: 'Met vriendelijke groet'
};

describe('spanKey', () => {
	it('encodes kind + range into a stable identifier', () => {
		expect(spanKey(header)).toBe('email_header:0-100');
		expect(spanKey(signature)).toBe('signature_block:200-300');
	});
});

describe('detectionInsideSpan', () => {
	it('returns true when fully contained', () => {
		const d = det({ start_char: 10, end_char: 20 });
		expect(detectionInsideSpan(d, header)).toBe(true);
	});

	it('returns false when partially overlapping', () => {
		const d = det({ start_char: 90, end_char: 110 });
		expect(detectionInsideSpan(d, header)).toBe(false);
	});

	it('returns false when detection has no char offsets', () => {
		const d = det({ start_char: null, end_char: null });
		expect(detectionInsideSpan(d, header)).toBe(false);
	});

	it('accepts an exact boundary match (span edges are inclusive)', () => {
		const d = det({ start_char: 0, end_char: 100 });
		expect(detectionInsideSpan(d, header)).toBe(true);
	});
});

describe('groupDetectionsBySpan', () => {
	it('buckets detections into their enclosing span', () => {
		const d1 = det({ id: 'a', start_char: 5, end_char: 15 });
		const d2 = det({ id: 'b', start_char: 210, end_char: 220 });
		const groups = groupDetectionsBySpan([d1, d2], [header, signature]);
		expect(groups).toHaveLength(2);
		expect(groups[0].key).toBe('email_header:0-100');
		expect(groups[0].detections.map((d) => d.id)).toEqual(['a']);
		expect(groups[1].key).toBe('signature_block:200-300');
		expect(groups[1].detections.map((d) => d.id)).toEqual(['b']);
	});

	it('tracks pending vs decided detections separately', () => {
		const pending = det({ id: 'a', start_char: 5, end_char: 15 });
		const accepted = det({ id: 'b', start_char: 20, end_char: 30, review_status: 'accepted' });
		const groups = groupDetectionsBySpan([pending, accepted], [header]);
		expect(groups).toHaveLength(1);
		expect(groups[0].detections).toHaveLength(2);
		expect(groups[0].pendingDetections.map((d) => d.id)).toEqual(['a']);
	});

	it('drops detections outside every relevant span', () => {
		const outside = det({ id: 'c', start_char: 150, end_char: 160 });
		const groups = groupDetectionsBySpan([outside], [header, signature]);
		expect(groups).toHaveLength(0);
	});

	it('ignores salutation spans by default', () => {
		const salutation: StructureSpan = {
			kind: 'salutation',
			start_char: 400,
			end_char: 410,
			confidence: 0.9,
			evidence: 'Beste'
		};
		const d = det({ id: 'x', start_char: 402, end_char: 405 });
		const groups = groupDetectionsBySpan([d], [salutation]);
		expect(groups).toHaveLength(0);
	});
});

describe('normalizeDetectionName', () => {
	it('lowercases and collapses internal whitespace', () => {
		expect(normalizeDetectionName('Jan  de  Vries')).toBe('jan de vries');
	});

	it('strips Dutch diacritics so accented names match their plain form', () => {
		expect(normalizeDetectionName('De Vríes')).toBe('de vries');
	});

	it('returns empty string for nullish input', () => {
		expect(normalizeDetectionName(null)).toBe('');
		expect(normalizeDetectionName(undefined)).toBe('');
	});
});

describe('findSameNameDetections', () => {
	it('matches on normalized form across the list', () => {
		const target = det({ id: 'a', entity_text: 'Jan de Vries' });
		const other = det({ id: 'b', entity_text: 'jan  de vries' });
		const unrelated = det({ id: 'c', entity_text: 'Piet Bakker' });
		const matches = findSameNameDetections(target, [target, other, unrelated]);
		expect(matches.map((d) => d.id)).toEqual(['a', 'b']);
	});

	it('only matches detections of the same entity_type', () => {
		const target = det({ id: 'a', entity_type: 'persoon', entity_text: 'Jan' });
		const wrongType = det({
			id: 'b',
			entity_type: 'email',
			entity_text: 'Jan'
		});
		const matches = findSameNameDetections(target, [target, wrongType]);
		expect(matches.map((d) => d.id)).toEqual(['a']);
	});

	it('returns just the target when entity_text is missing', () => {
		const target = det({ id: 'a', entity_text: '' });
		const matches = findSameNameDetections(target, [target]);
		expect(matches.map((d) => d.id)).toEqual(['a']);
	});
});
