/**
 * Shared IndexedDB schema for WOO Buddy client-first state.
 *
 * Every client-first module that needs persistent browser state opens
 * this DB so the schema and version number stay in one place. Before
 * #49 introduced the OCR extraction cache, `pdf-store` owned the DB
 * alone; splitting it out avoided a version-number race where two
 * modules would try to upgrade the same DB to different versions and
 * one of them would lose with a `VersionError`.
 *
 * ## Object stores
 *
 * - `documents` — uploaded PDF bytes, keyed by `docId` (pdf-store)
 * - `extractions` — OCR ExtractionResult for scanned docs, keyed by
 *   `docId` (extraction-store — #49)
 * - `session-state` — review-session state (detections, structure spans,
 *   reference names, custom terms, page reviews) keyed by `docId`
 *   (session-state-store — #50). Lets a Cmd+R on the review page
 *   preserve the reviewer's accept/reject/manual-redact work without
 *   ever touching the server.
 */

export const DB_NAME = 'woobuddy-pdfs';
export const DB_VERSION = 4;

export const DOCUMENTS_STORE = 'documents';
export const EXTRACTIONS_STORE = 'extractions';
export const SESSION_STATE_STORE = 'session-state';

export class IdbError extends Error {
	constructor(
		message: string,
		public readonly cause?: unknown
	) {
		super(message);
		this.name = 'IdbError';
	}
}

/**
 * Open (or upgrade) the WOO Buddy IndexedDB.
 *
 * The upgrade handler is idempotent and keyed to `event.oldVersion` so
 * that migrating a fresh browser to v3 does the same thing as
 * migrating an existing v2 browser to v3, without losing any data
 * users have already persisted.
 */
export function openWoobuddyDb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);

		request.onupgradeneeded = (event) => {
			const db = request.result;
			const oldVersion = event.oldVersion;

			// v0 → v1/v2: recreate documents from scratch. The original
			// schema carried a dossierId index that we no longer use;
			// dropping and recreating is safe because v1/v2 only ever
			// held a single in-flight upload and nothing cross-session
			// depended on surviving the migration.
			if (oldVersion < 2) {
				if (db.objectStoreNames.contains(DOCUMENTS_STORE)) {
					db.deleteObjectStore(DOCUMENTS_STORE);
				}
				db.createObjectStore(DOCUMENTS_STORE, { keyPath: 'id' });
			}

			// v2 → v3: add the OCR extraction cache (#49). Preserve the
			// documents store untouched — a user upgrading mid-session
			// must not lose the PDF they already uploaded.
			if (oldVersion < 3) {
				if (!db.objectStoreNames.contains(DOCUMENTS_STORE)) {
					db.createObjectStore(DOCUMENTS_STORE, { keyPath: 'id' });
				}
				if (!db.objectStoreNames.contains(EXTRACTIONS_STORE)) {
					db.createObjectStore(EXTRACTIONS_STORE, { keyPath: 'id' });
				}
			}

			// v3 → v4: add the review-session state cache (#50). Same
			// shape as the others — keyPath `id` (the docId). On
			// downgrade users would lose this state; we accept that
			// since the data is review-session scoped and the user
			// can re-analyze from the still-cached PDF.
			if (oldVersion < 4) {
				if (!db.objectStoreNames.contains(SESSION_STATE_STORE)) {
					db.createObjectStore(SESSION_STATE_STORE, { keyPath: 'id' });
				}
			}
		};

		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(new IdbError('Failed to open IndexedDB', request.error));
	});
}
