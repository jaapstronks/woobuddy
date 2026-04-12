import type { ConfidenceLevel } from '$lib/types';

export const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
	high: 'Hoog',
	medium: 'Gemiddeld',
	low: 'Laag'
};

export const CONFIDENCE_COLORS: Record<ConfidenceLevel, string> = {
	high: 'var(--color-success)',
	medium: 'var(--color-warning)',
	low: 'var(--color-danger)'
};
