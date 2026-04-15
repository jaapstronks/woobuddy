import { PUBLIC_API_URL } from '$env/static/public';
import type {
	Document,
	Detection,
	UpdateDetectionRequest,
	PageExtraction,
	BoundingBox,
	CustomTerm,
	EntityType,
	DetectionTier,
	ReferenceName,
	ReferenceRoleHint,
	StructureSpan,
	WooArticleCode
} from '$lib/types';

const BASE = PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * Typed API error so callers can distinguish transport problems (retryable,
 * offer a retry button) from backend errors (show the message as-is).
 */
export class ApiError extends Error {
	constructor(
		message: string,
		public readonly kind: 'network' | 'server' | 'client',
		public readonly status?: number
	) {
		super(message);
		this.name = 'ApiError';
	}

	get isRetryable(): boolean {
		// Transport failures and transient upstream errors are retryable; 4xx is not.
		return this.kind === 'network' || (this.status !== undefined && this.status >= 500);
	}
}

const RETRY_DELAY_MS = 2000;

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

async function requestOnce<T>(path: string, options?: RequestInit): Promise<T> {
	let res: Response;
	try {
		res = await fetch(`${BASE}${path}`, {
			headers: { 'Content-Type': 'application/json', ...options?.headers },
			...options
		});
	} catch (cause) {
		// `fetch` throws a TypeError for DNS, connection-refused, CORS, offline, etc.
		throw new ApiError(
			'Kan geen verbinding maken met de server. Controleer je internetverbinding.',
			'network'
		);
	}

	if (!res.ok) {
		const body = await res.text();
		const kind = res.status >= 500 ? 'server' : 'client';
		throw new ApiError(body || `API ${res.status}`, kind, res.status);
	}
	// 204 No Content: no body to parse. Caller receives `undefined as T`.
	if (res.status === 204) return undefined as T;
	return res.json();
}

/**
 * Perform a JSON API request with a single retry for transient failures.
 *
 * Retries are attempted once after a 2 s delay if the first attempt raises a
 * network error or a 5xx response. 4xx responses are never retried — they
 * indicate the client needs to change the request, not try again.
 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
	try {
		return await requestOnce<T>(path, options);
	} catch (error) {
		if (error instanceof ApiError && error.isRetryable) {
			await sleep(RETRY_DELAY_MS);
			return await requestOnce<T>(path, options);
		}
		throw error;
	}
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function registerDocument(
	filename: string,
	pageCount: number
): Promise<Document> {
	return request('/api/documents', {
		method: 'POST',
		body: JSON.stringify({ filename, page_count: pageCount })
	});
}

export async function getDocument(id: string): Promise<Document> {
	return request(`/api/documents/${id}`);
}

// ---------------------------------------------------------------------------
// Detections
// ---------------------------------------------------------------------------

export interface AnalyzeResponse {
	document_id: string;
	detection_count: number;
	page_count: number;
	status?: string;
	/**
	 * Structural regions (email headers, signature blocks, salutations)
	 * produced by the server-side structure engine (#14). Ephemeral:
	 * wired for #20 bulk-sweep affordances and #15 Tier 2 card context.
	 */
	structure_spans: StructureSpan[];
}

export interface AnalyzeCustomTermPayload {
	term: string;
	match_mode?: 'exact';
	woo_article?: string;
}

export async function analyzeDocument(
	documentId: string,
	pages: PageExtraction[],
	referenceNames: string[] = [],
	customTerms: AnalyzeCustomTermPayload[] = []
): Promise<AnalyzeResponse> {
	return request('/api/analyze', {
		method: 'POST',
		body: JSON.stringify({
			document_id: documentId,
			pages: pages.map((p) => ({
				page_number: p.pageNumber,
				full_text: p.fullText,
				text_items: p.textItems.map((ti) => ({
					text: ti.text,
					x0: ti.x0,
					y0: ti.y0,
					x1: ti.x1,
					y1: ti.y1
				}))
			})),
			// #17 — per-document reference list. The server normalizes these
			// before matching, so the frontend sends the original display
			// strings; duplicates or case-mismatches are tolerated.
			reference_names: referenceNames,
			// #21 — per-document custom wordlist. Opposite direction from the
			// reference list: these terms MUST be redacted. The server scans
			// the full text for every occurrence.
			custom_terms: customTerms
		})
	});
}

export async function getDetections(documentId: string): Promise<Detection[]> {
	return request(`/api/documents/${documentId}/detections`);
}

export async function updateDetection(id: string, data: UpdateDetectionRequest): Promise<Detection> {
	return request(`/api/detections/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(data)
	});
}

export interface CreateManualDetectionRequest {
	document_id: string;
	entity_type: EntityType;
	tier: DetectionTier;
	woo_article?: WooArticleCode;
	bounding_boxes: BoundingBox[];
	motivation_text?: string;
	/**
	 * "manual" for single text/area selections (#06/#07), "search_redact"
	 * for bulk-applied search hits (#09). The backend tags the row so audit
	 * logs can distinguish the two flows. Defaults to "manual" server-side.
	 */
	source?: 'manual' | 'search_redact';
}

/**
 * Create a reviewer-authored ("manual") detection.
 *
 * Client-first: only bounding boxes and metadata are sent. The selected
 * text itself stays in the browser — the server persists no `entity_text`.
 */
export async function createManualDetection(
	data: CreateManualDetectionRequest
): Promise<Detection> {
	return request('/api/detections', {
		method: 'POST',
		body: JSON.stringify(data)
	});
}

/**
 * Delete a reviewer-authored detection (used by the undo stack).
 *
 * The server rejects this for non-manual detections — undoing an auto
 * detection flips its `review_status` back via PATCH instead.
 */
export async function deleteDetection(id: string): Promise<void> {
	await request<void>(`/api/detections/${id}`, { method: 'DELETE' });
}

/**
 * Split a detection into two halves (#18).
 *
 * The client has resolved the split point against its local text layer
 * and sends the two resulting bbox sets. The server creates two new
 * manual-source detections inheriting the original's metadata and
 * deletes the original as part of the same operation.
 */
export async function splitDetection(
	id: string,
	bboxesA: BoundingBox[],
	bboxesB: BoundingBox[]
): Promise<Detection[]> {
	return request(`/api/detections/${id}/split`, {
		method: 'POST',
		body: JSON.stringify({ bboxes_a: bboxesA, bboxes_b: bboxesB })
	});
}

/**
 * Merge two or more detections into one (#18).
 *
 * The server concatenates the inputs' bboxes in list order, creates a
 * new manual-source detection inheriting metadata from the *first* id in
 * the list, and deletes the inputs. All ids must belong to the same
 * document; the server enforces this.
 */
export async function mergeDetections(ids: string[]): Promise<Detection> {
	return request('/api/detections/merge', {
		method: 'POST',
		body: JSON.stringify({ detection_ids: ids })
	});
}

// ---------------------------------------------------------------------------
// Page reviews (#10 — page completeness)
// ---------------------------------------------------------------------------

export type PageReviewStatus = 'unreviewed' | 'in_progress' | 'complete' | 'flagged';

export interface PageReview {
	id: string;
	document_id: string;
	page_number: number;
	status: PageReviewStatus;
	reviewer_id: string | null;
	updated_at: string;
}

export async function getPageReviews(documentId: string): Promise<PageReview[]> {
	return request(`/api/documents/${documentId}/page-reviews`);
}

export async function upsertPageReview(
	documentId: string,
	pageNumber: number,
	status: PageReviewStatus
): Promise<PageReview> {
	return request(`/api/documents/${documentId}/page-reviews/${pageNumber}`, {
		method: 'PUT',
		body: JSON.stringify({ status })
	});
}

// ---------------------------------------------------------------------------
// Reference names (#17 — per-document "niet lakken" list)
// ---------------------------------------------------------------------------

export async function getReferenceNames(documentId: string): Promise<ReferenceName[]> {
	return request(`/api/documents/${documentId}/reference-names`);
}

export async function createReferenceName(
	documentId: string,
	displayName: string,
	roleHint: ReferenceRoleHint = 'publiek_functionaris'
): Promise<ReferenceName> {
	return request(`/api/documents/${documentId}/reference-names`, {
		method: 'POST',
		body: JSON.stringify({ display_name: displayName, role_hint: roleHint })
	});
}

export async function deleteReferenceName(
	documentId: string,
	nameId: string
): Promise<void> {
	await request<void>(`/api/documents/${documentId}/reference-names/${nameId}`, {
		method: 'DELETE'
	});
}

// ---------------------------------------------------------------------------
// Custom terms (#21 — per-document "eigen zoektermen")
// ---------------------------------------------------------------------------

export async function getCustomTerms(documentId: string): Promise<CustomTerm[]> {
	return request(`/api/documents/${documentId}/custom-terms`);
}

export async function createCustomTerm(
	documentId: string,
	term: string,
	wooArticle: string = '5.1.2e'
): Promise<CustomTerm> {
	return request(`/api/documents/${documentId}/custom-terms`, {
		method: 'POST',
		body: JSON.stringify({ term, match_mode: 'exact', woo_article: wooArticle })
	});
}

export async function deleteCustomTerm(
	documentId: string,
	termId: string
): Promise<void> {
	await request<void>(`/api/documents/${documentId}/custom-terms/${termId}`, {
		method: 'DELETE'
	});
}

// ---------------------------------------------------------------------------
// Leads (#45 — public email capture)
// ---------------------------------------------------------------------------

export type LeadSource = 'landing' | 'post-export';

export interface LeadPayload {
	email: string;
	name?: string;
	organization?: string;
	message?: string;
	source: LeadSource;
	consent: boolean;
}

/**
 * Submit the public lead-capture form.
 *
 * Returns normally on both fresh inserts and duplicate submissions — the
 * backend is deliberately opaque about which of the two happened so the
 * form cannot be used to probe membership of the list.
 */
export async function submitLead(payload: LeadPayload): Promise<void> {
	await request<{ ok: boolean }>('/api/leads', {
		method: 'POST',
		body: JSON.stringify(payload)
	});
}
