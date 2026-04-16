/**
 * Entity-type labels — Dutch-facing strings and badge colors for the
 * redaction log (#19) and anywhere else the UI needs to render a detection
 * type in a human-readable form.
 *
 * Keep in sync with `EntityType` in `$lib/types`.
 */

import type { EntityType } from '$lib/types';

export interface EntityTypeInfo {
	/** Dutch label shown in table cells, filters, and badges. */
	label: string;
	/** Short explanation used in tooltips / detail rows. */
	description: string;
	/** Tailwind classes for the badge pill in the log table. */
	badgeClass: string;
}

export const ENTITY_TYPES: Record<EntityType, EntityTypeInfo> = {
	persoon: {
		label: 'Persoon',
		description: 'Naam van een natuurlijk persoon',
		badgeClass: 'bg-amber-100 text-amber-900'
	},
	bsn: {
		label: 'BSN',
		description: 'Burgerservicenummer',
		badgeClass: 'bg-red-100 text-red-900'
	},
	telefoon: {
		label: 'Telefoon',
		description: 'Telefoon- of mobiel nummer',
		badgeClass: 'bg-blue-100 text-blue-900'
	},
	email: {
		label: 'E-mail',
		description: 'E-mailadres',
		badgeClass: 'bg-blue-100 text-blue-900'
	},
	adres: {
		label: 'Adres',
		description: 'Straatnaam + huisnummer of volledig adres',
		badgeClass: 'bg-emerald-100 text-emerald-900'
	},
	iban: {
		label: 'IBAN',
		description: 'Bankrekeningnummer (IBAN)',
		badgeClass: 'bg-red-100 text-red-900'
	},
	datum: {
		label: 'Datum',
		description: 'Generieke datum',
		badgeClass: 'bg-slate-100 text-slate-900'
	},
	geboortedatum: {
		label: 'Geboortedatum',
		description: 'Geboortedatum',
		badgeClass: 'bg-amber-100 text-amber-900'
	},
	postcode: {
		label: 'Postcode',
		description: 'Nederlandse postcode',
		badgeClass: 'bg-emerald-100 text-emerald-900'
	},
	kenteken: {
		label: 'Kenteken',
		description: 'Voertuigkenteken',
		badgeClass: 'bg-indigo-100 text-indigo-900'
	},
	creditcard: {
		label: 'Creditcard',
		description: 'Creditcardnummer',
		badgeClass: 'bg-red-100 text-red-900'
	},
	kvk: {
		label: 'KvK',
		description: 'KvK-nummer',
		badgeClass: 'bg-violet-100 text-violet-900'
	},
	btw: {
		label: 'BTW',
		description: 'BTW-identificatienummer',
		badgeClass: 'bg-violet-100 text-violet-900'
	},
	url: {
		label: 'URL',
		description: 'Webadres (URL)',
		badgeClass: 'bg-sky-100 text-sky-900'
	},
	organisatie: {
		label: 'Organisatie',
		description: 'Organisatienaam',
		badgeClass: 'bg-blue-100 text-blue-600'
	},
	referentie: {
		label: 'Referentie',
		description: 'Kenmerk- of referentienummer (klantnummer, factuurnummer, dossiernummer, …)',
		badgeClass: 'bg-amber-100 text-amber-900'
	},
	area: {
		label: 'Gebied',
		description: 'Handmatig getekend gebied (handtekening, stempel, scan)',
		badgeClass: 'bg-gray-200 text-gray-800'
	},
	custom: {
		label: 'Zoekterm',
		description: 'Documentspecifieke zoekterm (eigen wordlist)',
		badgeClass: 'bg-teal-100 text-teal-900'
	}
};

/** Form-facing labels used in manual-redaction and search-redact pickers. */
export const ENTITY_FORM_LABELS: Record<EntityType, string> = {
	persoon: 'Persoon (naam)',
	bsn: 'BSN',
	telefoon: 'Telefoonnummer',
	email: 'E-mailadres',
	adres: 'Adres',
	iban: 'IBAN',
	datum: 'Datum',
	geboortedatum: 'Geboortedatum',
	postcode: 'Postcode',
	kenteken: 'Kenteken',
	creditcard: 'Creditcard',
	kvk: 'KvK-nummer',
	btw: 'BTW-nummer',
	url: 'URL',
	organisatie: 'Organisatienaam',
	referentie: 'Referentienummer',
	area: 'Handmatig gebied',
	custom: 'Zoekterm (eigen lijst)'
};

/** Entity types in the order they should appear in filter dropdowns. */
export const ENTITY_TYPE_ORDER: EntityType[] = [
	'persoon',
	'email',
	'telefoon',
	'adres',
	'postcode',
	'bsn',
	'iban',
	'kenteken',
	'geboortedatum',
	'datum',
	'creditcard',
	'kvk',
	'btw',
	'url',
	'organisatie',
	'referentie',
	'area',
	'custom'
];

export function getEntityTypeLabel(type: EntityType): string {
	return ENTITY_TYPES[type]?.label ?? type;
}

export function getEntityTypeBadgeClass(type: EntityType): string {
	return ENTITY_TYPES[type]?.badgeClass ?? 'bg-gray-100 text-gray-900';
}
