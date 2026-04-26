/**
 * Input shape for the DiWoo / GPP-Woo publication export bundle (#52).
 *
 * Captured by the metadata-input dialog and consumed by the XML / JSON
 * serializers and the bundle zip builder. Mirrors the field surface of
 * DiWoo metadata 0.9.8 (`https://standaarden.overheid.nl/diwoo/metadata/`)
 * with the GPP-Woo publicatiebank JSON shape mapped on top.
 *
 * V1 keeps the dialog small: a handful of required fields, sensible
 * defaults for the rest. Optional fields not exposed in the dialog
 * still get reasonable values from the document context (filename,
 * upload time, redaction-log dates).
 */

export interface InformatiecategorieRef {
	/** Canonical TOOI URI, e.g. `.../tooi/def/thes/kern/c_3baef532`. */
	uri: string;
	/** Dutch label, used for human-readable output. */
	label: string;
}

export interface DocumentHandeling {
	/**
	 * Loose handeling type. V1 only emits `anonimiseren` (redaction) but
	 * the schema allows the full DiWoo handelingen list — kept open here
	 * so future flows (e.g. "ondertekenen") plug in without a refactor.
	 */
	type: 'anonimiseren' | 'ondertekenen' | 'opstellen' | 'vaststellen' | 'ontvangen';
	atTime: string; // ISO 8601 datetime
}

export interface PublicationMetadataInput {
	/** dcterms:title — official document title. */
	officieleTitel: string;
	/** dcterms:identifier — besluit-identifier or referentie. */
	identifier: string;
	/** diwoo:informatiecategorie — TOOI URI(s); at least one required. */
	informatiecategorieen: InformatiecategorieRef[];
	/** dcterms:creator — organisatie / opsteller, free text at V1. */
	opsteller: string;
	/** Same as opsteller for single-organisation publishers. */
	verantwoordelijke?: string;
	/** dcterms:created — ISO 8601 date (YYYY-MM-DD). */
	creatiedatum: string;
	/** dcterms:modified — ISO 8601 datetime. */
	laatstGewijzigdDatum: string;
	/** ISO 639-2 three-letter code; default `nld`. */
	language: string;
	/** Optional document handelingen — V1 emits one anonimiseren entry. */
	handelingen: DocumentHandeling[];
	/** dcterms:format — IANA media type. Default `application/pdf`. */
	bestandsformaat: string;
	/** Filename for the redacted PDF inside the zip. */
	bestandsnaam: string;
	/** Number of bytes of the redacted PDF. */
	bestandsomvang?: number;
	/** Optional kort verhaal — exposed in dialog as a textarea. */
	omschrijving?: string;
}

export interface PublicationContextRefs {
	/**
	 * Stable UUID for the publication envelope in the GPP-Woo JSON. V1
	 * generates a fresh UUID per export — there's no persistent
	 * publicatiebank state on our side.
	 */
	publicatieUuid: string;
	/** Stable UUID for the document inside the publication. */
	documentUuid: string;
	/** ISO 8601 datetime stamp for the export itself (registratiedatum). */
	exportedAt: string;
}
