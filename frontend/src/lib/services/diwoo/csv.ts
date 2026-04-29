/**
 * Redaction-log CSV builder for the publication bundle (#52).
 *
 * Mirrors the redaction log table (#19) — entity type, tier, article,
 * status, source, motivation, dates — *without* any entity text, since
 * the server doesn't store it (client-first architecture). If todo #31
 * later builds a richer inventory that includes locally-extracted
 * passages, this file is its happy path: replace the row builder with
 * the inventory's, keep the CSV plumbing.
 */

import type { Detection } from '$lib/types';
import { ENTITY_TYPES } from '$lib/utils/entity-types';
import { WOO_ARTICLES } from '$lib/utils/woo-articles';
import { isAcceptedRedaction } from '$lib/utils/review-status';

const HEADERS = [
	'#',
	'pagina',
	'type',
	'trap',
	'woo_artikel',
	'grond',
	'status',
	'bron',
	'beoordeeld_op',
	'bbox_count',
	'motivatie'
];

function escapeCsv(value: string | number | null | undefined): string {
	if (value === null || value === undefined) return '';
	const s = String(value);
	if (s.includes('"') || s.includes(',') || s.includes('\n') || s.includes('\r')) {
		return `"${s.replace(/"/g, '""')}"`;
	}
	return s;
}

/**
 * Build a generic per-row motivation string. Mirrors the language used
 * elsewhere in the app — Dutch, anchored on the Woo article ground.
 */
function motivationFor(detection: Detection): string {
	if (!detection.woo_article) {
		return 'Geen Woo-artikel gekoppeld';
	}
	const article = WOO_ARTICLES[detection.woo_article];
	if (!article) return `Art. ${detection.woo_article}`;
	return `Art. ${article.code} — ${article.ground}`;
}

export function buildRedactionLogCsv(detections: Detection[]): string {
	const accepted = detections.filter((d) => isAcceptedRedaction(d.review_status));

	const rows: string[] = [];
	rows.push(HEADERS.join(','));

	accepted.forEach((d, idx) => {
		const page = d.bounding_boxes[0]?.page ?? '';
		const entity = ENTITY_TYPES[d.entity_type]?.label ?? d.entity_type;
		const articleCode = d.woo_article ?? '';
		const article = d.woo_article ? WOO_ARTICLES[d.woo_article] : null;
		rows.push(
			[
				escapeCsv(idx + 1),
				escapeCsv(page),
				escapeCsv(entity),
				escapeCsv(d.tier),
				escapeCsv(articleCode),
				escapeCsv(article?.ground ?? ''),
				escapeCsv(d.review_status),
				escapeCsv(d.source ?? ''),
				escapeCsv(d.reviewed_at ?? ''),
				escapeCsv(d.bounding_boxes.length),
				escapeCsv(motivationFor(d))
			].join(',')
		);
	});

	return rows.join('\n') + '\n';
}
