import { describe, it, expect } from 'vitest';
import { buildGppJson } from './json';
import type { PublicationContextRefs, PublicationMetadataInput } from './types';

const CTX: PublicationContextRefs = {
	publicatieUuid: '11111111-1111-4111-8111-111111111111',
	documentUuid: '22222222-2222-4222-8222-222222222222',
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
		bestandsnaam: 'gelakt_besluit.pdf',
		bestandsomvang: 12345,
		handelingen: [{ type: 'anonimiseren', atTime: '2026-04-25T10:00:00.000Z' }],
		...overrides
	};
}

describe('buildGppJson', () => {
	it('produces both publicatie and document objects', () => {
		const out = buildGppJson(makeInput(), CTX);
		expect(out.$schema).toBe('https://github.com/GPP-Woo/GPP-publicatiebank');
		expect(out.publicatie).toBeDefined();
		expect(out.document).toBeDefined();
	});

	it('marks every PublicationWrite-required field on the publicatie', () => {
		const out = buildGppJson(makeInput(), CTX);
		const required = [
			'uuid',
			'officieleTitel',
			'registratiedatum',
			'laatstGewijzigdDatum',
			'urlPublicatieIntern',
			'urlPublicatieExtern',
			'diWooInformatieCategorieen',
			'gepubliceerdOp',
			'ingetrokkenOp',
			'publicatiestatus'
		];
		for (const key of required) {
			expect(out.publicatie, `missing ${key}`).toHaveProperty(key);
		}
		expect(out.publicatie.diWooInformatieCategorieen).toEqual([
			'https://identifier.overheid.nl/tooi/def/thes/kern/c_3baef532'
		]);
	});

	it('marks every DocumentWrite-required field on the document', () => {
		const out = buildGppJson(makeInput(), CTX);
		const required = [
			'uuid',
			'publicatie',
			'officieleTitel',
			'creatiedatum',
			'registratiedatum',
			'laatstGewijzigdDatum',
			'publicatiestatus',
			'uploadVoltooid',
			'gepubliceerdOp',
			'ingetrokkenOp'
		];
		for (const key of required) {
			expect(out.document, `missing ${key}`).toHaveProperty(key);
		}
		expect(out.document.publicatie).toBe(CTX.publicatieUuid);
		expect(out.document.uuid).toBe(CTX.documentUuid);
	});

	it('starts the publication in concept status', () => {
		const out = buildGppJson(makeInput(), CTX);
		expect(out.publicatie.publicatiestatus).toBe('concept');
		expect(out.document.publicatiestatus).toBe('concept');
	});

	it('carries identifier through as a kenmerk on both objects', () => {
		const out = buildGppJson(makeInput(), CTX);
		expect(out.publicatie.kenmerken).toEqual([
			{ kenmerk: 'ZAAK-2026-0123', bron: 'WOO Buddy export' }
		]);
		expect(out.document.kenmerken).toEqual([
			{ kenmerk: 'ZAAK-2026-0123', bron: 'WOO Buddy export' }
		]);
	});

	it('only includes bestandsomvang when the bundle knows the size', () => {
		const sized = buildGppJson(makeInput(), CTX);
		expect(sized.document.bestandsomvang).toBe(12345);

		const unsized = buildGppJson(makeInput({ bestandsomvang: undefined }), CTX);
		expect(unsized.document.bestandsomvang).toBeUndefined();
	});

	it('carries omschrijving onto both objects when set', () => {
		const out = buildGppJson(makeInput({ omschrijving: 'Besluit op Woo-verzoek X' }), CTX);
		expect(out.publicatie.omschrijving).toBe('Besluit op Woo-verzoek X');
		expect(out.document.omschrijving).toBe('Besluit op Woo-verzoek X');
	});
});
