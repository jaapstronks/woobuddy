/**
 * Session-state store (#50 — anonymous review-session cache).
 *
 * Persists the slices of review-page state that need to survive a
 * Cmd+R into IndexedDB, keyed by the same `docId` that the PDF lives
 * under in `pdf-store`. The browser is the single place this state
 * exists — the server holds nothing.
 *
 * Each domain store (detections, reference-names, custom-terms,
 * page-reviews) reads its slice on hydrate and writes its slice on
 * mutate via {@link readSessionState} / {@link writeSessionStateSlice}.
 * The whole-record put is one transaction; concurrent updates from
 * different stores serialize through the IDB worker so the last
 * transaction wins for the slice it touches but does not clobber
 * other slices.
 *
 * IDB unavailable (private mode, quota exceeded, blocked by extension):
 * every function resolves to a safe no-op / null. Callers stay on
 * in-memory state and surface a one-time toast at the page level.
 */

import { openWoobuddyDb, SESSION_STATE_STORE as STORE_NAME } from './idb';
import type {
	CustomTerm,
	Detection,
	PageReviewStatus,
	ReferenceName,
	StructureSpan
} from '$lib/types';

/**
 * Whole record stored under one key (the docId). Not used directly by
 * callers — they go through the slice-aware helpers below.
 */
export interface SessionState {
	id: string;
	detections: Detection[];
	structureSpans: StructureSpan[];
	referenceNames: ReferenceName[];
	customTerms: CustomTerm[];
	pageReviews: Record<number, PageReviewStatus>;
	storedAt: number;
}

/** Per-slice patches the domain stores send. */
export type SessionStatePatch = Partial<
	Pick<
		SessionState,
		| 'detections'
		| 'structureSpans'
		| 'referenceNames'
		| 'customTerms'
		| 'pageReviews'
	>
>;

function emptyState(docId: string): SessionState {
	return {
		id: docId,
		detections: [],
		structureSpans: [],
		referenceNames: [],
		customTerms: [],
		pageReviews: {},
		storedAt: Date.now()
	};
}

async function openDb(): Promise<IDBDatabase | null> {
	try {
		return await openWoobuddyDb();
	} catch {
		// IDB blocked / unavailable — surface the failure to the caller as
		// `null` and let domain stores fall back to in-memory only.
		return null;
	}
}

/** Read the whole record for a docId, or `null` if not yet written. */
export async function readSessionState(docId: string): Promise<SessionState | null> {
	const db = await openDb();
	if (!db) return null;
	try {
		return await new Promise<SessionState | null>((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readonly');
			const store = tx.objectStore(STORE_NAME);
			const req = store.get(docId);
			req.onsuccess = () => resolve((req.result as SessionState | undefined) ?? null);
			req.onerror = () => reject(req.error);
		});
	} catch {
		return null;
	} finally {
		db.close();
	}
}

/** Replace the entire record. Used on first hydration after analyze. */
export async function writeSessionState(state: SessionState): Promise<void> {
	const db = await openDb();
	if (!db) return;
	try {
		await new Promise<void>((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readwrite');
			const store = tx.objectStore(STORE_NAME);
			const record: SessionState = { ...state, storedAt: Date.now() };
			const req = store.put(record);
			req.onsuccess = () => resolve();
			req.onerror = () => reject(req.error);
		});
	} catch {
		// Quota / transaction failure — silently degrade. The in-memory
		// store is still authoritative; a refresh will lose this slice
		// but the user can still finish their review and export.
	} finally {
		db.close();
	}
}

/**
 * Merge a slice patch into the existing record. Reads and writes within
 * a single read-write transaction so two concurrent updates from
 * different domain stores cannot drop a slice on the floor.
 */
export async function writeSessionStateSlice(
	docId: string,
	patch: SessionStatePatch
): Promise<void> {
	const db = await openDb();
	if (!db) return;
	try {
		await new Promise<void>((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readwrite');
			const store = tx.objectStore(STORE_NAME);
			const getReq = store.get(docId);
			getReq.onsuccess = () => {
				const existing = (getReq.result as SessionState | undefined) ?? emptyState(docId);
				const next: SessionState = {
					...existing,
					...patch,
					id: docId,
					storedAt: Date.now()
				};
				const putReq = store.put(next);
				putReq.onsuccess = () => resolve();
				putReq.onerror = () => reject(putReq.error);
			};
			getReq.onerror = () => reject(getReq.error);
		});
	} catch {
		// See writeSessionState — degrade silently.
	} finally {
		db.close();
	}
}

export async function deleteSessionState(docId: string): Promise<void> {
	const db = await openDb();
	if (!db) return;
	try {
		await new Promise<void>((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readwrite');
			const store = tx.objectStore(STORE_NAME);
			const req = store.delete(docId);
			req.onsuccess = () => resolve();
			req.onerror = () => reject(req.error);
		});
	} catch {
		// Best-effort delete; nothing to do on failure.
	} finally {
		db.close();
	}
}
