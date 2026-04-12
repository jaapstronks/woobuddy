import { PUBLIC_API_URL } from '$env/static/public';
import type {
	Dossier,
	DossierWithStats,
	Document,
	Detection,
	CreateDossierRequest,
	UpdateDetectionRequest,
	PublicOfficial
} from '$lib/types';

const BASE = PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const isFormData = options?.body instanceof FormData;
	const res = await fetch(`${BASE}${path}`, {
		headers: isFormData ? options?.headers : { 'Content-Type': 'application/json', ...options?.headers },
		...options
	});
	if (!res.ok) {
		const body = await res.text();
		throw new Error(`API ${res.status}: ${body}`);
	}
	return res.json();
}

// ---------------------------------------------------------------------------
// Dossiers
// ---------------------------------------------------------------------------

export async function createDossier(data: CreateDossierRequest): Promise<Dossier> {
	return request('/api/dossiers', {
		method: 'POST',
		body: JSON.stringify(data)
	});
}

export async function listDossiers(): Promise<Dossier[]> {
	return request('/api/dossiers');
}

export async function getDossier(id: string): Promise<DossierWithStats> {
	return request(`/api/dossiers/${id}`);
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function uploadDocuments(dossierId: string, files: File[]): Promise<Document[]> {
	const formData = new FormData();
	for (const file of files) {
		formData.append('files', file);
	}
	return request(`/api/dossiers/${dossierId}/documents`, {
		method: 'POST',
		body: formData
	});
}

export async function getDocument(id: string): Promise<Document> {
	return request(`/api/documents/${id}`);
}

export function getDocumentPdfUrl(id: string): string {
	return `${BASE}/api/documents/${id}/pdf`;
}

// ---------------------------------------------------------------------------
// Detections
// ---------------------------------------------------------------------------

export async function triggerDetection(documentId: string): Promise<void> {
	await request(`/api/documents/${documentId}/detect`, { method: 'POST' });
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

export async function propagateName(detectionId: string): Promise<Detection[]> {
	return request(`/api/detections/${detectionId}/propagate`, { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Public officials
// ---------------------------------------------------------------------------

export async function uploadOfficials(dossierId: string, file: File): Promise<PublicOfficial[]> {
	const formData = new FormData();
	formData.append('file', file);
	return request(`/api/dossiers/${dossierId}/officials`, {
		method: 'POST',
		body: formData
	});
}

export async function getOfficials(dossierId: string): Promise<PublicOfficial[]> {
	return request(`/api/dossiers/${dossierId}/officials`);
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export function getExportDownloadUrl(dossierId: string): string {
	return `${BASE}/api/dossiers/${dossierId}/export/download`;
}

export function getMotivationReportUrl(dossierId: string): string {
	return `${BASE}/api/dossiers/${dossierId}/motivation-report`;
}
