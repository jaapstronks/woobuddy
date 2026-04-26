import { describe, it, expect } from 'vitest';
import { buildDiWooXml, validateMetadataInput, escapeXml } from './xml';
import type { PublicationContextRefs, PublicationMetadataInput } from './types';

const DUMMY_CTX: PublicationContextRefs = {
	publicatieUuid: '00000000-0000-4000-8000-000000000001',
	documentUuid: '00000000-0000-4000-8000-000000000002',
	exportedAt: '2026-04-25T10:00:00.000Z'
};

function makeInput(overrides: Partial<PublicationMetadataInput> = {}): PublicationMetadataInput {
	return {
		officieleTitel: 'Besluit Woo-verzoek 2026-0123',
		identifier: 'ZAAK-2026-0123',
		informatiecategorieen: [
			{
				uri: 'https://identifier.overheid.nl/tooi/def/thes/kern/c_3baef532',
				label: 'Woo-verzoek of -besluit'
			}
		],
		opsteller: 'Gemeente Voorbeeld',
		creatiedatum: '2026-01-15',
		laatstGewijzigdDatum: '2026-04-25T10:00:00.000Z',
		language: 'nld',
		bestandsformaat: 'application/pdf',
		bestandsnaam: 'gelakt_besluit-woo-verzoek.pdf',
		handelingen: [{ type: 'anonimiseren', atTime: '2026-04-25T10:00:00.000Z' }],
		...overrides
	};
}

describe('escapeXml', () => {
	it('escapes the five XML metacharacters', () => {
		expect(escapeXml('<a>&"\'')).toBe('&lt;a&gt;&amp;&quot;&apos;');
	});

	it('leaves plain Dutch text alone', () => {
		expect(escapeXml('Gemeente Voorbeeld')).toBe('Gemeente Voorbeeld');
	});
});

describe('buildDiWooXml', () => {
	it('emits a valid XML prolog and namespaced root', () => {
		const xml = buildDiWooXml(makeInput(), DUMMY_CTX);
		expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
		expect(xml).toContain(
			'<diwoo:Document xmlns:diwoo="https://standaarden.overheid.nl/diwoo/metadata/" xmlns:dcterms="http://purl.org/dc/terms/">'
		);
	});

	it('emits every required DiWoo element from the 0.9.8 schema', () => {
		const xml = buildDiWooXml(makeInput(), DUMMY_CTX);
		// All elements with cardinality 1 in the v0.9.8 metadata-xsd
		const required = [
			'<diwoo:DiWoo>',
			'<diwoo:classificatiecollectie>',
			'<diwoo:documentsoorten>',
			'<diwoo:documentsoort>',
			'<diwoo:informatiecategorieen>',
			'<diwoo:informatiecategorie',
			'<diwoo:themas>',
			'<diwoo:thema>',
			'<diwoo:trefwoorden>',
			'<diwoo:trefwoord>',
			'<diwoo:creatiedatum>',
			'<diwoo:format>',
			'<diwoo:geldigheid>',
			'<diwoo:begindatum>',
			'<diwoo:language>',
			'<diwoo:opsteller>',
			'<diwoo:publisher>',
			'<diwoo:verantwoordelijke>',
			'<diwoo:titelcollectie>',
			'<diwoo:officieleTitel>'
		];
		for (const tag of required) {
			expect(xml, `missing ${tag}`).toContain(tag);
		}
	});

	it('emits the informatiecategorie URI as a resource attribute', () => {
		const xml = buildDiWooXml(makeInput(), DUMMY_CTX);
		expect(xml).toContain(
			'<diwoo:informatiecategorie resource="https://identifier.overheid.nl/tooi/def/thes/kern/c_3baef532">Woo-verzoek of -besluit</diwoo:informatiecategorie>'
		);
	});

	it('emits documenthandelingen when present', () => {
		const xml = buildDiWooXml(makeInput(), DUMMY_CTX);
		expect(xml).toContain('<diwoo:documenthandeling>');
		expect(xml).toContain('<diwoo:soortHandeling>anonimiseren</diwoo:soortHandeling>');
	});

	it('omits documenthandelingen when the input is empty', () => {
		const xml = buildDiWooXml(makeInput({ handelingen: [] }), DUMMY_CTX);
		expect(xml).not.toContain('<diwoo:documenthandelingen>');
	});

	it('escapes user-provided strings', () => {
		const xml = buildDiWooXml(
			makeInput({ officieleTitel: 'Besluit "spoed" & overig <test>' }),
			DUMMY_CTX
		);
		expect(xml).toContain(
			'<diwoo:officieleTitel>Besluit &quot;spoed&quot; &amp; overig &lt;test&gt;</diwoo:officieleTitel>'
		);
	});

	it('falls back to opsteller for verantwoordelijke when not set', () => {
		const xml = buildDiWooXml(makeInput(), DUMMY_CTX);
		expect(xml).toContain('<diwoo:verantwoordelijke>Gemeente Voorbeeld</diwoo:verantwoordelijke>');
		expect(xml).toContain('<diwoo:publisher>Gemeente Voorbeeld</diwoo:publisher>');
	});

	it('emits an extra urn:uuid identifier alongside the user kenmerk', () => {
		const xml = buildDiWooXml(makeInput(), DUMMY_CTX);
		expect(xml).toContain('<diwoo:identifier>ZAAK-2026-0123</diwoo:identifier>');
		expect(xml).toContain(
			'<diwoo:identifier>urn:uuid:00000000-0000-4000-8000-000000000002</diwoo:identifier>'
		);
	});
});

describe('validateMetadataInput', () => {
	it('returns no missing fields for a complete input', () => {
		expect(validateMetadataInput(makeInput())).toEqual([]);
	});

	it('flags missing required fields', () => {
		const missing = validateMetadataInput({
			officieleTitel: '',
			identifier: '   ',
			informatiecategorieen: [],
			opsteller: '',
			creatiedatum: '2026',
			laatstGewijzigdDatum: '2026-04-25',
			language: '',
			bestandsformaat: '',
			bestandsnaam: ''
		});
		expect(missing).toEqual([
			'officieleTitel',
			'identifier',
			'informatiecategorieen',
			'opsteller',
			'creatiedatum',
			'laatstGewijzigdDatum',
			'language',
			'bestandsformaat',
			'bestandsnaam'
		]);
	});

	it('accepts ISO-8601 datetime for laatstGewijzigdDatum', () => {
		const missing = validateMetadataInput(
			makeInput({ laatstGewijzigdDatum: '2026-04-25T10:00:00.000Z' })
		);
		expect(missing).toEqual([]);
	});
});
