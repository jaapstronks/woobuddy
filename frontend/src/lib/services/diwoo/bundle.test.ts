import { describe, it, expect } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import { buildPublicationBundle } from './bundle';
import type { PublicationMetadataInput } from './types';
import type { Detection } from '$lib/types';

function makeInput(): PublicationMetadataInput {
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
		handelingen: [{ type: 'anonimiseren', atTime: '2026-04-25T10:00:00.000Z' }]
	};
}

function makeDetection(): Detection {
	return {
		id: 'd1',
		document_id: 'doc1',
		entity_type: 'bsn',
		tier: '1',
		confidence: 1,
		woo_article: '5.1.1e',
		review_status: 'accepted',
		bounding_boxes: [{ page: 1, x0: 0, y0: 0, x1: 10, y1: 10 }],
		reasoning: null,
		propagated_from: null,
		reviewer_id: null,
		reviewed_at: '2026-04-25T10:00:00Z',
		is_environmental: false,
		source: 'regex'
	};
}

describe('buildPublicationBundle', () => {
	const FAKE_PDF = new TextEncoder().encode('%PDF-1.7 fake');
	let counter = 0;
	const fixedUuid = () => {
		counter += 1;
		return `00000000-0000-4000-8000-${counter.toString().padStart(12, '0')}`;
	};
	const fixedNow = () => new Date('2026-04-25T10:00:00.000Z');

	it('produces a zip blob containing every required file', async () => {
		counter = 0;
		const bundle = buildPublicationBundle({
			input: makeInput(),
			redactedPdf: FAKE_PDF,
			detections: [makeDetection()],
			tooiSchemaVersion: '0.9.8',
			now: fixedNow,
			uuid: fixedUuid
		});

		expect(bundle.blob.type).toBe('application/zip');

		const buf = new Uint8Array(await bundle.blob.arrayBuffer());
		const entries = unzipSync(buf);
		expect(Object.keys(entries).sort()).toEqual([
			'README.txt',
			'metadata.json',
			'metadata.xml',
			'redacted.pdf',
			'redaction-log.csv'
		]);
	});

	it('preserves the redacted PDF bytes intact', async () => {
		const bundle = buildPublicationBundle({
			input: makeInput(),
			redactedPdf: FAKE_PDF,
			detections: [],
			tooiSchemaVersion: '0.9.8',
			now: fixedNow,
			uuid: fixedUuid
		});
		const buf = new Uint8Array(await bundle.blob.arrayBuffer());
		const entries = unzipSync(buf);
		expect(entries['redacted.pdf']).toEqual(FAKE_PDF);
	});

	it('emits valid JSON in metadata.json', async () => {
		const bundle = buildPublicationBundle({
			input: makeInput(),
			redactedPdf: FAKE_PDF,
			detections: [],
			tooiSchemaVersion: '0.9.8',
			now: fixedNow,
			uuid: fixedUuid
		});
		const buf = new Uint8Array(await bundle.blob.arrayBuffer());
		const entries = unzipSync(buf);
		const json = JSON.parse(strFromU8(entries['metadata.json']));
		expect(json.publicatie.officieleTitel).toBe('Besluit Woo-verzoek 2026-0123');
		expect(json.document.bestandsnaam).toBe('gelakt_besluit.pdf');
	});

	it('round-trips: README mentions the schema version it was generated against', async () => {
		const bundle = buildPublicationBundle({
			input: makeInput(),
			redactedPdf: FAKE_PDF,
			detections: [],
			tooiSchemaVersion: '0.9.8',
			now: fixedNow,
			uuid: fixedUuid
		});
		const buf = new Uint8Array(await bundle.blob.arrayBuffer());
		const entries = unzipSync(buf);
		const readme = strFromU8(entries['README.txt']);
		expect(readme).toContain('DiWoo-standaard v0.9.8');
		expect(readme).toContain('GPP-publicatiebank');
	});

	it('CSV inside the zip lists accepted detections', async () => {
		const bundle = buildPublicationBundle({
			input: makeInput(),
			redactedPdf: FAKE_PDF,
			detections: [makeDetection()],
			tooiSchemaVersion: '0.9.8',
			now: fixedNow,
			uuid: fixedUuid
		});
		const buf = new Uint8Array(await bundle.blob.arrayBuffer());
		const entries = unzipSync(buf);
		const csv = strFromU8(entries['redaction-log.csv']);
		expect(csv).toContain('5.1.1e');
		expect(csv).toContain('BSN');
	});
});
