/**
 * Debug JSON export — dumps the current document + detections state as
 * a client-side JSON blob for triage and regression hunting.
 *
 * This is a developer/reviewer aid, not a redaction artifact. It lets us
 * paste a fixture PDF alongside its detection dump so we can compare the
 * analyzer's output against the UI and pinpoint false positives/negatives
 * without guessing at internal state.
 *
 * Runs entirely client-side: no new API calls. Everything it writes is
 * already in memory on the review screen.
 */

import type { Detection, Document } from '$lib/types';

export interface DebugExportPayload {
	generated_at: string;
	schema_version: 1;
	document: {
		id: string;
		filename: string;
		page_count: number;
		created_at: string;
		five_year_warning: boolean;
	} | null;
	counts: {
		total: number;
		by_tier: Record<string, number>;
		by_status: Record<string, number>;
	};
	detections: Array<{
		id: string;
		tier: string;
		entity_type: string;
		entity_text: string | null;
		woo_article: string | null;
		confidence: number;
		confidence_level: string | null;
		review_status: string;
		reasoning: string | null;
		source: string | null;
		subject_role: string | null;
		start_char: number | null;
		end_char: number | null;
		bounding_boxes: Array<{
			page: number;
			x0: number;
			y0: number;
			x1: number;
			y1: number;
		}>;
	}>;
}

export function buildDebugExport(
	document: Document | null,
	detections: Detection[]
): DebugExportPayload {
	const byTier: Record<string, number> = {};
	const byStatus: Record<string, number> = {};
	for (const d of detections) {
		byTier[d.tier] = (byTier[d.tier] ?? 0) + 1;
		byStatus[d.review_status] = (byStatus[d.review_status] ?? 0) + 1;
	}

	return {
		generated_at: new Date().toISOString(),
		schema_version: 1,
		document: document
			? {
					id: document.id,
					filename: document.filename,
					page_count: document.page_count,
					created_at: document.created_at,
					five_year_warning: document.five_year_warning
				}
			: null,
		counts: {
			total: detections.length,
			by_tier: byTier,
			by_status: byStatus
		},
		detections: detections.map((d) => ({
			id: d.id,
			tier: d.tier,
			entity_type: d.entity_type,
			entity_text: d.entity_text ?? null,
			woo_article: d.woo_article,
			confidence: d.confidence,
			confidence_level: d.confidence_level ?? null,
			review_status: d.review_status,
			reasoning: d.reasoning,
			source: d.source ?? null,
			subject_role: d.subject_role ?? null,
			start_char: d.start_char ?? null,
			end_char: d.end_char ?? null,
			bounding_boxes: d.bounding_boxes.map((b) => ({
				page: b.page,
				x0: b.x0,
				y0: b.y0,
				x1: b.x1,
				y1: b.y1
			}))
		}))
	};
}

/**
 * Trigger a JSON download in the browser. Uses a blob URL so the bytes
 * never leave the client.
 */
export function downloadDebugExport(
	payload: DebugExportPayload,
	filenameBase: string
): void {
	const json = JSON.stringify(payload, null, 2);
	const blob = new Blob([json], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	const a = globalThis.document.createElement('a');
	a.href = url;
	a.download = `${filenameBase.replace(/\.pdf$/i, '')}.detections.json`;
	globalThis.document.body.appendChild(a);
	a.click();
	globalThis.document.body.removeChild(a);
	URL.revokeObjectURL(url);
}
