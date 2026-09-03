import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { Detection, ExtractionResult } from '$lib/types';

// ---------------------------------------------------------------------------
// #85 — the "kon niet geplaatst worden" record has to survive a refresh.
//
// These tests drive the real detections store against an in-memory stand-in
// for the IndexedDB session cache, so they exercise the actual write/read
// round trip a Cmd+R goes through. The store's other collaborators (API
// client, structure spans, analytics) are stubbed because they pull in
// `$env/static/public`, which vitest cannot resolve.
// ---------------------------------------------------------------------------

const { store } = vi.hoisted(() => ({
	store: new Map<string, Record<string, unknown>>()
}));

vi.mock('$lib/services/session-state-store', () => ({
	readSessionState: vi.fn(async (docId: string) => store.get(docId) ?? null),
	writeSessionState: vi.fn(async (state: { id: string }) => {
		store.set(state.id, structuredClone(state));
	}),
	writeSessionStateSlice: vi.fn(async (docId: string, patch: Record<string, unknown>) => {
		const prev = store.get(docId) ?? { id: docId };
		store.set(docId, { ...prev, ...structuredClone(patch) });
	})
}));

vi.mock('$lib/api/client', () => ({
	analyzeDocument: vi.fn(async () => ({ detections: [], structure_spans: [] }))
}));

vi.mock('$lib/stores/structure-spans.svelte', () => ({
	structureSpansStore: { set: vi.fn() }
}));

vi.mock('$lib/analytics/plausible', () => ({ track: vi.fn() }));

const { detectionStore } = await import('$lib/stores/detections.svelte');

const DOC = 'doc-85';

/**
 * One page, two visual lines. "Pieter" ends line 1 and "de Vries" opens
 * line 2, which is how the analyzer ends up with a name it cannot box.
 */
function extraction(): ExtractionResult {
	const textItems = [
		{ text: 'medewerker Pieter', x0: 0, y0: 100, x1: 102, y1: 110 },
		{ text: 'de Vries', x0: 0, y0: 120, x1: 48, y1: 130 }
	];
	const fullText = 'medewerker Pieter de Vries';
	return { pages: [{ pageNumber: 0, fullText, textItems }], pageCount: 1, fullText };
}

function detections(): Detection[] {
	return [
		{
			id: 'placed',
			entity_type: 'telefoon',
			tier: '1',
			confidence: 1,
			review_status: 'auto_accepted',
			bounding_boxes: [{ page: 0, x0: 0, y0: 100, x1: 102, y1: 110 }],
			source: 'regex'
		} as unknown as Detection,
		{
			id: 'unplaceable',
			entity_type: 'persoon',
			tier: '2',
			confidence: 0.8,
			review_status: 'pending',
			bounding_boxes: [],
			source: 'ner',
			start_char: 11,
			end_char: 26
		} as unknown as Detection
	];
}

describe('detectionStore — unplaced rows survive a refresh (#85)', () => {
	beforeEach(() => {
		store.clear();
	});

	it('keeps the unplaceable row in the session cache after a review action', async () => {
		detectionStore.setExtraction(extraction());
		await detectionStore.setFromAnalyze(DOC, detections(), []);
		expect(detectionStore.unplaced.map((u) => u.text)).toEqual(['Pieter de Vries']);

		// One ordinary review action used to narrow the cache to the placed
		// rows, because `persistDetections` writes the resolved list.
		await detectionStore.review('placed', { review_status: 'rejected' });

		const cached = store.get(DOC) as { detections: Detection[] };
		expect(cached.detections.map((d) => d.id).sort()).toEqual(['placed', 'unplaceable']);
	});

	it('rebuilds the banner from the cache on hydrate', async () => {
		detectionStore.setExtraction(extraction());
		await detectionStore.setFromAnalyze(DOC, detections(), []);
		await detectionStore.review('placed', { review_status: 'rejected' });

		const before = detectionStore.unplaced.map((u) => u.text);
		const ok = await detectionStore.hydrate(DOC);

		expect(ok).toBe(true);
		expect(detectionStore.unplaced.map((u) => u.text)).toEqual(before);
		// Still not a card: the row has no box to draw or edit.
		expect(detectionStore.all.map((d) => d.id)).toEqual(['placed']);
	});
});
