import type { DossierStatus } from '$lib/types';

export const DOSSIER_STATUS_LABELS: Record<DossierStatus, { label: string; color: string }> = {
	open: { label: 'Open', color: 'bg-blue-100 text-blue-700' },
	in_review: { label: 'In review', color: 'bg-amber-100 text-amber-700' },
	completed: { label: 'Afgerond', color: 'bg-green-100 text-green-700' }
};
