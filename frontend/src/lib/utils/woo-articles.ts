import type { WooArticleCode, DetectionTier, EntityType } from '$lib/types';

export interface WooArticle {
	code: WooArticleCode;
	ground: string;
	description: string;
	type: 'absolute' | 'relative' | 'special' | 'residual';
	tier: DetectionTier;
}

export const WOO_ARTICLES: Record<WooArticleCode, WooArticle> = {
	'5.1.1c': {
		code: '5.1.1c',
		ground: 'Bedrijfs- en fabricagegegevens (vertrouwelijk verstrekt)',
		description: 'Vertrouwelijk aan de overheid verstrekte bedrijfsgegevens',
		type: 'absolute',
		tier: '3'
	},
	'5.1.1d': {
		code: '5.1.1d',
		ground: 'Bijzondere persoonsgegevens',
		description:
			'Ras, politieke opvattingen, religie, vakbondslidmaatschap, genetische/biometrische gegevens, gezondheid, seksuele gerichtheid, strafrechtelijke gegevens',
		type: 'absolute',
		tier: '2'
	},
	'5.1.1e': {
		code: '5.1.1e',
		ground: 'Identificatienummers',
		description: 'BSN, BIG-nummer, AGB-code, patiëntnummers',
		type: 'absolute',
		tier: '1'
	},
	'5.1.2a': {
		code: '5.1.2a',
		ground: 'Internationale betrekkingen',
		description: 'Diplomatieke relaties, grensoverschrijdende samenwerking',
		type: 'relative',
		tier: '3'
	},
	'5.1.2c': {
		code: '5.1.2c',
		ground: 'Opsporing/vervolging strafbare feiten',
		description: 'Verwijzingen naar lopende strafrechtelijke onderzoeken',
		type: 'relative',
		tier: '3'
	},
	'5.1.2d': {
		code: '5.1.2d',
		ground: 'Inspectie, controle en toezicht',
		description: 'Inspectiestrategieën, handhavingsplannen, auditaanpakken',
		type: 'relative',
		tier: '3'
	},
	'5.1.2e': {
		code: '5.1.2e',
		ground: 'Persoonlijke levenssfeer',
		description:
			'Namen van privépersonen, e-mailadressen, telefoonnummers, woonadressen, IBAN, geboortedata, kentekens',
		type: 'relative',
		tier: '2'
	},
	'5.1.2f': {
		code: '5.1.2f',
		ground: 'Bedrijfs- en fabricagegegevens (concurrentiegevoelig)',
		description: 'Concurrentiegevoelige bedrijfsinformatie, handelsgeheimen',
		type: 'relative',
		tier: '3'
	},
	'5.1.2h': {
		code: '5.1.2h',
		ground: 'Beveiliging personen/bedrijven',
		description: 'Beveiligingsdetails, toegangscodes',
		type: 'relative',
		tier: '3'
	},
	'5.1.2i': {
		code: '5.1.2i',
		ground: 'Goed functioneren bestuursorgaan',
		description: 'Informatie die het intern beraad zou schaden',
		type: 'relative',
		tier: '3'
	},
	'5.2': {
		code: '5.2',
		ground: 'Persoonlijke beleidsopvattingen',
		description:
			'Intern beleidsadvies, meningen, aanbevelingen. Let op: feiten, prognoses en beleidsalternatieven vallen hier NIET onder.',
		type: 'special',
		tier: '3'
	},
	'5.1.5': {
		code: '5.1.5',
		ground: 'Onevenredige benadeling',
		description: 'Alleen in uitzonderlijke gevallen; mag niet subsidiair aan andere gronden worden gebruikt',
		type: 'residual',
		tier: '3'
	}
};

/** Default entity-type nudge when the reviewer picks an article. */
export const ARTICLE_TO_ENTITY: Partial<Record<WooArticleCode, EntityType>> = {
	'5.1.1e': 'bsn',
	'5.1.1d': 'gezondheid',
	'5.1.2e': 'persoon'
};

/** Articles grouped by tier, sorted by code within each tier. */
export const ARTICLES_BY_TIER: Record<DetectionTier, WooArticle[]> = {
	'1': Object.values(WOO_ARTICLES)
		.filter((a) => a.tier === '1')
		.sort((a, b) => a.code.localeCompare(b.code)),
	'2': Object.values(WOO_ARTICLES)
		.filter((a) => a.tier === '2')
		.sort((a, b) => a.code.localeCompare(b.code)),
	'3': Object.values(WOO_ARTICLES)
		.filter((a) => a.tier === '3')
		.sort((a, b) => a.code.localeCompare(b.code))
};

export function getArticleLabel(code: WooArticleCode): string {
	const article = WOO_ARTICLES[code];
	return `Art. ${code} — ${article.ground}`;
}

export function isAbsoluteGround(code: WooArticleCode): boolean {
	return WOO_ARTICLES[code].type === 'absolute';
}

export function isRelativeGround(code: WooArticleCode): boolean {
	return WOO_ARTICLES[code].type === 'relative';
}
