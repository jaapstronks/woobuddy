/**
 * Pure helpers that compute the counts and per-row records the
 * onderbouwingsrapport (#64) prints. Lives outside `report.ts` so
 * unit tests can exercise the data shaping without pulling in
 * pdf-lib.
 *
 * Client-first reminder: this file deliberately ignores
 * `entity_text`. The report tells the recipient *why* a black bar
 * exists, never *what* sat behind it.
 */

import type { Detection, DetectionTier, ReviewStatus, WooArticleCode } from '$lib/types';
import { ENTITY_TYPES } from '$lib/utils/entity-types';
import { WOO_ARTICLES } from '$lib/utils/woo-articles';
import { isAutoSource, getSourceLabel, isAcceptedRedaction } from '$lib/utils/review-status';

/**
 * Detection rows that end up on the report. Mirrors the export
 * pipeline (`accepted` + `auto_accepted` only) so the report and the
 * actual gelakte PDF describe exactly the same set of black bars.
 */
export function selectReportableDetections(detections: Detection[]): Detection[] {
	const reportable = detections.filter((d) => isAcceptedRedaction(d.review_status));
	reportable.sort((a, b) => {
		const pa = a.bounding_boxes[0]?.page ?? Number.MAX_SAFE_INTEGER;
		const pb = b.bounding_boxes[0]?.page ?? Number.MAX_SAFE_INTEGER;
		if (pa !== pb) return pa - pb;
		const ya = a.bounding_boxes[0]?.y0 ?? 0;
		const yb = b.bounding_boxes[0]?.y0 ?? 0;
		if (ya !== yb) return ya - yb;
		return a.id.localeCompare(b.id);
	});
	return reportable;
}

export interface ReportRow {
	number: number;
	page: number;
	entityLabel: string;
	tier: DetectionTier;
	articleCode: WooArticleCode | null;
	source: 'auto' | 'handmatig';
	sourceLabel: string;
	motivation: string;
}

export interface ReportSummary {
	total: number;
	byArticle: Array<{ code: WooArticleCode; count: number }>;
	byTier: Record<DetectionTier, number>;
	bySource: { auto: number; handmatig: number };
	byEntityType: Array<{ label: string; count: number }>;
}

/**
 * Templated Dutch motivation, keyed off the Woo-article. Falls back
 * to a generic phrase when no article is set so the column never
 * reads empty in the printed table.
 */
export function motivationFor(detection: Detection): string {
	if (!detection.woo_article) {
		return 'Geen Woo-grond gekoppeld — handmatig vastgesteld';
	}
	const article = WOO_ARTICLES[detection.woo_article];
	if (!article) return `Art. ${detection.woo_article}`;
	return `Art. ${article.code} — ${article.ground}`;
}

export function buildReportRows(detections: Detection[]): ReportRow[] {
	const reportable = selectReportableDetections(detections);
	return reportable.map((d, idx): ReportRow => {
		const page = (d.bounding_boxes[0]?.page ?? -1) + 1;
		const entity = ENTITY_TYPES[d.entity_type]?.label ?? d.entity_type;
		const auto = isAutoSource(d.source);
		return {
			number: idx + 1,
			page,
			entityLabel: entity,
			tier: d.tier,
			articleCode: d.woo_article,
			source: auto ? 'auto' : 'handmatig',
			sourceLabel: getSourceLabel(d.source),
			motivation: motivationFor(d)
		};
	});
}

export function buildReportSummary(detections: Detection[]): ReportSummary {
	const reportable = selectReportableDetections(detections);
	const byTier: Record<DetectionTier, number> = { '1': 0, '2': 0, '3': 0 };
	const byArticleMap = new Map<WooArticleCode, number>();
	const byEntityMap = new Map<string, number>();
	let auto = 0;
	let handmatig = 0;
	for (const d of reportable) {
		byTier[d.tier] = (byTier[d.tier] ?? 0) + 1;
		if (d.woo_article) {
			byArticleMap.set(d.woo_article, (byArticleMap.get(d.woo_article) ?? 0) + 1);
		}
		const entity = ENTITY_TYPES[d.entity_type]?.label ?? d.entity_type;
		byEntityMap.set(entity, (byEntityMap.get(entity) ?? 0) + 1);
		if (isAutoSource(d.source)) auto++;
		else handmatig++;
	}
	const byArticle = Array.from(byArticleMap.entries())
		.map(([code, count]) => ({ code, count }))
		.sort((a, b) => a.code.localeCompare(b.code));
	const byEntityType = Array.from(byEntityMap.entries())
		.map(([label, count]) => ({ label, count }))
		.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
	return {
		total: reportable.length,
		byArticle,
		byTier,
		bySource: { auto, handmatig },
		byEntityType
	};
}

/**
 * Articles that should appear in Bijlage A — the per-Woo-grond
 * toelichting block. We include every article that shows up at
 * least once in the table, in code order.
 */
export function articlesForToelichting(rows: ReportRow[]): WooArticleCode[] {
	const present = new Set<WooArticleCode>();
	for (const row of rows) {
		if (row.articleCode) present.add(row.articleCode);
	}
	return Array.from(present).sort((a, b) => a.localeCompare(b));
}

/** Status labels used in the cover summary line. */
export function reportStatusBreakdown(detections: Detection[]): {
	reviewable: number;
	rejected: number;
	pending: number;
	deferred: number;
} {
	const counts: Record<ReviewStatus, number> = {
		pending: 0,
		auto_accepted: 0,
		accepted: 0,
		rejected: 0,
		edited: 0,
		deferred: 0
	};
	for (const d of detections) counts[d.review_status]++;
	return {
		reviewable: counts.accepted + counts.auto_accepted + counts.edited,
		rejected: counts.rejected,
		pending: counts.pending,
		deferred: counts.deferred
	};
}
