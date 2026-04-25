/**
 * Publication-export bundle assembler (#52).
 *
 * Composes the redacted PDF (already returned by the existing
 * `exportRedactedPdf` server route) and the DiWoo / GPP-Woo metadata
 * artifacts into a single zip, fully client-side via `fflate`. No new
 * server route is involved — see todo #52 §Backend ("Nothing.").
 *
 * Returns a Blob the caller hands to `downloadBlob` for the browser
 * save dialog. Errors propagate so the review-export store can show
 * the existing retry banner.
 */

import { zipSync, strToU8 } from 'fflate';
import type { Detection, Document } from '$lib/types';
import { buildDiWooXml } from './xml';
import { buildGppJson } from './json';
import { buildRedactionLogCsv } from './csv';
import { buildBundleReadme } from './readme';
import type { PublicationMetadataInput, PublicationContextRefs } from './types';

export interface BuildBundleArgs {
	input: PublicationMetadataInput;
	redactedPdf: Uint8Array;
	detections: Detection[];
	tooiSchemaVersion: string;
	/** Inject deterministic UUID + clock for tests. */
	now?: () => Date;
	uuid?: () => string;
}

export interface PublicationBundle {
	blob: Blob;
	publicatieUuid: string;
	documentUuid: string;
	exportedAt: string;
	files: {
		'redacted.pdf': Uint8Array;
		'metadata.xml': string;
		'metadata.json': string;
		'redaction-log.csv': string;
		'README.txt': string;
	};
}

function defaultUuid(): string {
	if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
		return crypto.randomUUID();
	}
	// Fallback: random hex with a v4-ish layout. Node test environments
	// without `crypto.randomUUID` shouldn't actually hit this — but
	// we'd rather degrade than throw at zip time.
	const r = () => Math.floor(Math.random() * 0xffff).toString(16).padStart(4, '0');
	return `${r()}${r()}-${r()}-4${r().slice(1)}-${(8 + Math.floor(Math.random() * 4)).toString(16)}${r().slice(1)}-${r()}${r()}${r()}`;
}

export function buildPublicationBundle(args: BuildBundleArgs): PublicationBundle {
	const now = args.now ?? (() => new Date());
	const uuid = args.uuid ?? defaultUuid;

	const ctx: PublicationContextRefs = {
		publicatieUuid: uuid(),
		documentUuid: uuid(),
		exportedAt: now().toISOString()
	};

	const xml = buildDiWooXml(args.input, ctx);
	const jsonObj = buildGppJson(args.input, ctx);
	const json = JSON.stringify(jsonObj, null, 2) + '\n';
	const csv = buildRedactionLogCsv(args.detections);
	const readme = buildBundleReadme(args.input, ctx, args.tooiSchemaVersion);

	const files: PublicationBundle['files'] = {
		'redacted.pdf': args.redactedPdf,
		'metadata.xml': xml,
		'metadata.json': json,
		'redaction-log.csv': csv,
		'README.txt': readme
	};

	const zipBytes = zipSync({
		'redacted.pdf': args.redactedPdf,
		'metadata.xml': strToU8(xml),
		'metadata.json': strToU8(json),
		'redaction-log.csv': strToU8(csv),
		'README.txt': strToU8(readme)
	});

	const blob = new Blob([zipBytes as BlobPart], { type: 'application/zip' });

	return {
		blob,
		publicatieUuid: ctx.publicatieUuid,
		documentUuid: ctx.documentUuid,
		exportedAt: ctx.exportedAt,
		files
	};
}

/**
 * Convenience wrapper used by the dialog: derives a sensible zip
 * filename from the document's filename and the timestamp.
 */
export function deriveBundleFilename(doc: Document | null, exportedAt: string): string {
	const base = (doc?.filename ?? 'document.pdf').replace(/\.pdf$/i, '');
	const stamp = exportedAt.slice(0, 10);
	return `${base}_diwoo_${stamp}.zip`;
}
