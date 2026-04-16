/**
 * IndexedDB cache for OCR'd ExtractionResult (#49).
 *
 * When a user accepts the OCR opt-in, running tesseract on a 20-page
 * scan takes 30–90 seconds. The review page runs its own extract pass
 * on load (to hydrate `entity_text` via `bbox-text-resolver`), so
 * without a cache the user would pay the OCR cost again on every page
 * reload. We stash the `ExtractionResult` here keyed by `docId`; the
 * review page consults it before falling back to the pdf.js
 * text-layer path.
 */
import type { ExtractionResult } from '$lib/types';
import { openWoobuddyDb, EXTRACTIONS_STORE } from './idb';

interface StoredExtraction {
	id: string;
	extraction: ExtractionResult;
	storedAt: number;
}

export async function storeExtraction(
	docId: string,
	extraction: ExtractionResult
): Promise<void> {
	const db = await openWoobuddyDb();
	try {
		return await new Promise<void>((resolve, reject) => {
			const tx = db.transaction(EXTRACTIONS_STORE, 'readwrite');
			const store = tx.objectStore(EXTRACTIONS_STORE);
			const record: StoredExtraction = {
				id: docId,
				extraction,
				storedAt: Date.now()
			};
			const request = store.put(record);
			request.onsuccess = () => resolve();
			request.onerror = () => reject(request.error);
		});
	} finally {
		db.close();
	}
}

export async function getExtraction(docId: string): Promise<ExtractionResult | null> {
	const db = await openWoobuddyDb();
	try {
		return await new Promise<ExtractionResult | null>((resolve, reject) => {
			const tx = db.transaction(EXTRACTIONS_STORE, 'readonly');
			const store = tx.objectStore(EXTRACTIONS_STORE);
			const request = store.get(docId);
			request.onsuccess = () => {
				const record = request.result as StoredExtraction | undefined;
				resolve(record?.extraction ?? null);
			};
			request.onerror = () => reject(request.error);
		});
	} finally {
		db.close();
	}
}

export async function deleteExtraction(docId: string): Promise<void> {
	const db = await openWoobuddyDb();
	try {
		return await new Promise<void>((resolve, reject) => {
			const tx = db.transaction(EXTRACTIONS_STORE, 'readwrite');
			const store = tx.objectStore(EXTRACTIONS_STORE);
			const request = store.delete(docId);
			request.onsuccess = () => resolve();
			request.onerror = () => reject(request.error);
		});
	} finally {
		db.close();
	}
}
