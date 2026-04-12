import { PUBLIC_API_URL } from '$env/static/public';
import type {
	Document,
	Detection,
	UpdateDetectionRequest,
	PageExtraction
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

export async function analyzeDocument(
	documentId: string,
	pages: PageExtraction[]
): Promise<{ document_id: string; detection_count: number; page_count: number }> {
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
			}))
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
