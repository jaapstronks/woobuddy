/**
 * IndexedDB-based PDF storage for client-first architecture.
 *
 * PDFs never leave the browser. This service persists them in IndexedDB
 * so they survive page reloads within a session.
 */

const DB_NAME = 'woobuddy-pdfs';
const DB_VERSION = 2;
const STORE_NAME = 'documents';

export interface StoredPdf {
	id: string;
	filename: string;
	pdfBytes: ArrayBuffer;
	storedAt: number;
}

export class PdfStoreError extends Error {
	constructor(
		message: string,
		public readonly cause?: unknown
	) {
		super(message);
		this.name = 'PdfStoreError';
	}
}

function openDb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);

		request.onupgradeneeded = () => {
			const db = request.result;
			// Drop and recreate: old schema had a dossierId index we no longer use.
			if (db.objectStoreNames.contains(STORE_NAME)) {
				db.deleteObjectStore(STORE_NAME);
			}
			db.createObjectStore(STORE_NAME, { keyPath: 'id' });
		};

		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(new PdfStoreError('Failed to open IndexedDB', request.error));
	});
}

/**
 * Check whether there is enough room to store `incomingBytes` in IndexedDB
 * and throw a friendly error if not. This is advisory: `navigator.storage`
 * reports a coarse estimate, so we keep a generous safety margin. The real
 * `QuotaExceededError` handler below remains as a last-resort fallback.
 */
async function assertStorageAvailable(incomingBytes: number): Promise<void> {
	if (!navigator.storage?.estimate) return;
	let estimate: StorageEstimate;
	try {
		estimate = await navigator.storage.estimate();
	} catch {
		return; // treat unknown as "probably fine" — the real write will still error out
	}
	const usage = estimate.usage ?? 0;
	const quota = estimate.quota ?? 0;
	if (quota === 0) return;
	const safetyMargin = 10 * 1024 * 1024; // 10 MB buffer for other IDB data
	if (usage + incomingBytes + safetyMargin > quota) {
		throw new PdfStoreError(
			'Onvoldoende opslagruimte in de browser. Sluit andere tabbladen of verwijder het vorige document in WOO Buddy voordat je verder gaat.'
		);
	}
}

export async function storePdf(
	docId: string,
	filename: string,
	pdfBytes: ArrayBuffer
): Promise<void> {
	await assertStorageAvailable(pdfBytes.byteLength);
	const db = await openDb();
	try {
		const record: StoredPdf = {
			id: docId,
			filename,
			pdfBytes,
			storedAt: Date.now()
		};

		return await new Promise((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readwrite');
			const store = tx.objectStore(STORE_NAME);
			const request = store.put(record);

			request.onsuccess = () => resolve();
			request.onerror = () => {
				const error = request.error;
				if (error?.name === 'QuotaExceededError') {
					reject(
						new PdfStoreError(
							'Onvoldoende opslagruimte in de browser. Verwijder ongebruikte documenten.',
							error
						)
					);
				} else {
					reject(new PdfStoreError('Failed to store PDF', error));
				}
			};
		});
	} finally {
		db.close();
	}
}

export async function getPdf(docId: string): Promise<StoredPdf | null> {
	const db = await openDb();
	try {
		return await new Promise((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readonly');
			const store = tx.objectStore(STORE_NAME);
			const request = store.get(docId);

			request.onsuccess = () => resolve(request.result ?? null);
			request.onerror = () => reject(new PdfStoreError('Failed to read PDF', request.error));
		});
	} finally {
		db.close();
	}
}

export async function deletePdf(docId: string): Promise<void> {
	const db = await openDb();
	try {
		return await new Promise((resolve, reject) => {
			const tx = db.transaction(STORE_NAME, 'readwrite');
			const store = tx.objectStore(STORE_NAME);
			const request = store.delete(docId);

			request.onsuccess = () => resolve();
			request.onerror = () => reject(new PdfStoreError('Failed to delete PDF', request.error));
		});
	} finally {
		db.close();
	}
}

export async function getStorageEstimate(): Promise<{
	usage: number;
	quota: number;
	percentUsed: number;
} | null> {
	if (!navigator.storage?.estimate) return null;
	const estimate = await navigator.storage.estimate();
	const usage = estimate.usage ?? 0;
	const quota = estimate.quota ?? 0;
	return {
		usage,
		quota,
		percentUsed: quota > 0 ? (usage / quota) * 100 : 0
	};
}
