/**
 * Review status + detection source labels shared across the review UI and
 * the redaction log (#19). Kept in one place so the log table, the filter
 * bar, and any future oversight surface speak exactly the same language.
 */

import type { DetectionSource, ReviewStatus } from '$lib/types';

export interface StatusInfo {
	label: string;
	/** Tailwind classes for a small status pill. */
	badgeClass: string;
}

export const REVIEW_STATUSES: Record<ReviewStatus, StatusInfo> = {
	pending: {
		label: 'Te beoordelen',
		badgeClass: 'bg-yellow-100 text-yellow-900'
	},
	auto_accepted: {
		label: 'Auto-gelakt',
		badgeClass: 'bg-emerald-50 text-emerald-800'
	},
	accepted: {
		label: 'Geaccepteerd',
		badgeClass: 'bg-emerald-100 text-emerald-900'
	},
	rejected: {
		label: 'Afgewezen',
		badgeClass: 'bg-gray-100 text-gray-700'
	},
	edited: {
		label: 'Bewerkt',
		badgeClass: 'bg-blue-100 text-blue-900'
	},
	deferred: {
		label: 'Uitgesteld',
		badgeClass: 'bg-orange-100 text-orange-900'
	}
};

export const REVIEW_STATUS_ORDER: ReviewStatus[] = [
	'pending',
	'deferred',
	'accepted',
	'auto_accepted',
	'edited',
	'rejected'
];

export function getReviewStatusLabel(status: ReviewStatus): string {
	return REVIEW_STATUSES[status]?.label ?? status;
}

export function getReviewStatusBadgeClass(status: ReviewStatus): string {
	return REVIEW_STATUSES[status]?.badgeClass ?? 'bg-gray-100 text-gray-900';
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

export const DETECTION_SOURCES: Record<DetectionSource, { label: string }> = {
	regex: { label: 'Regex' },
	deduce: { label: 'Deduce NER' },
	manual: { label: 'Handmatig' },
	search_redact: { label: 'Zoek & lak' },
	reference_list: { label: 'Referentielijst' },
	structure: { label: 'Structuur' },
	rule: { label: 'Regel' },
	custom_wordlist: { label: 'Eigen zoektermen' }
};

export function getSourceLabel(source: DetectionSource | undefined | null): string {
	if (!source) return '—';
	return DETECTION_SOURCES[source]?.label ?? source;
}

/** A source is "automatic" (analyzer-generated) iff it is not reviewer-authored. */
export function isAutoSource(source: DetectionSource | undefined | null): boolean {
	return source !== 'manual' && source !== 'search_redact';
}

/**
 * A detection that will produce a black bar in the exported PDF: either
 * confirmed by the reviewer (`accepted`) or auto-redacted by the pipeline
 * (`auto_accepted`, e.g. Tier 1 hard identifiers). Used by export, the
 * redaction log, and card UI to mirror the export pipeline exactly.
 */
export function isAcceptedRedaction(status: ReviewStatus): boolean {
	return status === 'accepted' || status === 'auto_accepted';
}
