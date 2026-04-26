/**
 * GPP-Woo publicatiebank JSON serializer (#52).
 *
 * Mirrors the OpenAPI schema published at
 * `https://github.com/GPP-Woo/GPP-publicatiebank` (resource paths
 * `/api/v1/publicaties` and `/api/v1/documenten`). The bundle includes
 * BOTH a publication envelope and a document entry so a downstream
 * tool can ingest the pair without reconstructing the parent on the
 * fly.
 *
 * The shape captures the intent of `PublicationWrite` and
 * `DocumentWrite`: every field that the API treats as required is
 * always populated; optional fields appear when the dialog or
 * document context provides a value.
 */

import type { PublicationMetadataInput, PublicationContextRefs } from './types';

export interface GppPublicationJson {
	uuid: string;
	officieleTitel: string;
	registratiedatum: string;
	laatstGewijzigdDatum: string;
	urlPublicatieIntern: string;
	urlPublicatieExtern: string;
	diWooInformatieCategorieen: string[];
	gepubliceerdOp: string | null;
	ingetrokkenOp: string | null;
	publicatiestatus: 'concept' | 'gepubliceerd' | 'ingetrokken';
	kenmerken: Array<{ kenmerk: string; bron: string }>;
	verantwoordelijke?: string;
	publisher?: string;
	opsteller?: string;
	omschrijving?: string;
}

export interface GppDocumentJson {
	uuid: string;
	publicatie: string;
	officieleTitel: string;
	creatiedatum: string;
	registratiedatum: string;
	laatstGewijzigdDatum: string;
	publicatiestatus: 'concept' | 'gepubliceerd' | 'ingetrokken';
	uploadVoltooid: boolean;
	gepubliceerdOp: string | null;
	ingetrokkenOp: string | null;
	bestandsformaat?: string;
	bestandsnaam?: string;
	bestandsomvang?: number;
	omschrijving?: string;
	kenmerken: Array<{ kenmerk: string; bron: string }>;
}

export interface GppBundleJson {
	$schema: 'https://github.com/GPP-Woo/GPP-publicatiebank';
	publicatie: GppPublicationJson;
	document: GppDocumentJson;
}

export function buildGppJson(
	input: PublicationMetadataInput,
	ctx: PublicationContextRefs
): GppBundleJson {
	const kenmerk = { kenmerk: input.identifier, bron: 'WOO Buddy export' };

	const publicatie: GppPublicationJson = {
		uuid: ctx.publicatieUuid,
		officieleTitel: input.officieleTitel,
		registratiedatum: ctx.exportedAt,
		laatstGewijzigdDatum: input.laatstGewijzigdDatum,
		urlPublicatieIntern: '',
		urlPublicatieExtern: '',
		diWooInformatieCategorieen: input.informatiecategorieen.map((c) => c.uri),
		gepubliceerdOp: null,
		ingetrokkenOp: null,
		publicatiestatus: 'concept',
		kenmerken: [kenmerk],
		opsteller: input.opsteller,
		verantwoordelijke: input.verantwoordelijke ?? input.opsteller,
		publisher: input.verantwoordelijke ?? input.opsteller,
		...(input.omschrijving ? { omschrijving: input.omschrijving } : {})
	};

	const document: GppDocumentJson = {
		uuid: ctx.documentUuid,
		publicatie: ctx.publicatieUuid,
		officieleTitel: input.officieleTitel,
		creatiedatum: input.creatiedatum,
		registratiedatum: ctx.exportedAt,
		laatstGewijzigdDatum: input.laatstGewijzigdDatum,
		publicatiestatus: 'concept',
		uploadVoltooid: true,
		gepubliceerdOp: null,
		ingetrokkenOp: null,
		bestandsformaat: input.bestandsformaat,
		bestandsnaam: input.bestandsnaam,
		...(typeof input.bestandsomvang === 'number'
			? { bestandsomvang: input.bestandsomvang }
			: {}),
		...(input.omschrijving ? { omschrijving: input.omschrijving } : {}),
		kenmerken: [kenmerk]
	};

	return {
		$schema: 'https://github.com/GPP-Woo/GPP-publicatiebank',
		publicatie,
		document
	};
}
