/**
 * Structure-span ↔ detection matching helpers (#20 bulk sweeps).
 *
 * The bulk-sweep UI (email header / signature block / same-name) needs
 * three things:
 *
 *   1. Group detections by the structure span they fall inside.
 *   2. Count how many of those detections are still pending (the rest
 *      have a decision the reviewer has already made and must not be
 *      silently overwritten).
 *   3. Group `persoon` detections by normalized name so a reviewer can
 *      apply a single decision to every occurrence of "Jan de Vries".
 *
 * All of this is pure functions over the already-loaded detections and
 * the structure spans returned with the analyze response. No I/O.
 */

import type { Detection, StructureSpan, StructureSpanKind } from '$lib/types';

// ---------------------------------------------------------------------------
// Span key — stable identifier for a single structure span in this session.
//
// Spans come back from the server unsorted-by-id; we key them by kind +
// character range so the frontend can build a Map without caring about
// reference equality. A reviewer never sees these strings — they are only
// used as Svelte `{#each}` keys and as the discriminator on the
// `SweepBlockCommand` so redo can target the same block again.
// ---------------------------------------------------------------------------

export function spanKey(span: StructureSpan): string {
	return `${span.kind}:${span.start_char}-${span.end_char}`;
}

// ---------------------------------------------------------------------------
// Interval test — a detection sits "inside" a span when its full character
// range fits within the span's range. We deliberately require full
// containment (not overlap) so a name that straddles a block boundary is
// not swept along with the block.
// ---------------------------------------------------------------------------

export function detectionInsideSpan(
	detection: Detection,
	span: StructureSpan
): boolean {
	if (detection.start_char == null || detection.end_char == null) return false;
	return (
		detection.start_char >= span.start_char && detection.end_char <= span.end_char
	);
}

// ---------------------------------------------------------------------------
// Detections grouped by enclosing span.
//
// One detection can technically match more than one span (a salutation
// nested inside a forwarded email header), but in practice the backend's
// structure engine emits disjoint ranges for the kinds we sweep
// (`email_header` and `signature_block`). When there is overlap we
// resolve to the narrowest enclosing span — the smallest meaningful unit
// is what the reviewer is clicking the chip to act on.
// ---------------------------------------------------------------------------

export interface SpanGroup {
	span: StructureSpan;
	key: string;
	detections: Detection[];
	pendingDetections: Detection[];
}

export function groupDetectionsBySpan(
	detections: Detection[],
	spans: StructureSpan[],
	kinds: StructureSpanKind[] = ['email_header', 'signature_block']
): SpanGroup[] {
	const relevantSpans = spans.filter((s) => kinds.includes(s.kind));
	if (relevantSpans.length === 0) return [];

	// Sort by narrowest first so when a detection matches multiple spans
	// we assign it to the narrowest one.
	const byWidth = [...relevantSpans].sort(
		(a, b) => a.end_char - a.start_char - (b.end_char - b.start_char)
	);

	const byKey = new Map<string, SpanGroup>();
	for (const span of relevantSpans) {
		byKey.set(spanKey(span), {
			span,
			key: spanKey(span),
			detections: [],
			pendingDetections: []
		});
	}

	for (const detection of detections) {
		for (const span of byWidth) {
			if (detectionInsideSpan(detection, span)) {
				const group = byKey.get(spanKey(span));
				if (!group) continue;
				group.detections.push(detection);
				if (detection.review_status === 'pending') {
					group.pendingDetections.push(detection);
				}
				break;
			}
		}
	}

	// Only return groups that actually contain detections — a span with
	// nothing in it has no useful affordance.
	return Array.from(byKey.values())
		.filter((g) => g.detections.length > 0)
		.sort((a, b) => a.span.start_char - b.span.start_char);
}

// ---------------------------------------------------------------------------
// Name normalization for the same-name sweep.
//
// Lowercase, strip diacritics, collapse internal whitespace. Matches the
// shape the backend `name_engine` uses for reference-name matching, which
// is the pattern the reviewer expects (click "De Vries" on one card →
// the sweep picks up "de vries", "De  Vries", "De Vríes").
// ---------------------------------------------------------------------------

export function normalizeDetectionName(text: string | undefined | null): string {
	if (!text) return '';
	return text
		.normalize('NFKD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLowerCase()
		.replace(/\s+/g, ' ')
		.trim();
}

/**
 * Find every Tier 2 persoon detection whose normalized name matches
 * `target`, including `target` itself. Returns them in the document
 * order the detections list already uses (callers should not re-sort
 * — the undo command captures state in this order and the reverse
 * must mirror it).
 */
export function findSameNameDetections(
	target: Detection,
	all: Detection[]
): Detection[] {
	const normalized = normalizeDetectionName(target.entity_text);
	if (!normalized) return [target];
	return all.filter(
		(d) =>
			d.entity_type === target.entity_type &&
			normalizeDetectionName(d.entity_text) === normalized
	);
}
