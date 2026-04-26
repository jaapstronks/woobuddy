/**
 * DiWoo metadata XML serializer (#52).
 *
 * Produces a `metadata.xml` document conforming to DiWoo metadata 0.9.8
 * (`https://standaarden.overheid.nl/diwoo/metadata/`). The schema is
 * structurally large (see the XSD at .../doc/0.9.8/metadata-xsd.html)
 * so the dialog only collects the fields that need a real reviewer
 * decision; everything else here is sensible defaults derived from the
 * document context — explicitly noted at each call site.
 *
 * Pure string concatenation, no DOMParser / xmldom: keeps this
 * usable in a Node test environment without polyfills, and the schema
 * is rigid enough that template literals are the path of least
 * surprise.
 */

import type { PublicationMetadataInput, PublicationContextRefs } from './types';

const NS_DIWOO = 'https://standaarden.overheid.nl/diwoo/metadata/';
const NS_DCTERMS = 'http://purl.org/dc/terms/';

/**
 * Escape a string for inclusion as XML element text. Attribute values
 * and CDATA are not used in the DiWoo output we emit, so this is the
 * only escaping path.
 */
export function escapeXml(value: string): string {
	return value
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&apos;');
}

function indent(depth: number): string {
	return '\t'.repeat(depth);
}

/**
 * Render a single `<diwoo:Document>` envelope. Returns a complete XML
 * document with prolog and namespace declarations on the root.
 */
export function buildDiWooXml(
	input: PublicationMetadataInput,
	ctx: PublicationContextRefs
): string {
	const lines: string[] = [];
	lines.push('<?xml version="1.0" encoding="UTF-8"?>');
	lines.push(
		`<diwoo:Document xmlns:diwoo="${NS_DIWOO}" xmlns:dcterms="${NS_DCTERMS}">`
	);
	lines.push(`${indent(1)}<diwoo:DiWoo>`);

	// classificatiecollectie — required, all four child collections required.
	// V1 has only the informatiecategorieen list driven by the dialog;
	// documentsoorten / themas / trefwoorden are filled with defaults
	// derived from the title and the chosen informatiecategorie label so
	// the schema's 1+ cardinality is satisfied. Reviewers who care can
	// edit the XML before publishing — V1 is "publication-ready", not
	// "publication-perfect".
	lines.push(`${indent(2)}<diwoo:classificatiecollectie>`);
	lines.push(`${indent(3)}<diwoo:documentsoorten>`);
	lines.push(`${indent(4)}<diwoo:documentsoort>besluit</diwoo:documentsoort>`);
	lines.push(`${indent(3)}</diwoo:documentsoorten>`);
	lines.push(`${indent(3)}<diwoo:informatiecategorieen>`);
	for (const cat of input.informatiecategorieen) {
		lines.push(
			`${indent(4)}<diwoo:informatiecategorie resource="${escapeXml(cat.uri)}">${escapeXml(cat.label)}</diwoo:informatiecategorie>`
		);
	}
	lines.push(`${indent(3)}</diwoo:informatiecategorieen>`);
	lines.push(`${indent(3)}<diwoo:themas>`);
	const primaryThema = input.informatiecategorieen[0]?.label ?? 'overig';
	lines.push(`${indent(4)}<diwoo:thema>${escapeXml(primaryThema)}</diwoo:thema>`);
	lines.push(`${indent(3)}</diwoo:themas>`);
	lines.push(`${indent(3)}<diwoo:trefwoorden>`);
	lines.push(`${indent(4)}<diwoo:trefwoord>${escapeXml(deriveTrefwoord(input.officieleTitel))}</diwoo:trefwoord>`);
	lines.push(`${indent(3)}</diwoo:trefwoorden>`);
	lines.push(`${indent(2)}</diwoo:classificatiecollectie>`);

	// creatiedatum — required, single date.
	lines.push(
		`${indent(2)}<diwoo:creatiedatum>${escapeXml(input.creatiedatum)}</diwoo:creatiedatum>`
	);

	// documenthandelingen — optional. V1 always emits at least the
	// anonimiseren handeling that produced the redacted PDF; this is the
	// audit hook that connects the bundle back to the redaction log.
	if (input.handelingen.length > 0) {
		lines.push(`${indent(2)}<diwoo:documenthandelingen>`);
		for (const h of input.handelingen) {
			lines.push(`${indent(3)}<diwoo:documenthandeling>`);
			lines.push(`${indent(4)}<diwoo:soortHandeling>${escapeXml(h.type)}</diwoo:soortHandeling>`);
			lines.push(`${indent(4)}<diwoo:atTime>${escapeXml(h.atTime)}</diwoo:atTime>`);
			lines.push(`${indent(3)}</diwoo:documenthandeling>`);
		}
		lines.push(`${indent(2)}</diwoo:documenthandelingen>`);
	}

	// format — required, IANA media type.
	lines.push(`${indent(2)}<diwoo:format>${escapeXml(input.bestandsformaat)}</diwoo:format>`);

	// geldigheid — begindatum required. We use the creatiedatum as the
	// begindatum default; the schema's einddatum is left open.
	lines.push(`${indent(2)}<diwoo:geldigheid>`);
	lines.push(
		`${indent(3)}<diwoo:begindatum>${escapeXml(input.creatiedatum)}</diwoo:begindatum>`
	);
	lines.push(`${indent(2)}</diwoo:geldigheid>`);

	// identifiers — optional but the dialog requires one.
	lines.push(`${indent(2)}<diwoo:identifiers>`);
	lines.push(
		`${indent(3)}<diwoo:identifier>${escapeXml(input.identifier)}</diwoo:identifier>`
	);
	lines.push(`${indent(3)}<diwoo:identifier>${escapeXml(`urn:uuid:${ctx.documentUuid}`)}</diwoo:identifier>`);
	lines.push(`${indent(2)}</diwoo:identifiers>`);

	// language — required, ISO 639-2 three-letter code.
	lines.push(`${indent(2)}<diwoo:language>${escapeXml(input.language)}</diwoo:language>`);

	// omschrijvingen — optional.
	if (input.omschrijving) {
		lines.push(`${indent(2)}<diwoo:omschrijvingen>`);
		lines.push(
			`${indent(3)}<diwoo:omschrijving>${escapeXml(input.omschrijving)}</diwoo:omschrijving>`
		);
		lines.push(`${indent(2)}</diwoo:omschrijvingen>`);
	}

	// opsteller, publisher, verantwoordelijke — required, all three. V1
	// uses the same free-text value for all three when the reviewer has
	// only entered one organisation (typical anonymous-flow case).
	const verant = input.verantwoordelijke ?? input.opsteller;
	lines.push(`${indent(2)}<diwoo:opsteller>${escapeXml(input.opsteller)}</diwoo:opsteller>`);
	lines.push(`${indent(2)}<diwoo:publisher>${escapeXml(verant)}</diwoo:publisher>`);
	lines.push(
		`${indent(2)}<diwoo:verantwoordelijke>${escapeXml(verant)}</diwoo:verantwoordelijke>`
	);

	// titelcollectie — required, with officieleTitel required inside.
	lines.push(`${indent(2)}<diwoo:titelcollectie>`);
	lines.push(
		`${indent(3)}<diwoo:officieleTitel>${escapeXml(input.officieleTitel)}</diwoo:officieleTitel>`
	);
	lines.push(`${indent(2)}</diwoo:titelcollectie>`);

	lines.push(`${indent(1)}</diwoo:DiWoo>`);
	lines.push('</diwoo:Document>');
	lines.push('');
	return lines.join('\n');
}

/**
 * Pull a usable trefwoord out of a free-text title. We strip filename
 * extensions, lowercase, and grab the first non-trivial token. The
 * schema requires *something* in trefwoorden (1+), and the reviewer can
 * always edit the XML before publishing — this is a guardrail, not a
 * classifier.
 */
function deriveTrefwoord(title: string): string {
	const cleaned = title
		.replace(/\.[a-z0-9]{1,5}$/i, '')
		.replace(/[_-]+/g, ' ')
		.toLowerCase()
		.trim();
	const first = cleaned.split(/\s+/).find((w) => w.length >= 4);
	return first ?? cleaned.split(/\s+/)[0] ?? 'document';
}

/**
 * Required-field gate used by the dialog before enabling the export
 * button. Returns a list of field names that are missing or invalid.
 * Empty array means the input is ready to serialize.
 */
export function validateMetadataInput(
	input: Partial<PublicationMetadataInput>
): string[] {
	const missing: string[] = [];
	if (!input.officieleTitel?.trim()) missing.push('officieleTitel');
	if (!input.identifier?.trim()) missing.push('identifier');
	if (!input.informatiecategorieen || input.informatiecategorieen.length === 0) {
		missing.push('informatiecategorieen');
	}
	if (!input.opsteller?.trim()) missing.push('opsteller');
	if (!input.creatiedatum?.match(/^\d{4}-\d{2}-\d{2}$/)) missing.push('creatiedatum');
	if (!input.laatstGewijzigdDatum?.match(/^\d{4}-\d{2}-\d{2}T/)) {
		missing.push('laatstGewijzigdDatum');
	}
	if (!input.language?.trim()) missing.push('language');
	if (!input.bestandsformaat?.trim()) missing.push('bestandsformaat');
	if (!input.bestandsnaam?.trim()) missing.push('bestandsnaam');
	return missing;
}
