import type { DetectionTier, ConfidenceLevel } from '$lib/types';

export interface TierInfo {
	tier: DetectionTier;
	label: string;
	description: string;
	defaultState: string;
	userAction: string;
	color: string;
}

export const TIERS: Record<DetectionTier, TierInfo> = {
	'1': {
		tier: '1',
		label: 'Harde identifiers',
		description: 'BSN, IBAN, telefoonnummers, e-mailadressen — automatisch herkend met hoge zekerheid',
		defaultState: 'Automatisch gelakt',
		userAction: 'Ontlakken indien nodig',
		color: 'var(--color-neutral)'
	},
	'2': {
		tier: '2',
		label: 'Contextafhankelijke persoonsgegevens',
		description: 'Namen, adressen, functies — herkend maar context bepaalt of lakken nodig is',
		defaultState: 'Voorgesteld (gemarkeerd)',
		userAction: 'Bevestigen of afwijzen',
		color: 'var(--color-warning)'
	},
	'3': {
		tier: '3',
		label: 'Inhoudelijke beoordeling',
		description: 'Beleidsopvattingen, bedrijfsgegevens, toezichtinformatie — menselijke beoordeling vereist',
		defaultState: 'Geannoteerd (gesignaleerd)',
		userAction: 'Beoordelen met beslisondersteuning',
		color: 'var(--color-primary)'
	}
};

export function confidenceToLevel(confidence: number): ConfidenceLevel {
	if (confidence >= 0.85) return 'high';
	if (confidence >= 0.6) return 'medium';
	return 'low';
}
