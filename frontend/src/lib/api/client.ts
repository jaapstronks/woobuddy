import { PUBLIC_API_URL } from '$env/static/public';
import type { Detection, PageExtraction, StructureSpan } from '$lib/types';

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
	} catch {
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

const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']);

/**
 * Perform a JSON API request with a single retry for transient failures.
 *
 * Retries only fire on idempotent methods (GET/HEAD/OPTIONS/PUT/DELETE). Non-
 * idempotent POSTs would double-execute on a transient gateway error if
 * retried, so they surface the first failure to the caller instead.
 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
	try {
		return await requestOnce<T>(path, options);
	} catch (error) {
		const method = (options?.method ?? 'GET').toUpperCase();
		const canRetry =
			error instanceof ApiError && error.isRetryable && IDEMPOTENT_METHODS.has(method);
		if (canRetry) {
			await sleep(RETRY_DELAY_MS);
			return await requestOnce<T>(path, options);
		}
		throw error;
	}
}

// ---------------------------------------------------------------------------
// Analyze (#50 — anonymous mode)
//
// The hosted tier launches without authentication, so every analyze call
// from the public landing-page upload flow is anonymous: no document_id,
// detections returned inline with server-generated UUIDs, zero DB writes.
// The save-mode (with document_id) on the backend stays in-tree for the
// future authenticated save flow but has no caller in this codebase.
// ---------------------------------------------------------------------------

export interface AnalyzeResponse {
	/**
	 * Server-generated session UUID — never corresponds to a Postgres row.
	 * Callers use it as a local key in IndexedDB / in-memory state.
	 */
	document_id: string;
	detection_count: number;
	page_count: number;
	status?: string;
	/**
	 * Full detection list with server-generated UUIDs. The list is the
	 * single source of truth for the review session — no follow-up GET is
	 * required (and would 404 anyway, since the document was never
	 * registered).
	 */
	detections: Detection[];
	/**
	 * Structural regions (email headers, signature blocks, salutations)
	 * produced by the server-side structure engine (#14). Wired for #20
	 * bulk-sweep affordances and #15 Tier 2 card context.
	 */
	structure_spans: StructureSpan[];
}

export interface AnalyzeCustomTermPayload {
	term: string;
	match_mode?: 'exact';
	woo_article?: string;
}

/**
 * Run the rule-based detection pipeline on client-extracted text.
 *
 * The text is processed ephemerally on the server (#00 client-first
 * architecture) — never logged, never stored. The full detection list
 * comes back inline.
 */
export async function analyzeDocument(
	pages: PageExtraction[],
	referenceNames: string[] = [],
	customTerms: AnalyzeCustomTermPayload[] = []
): Promise<AnalyzeResponse> {
	return request('/api/analyze', {
		method: 'POST',
		body: JSON.stringify({
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

// ---------------------------------------------------------------------------
// Leads (#45 — public contact form)
// ---------------------------------------------------------------------------

export type LeadSource = 'landing' | 'post-export';

export interface LeadPayload {
	email: string;
	name?: string;
	organization?: string;
	message?: string;
	source: LeadSource;
	newsletterOptIn: boolean;
}

/**
 * Submit the public contact form.
 *
 * Every submission triggers a transactional email to the operator. If
 * `newsletterOptIn` is true, the contact is also added to the Brevo
 * newsletter list. The backend is deliberately opaque about list-state
 * so duplicate submissions cannot be used to probe membership.
 */
export async function submitLead(payload: LeadPayload): Promise<void> {
	const { newsletterOptIn, ...rest } = payload;
	await request<{ ok: boolean }>('/api/leads', {
		method: 'POST',
		body: JSON.stringify({ ...rest, newsletter_opt_in: newsletterOptIn })
	});
}
