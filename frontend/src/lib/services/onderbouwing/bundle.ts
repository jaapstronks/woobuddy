/**
 * Bundling and filename helpers for the onderbouwingsrapport (#64).
 *
 * The PDF is the primary artifact. When the reviewer ticks "ook
 * CSV erbij", we re-use the existing `buildRedactionLogCsv` from
 * #52 and zip the two files together with `fflate` so the dossier
 * folder stays tidy. With PDF only we hand the bare bytes back —
 * one file is friendlier than a zip.
 */

import { zipSync, strToU8 } from 'fflate';
import { buildRedactionLogCsv } from '$lib/services/diwoo/csv';
import type { Detection } from '$lib/types';

export interface OnderbouwingArtifact {
	blob: Blob;
	filename: string;
}

/**
 * Strip the `.pdf` suffix and any path separators (defensive — the
 * filename comes from the original upload and shouldn't have them,
 * but a malformed name would otherwise inject a subdirectory into
 * our download).
 */
function basename(filename: string): string {
	return filename
		.replace(/\.pdf$/i, '')
		.replace(/[\\/]/g, '_');
}

function todayStamp(date: Date): string {
	const y = date.getFullYear();
	const m = String(date.getMonth() + 1).padStart(2, '0');
	const d = String(date.getDate()).padStart(2, '0');
	return `${y}-${m}-${d}`;
}

export function deriveOnderbouwingFilename(args: {
	originalFilename: string;
	includeCsv: boolean;
	now?: Date;
}): string {
	const stem = basename(args.originalFilename);
	const stamp = todayStamp(args.now ?? new Date());
	const ext = args.includeCsv ? 'zip' : 'pdf';
	return `onderbouwing_${stem}_${stamp}.${ext}`;
}

export interface BundleOnderbouwingArgs {
	pdfBytes: Uint8Array;
	originalFilename: string;
	includeCsv: boolean;
	detections: Detection[];
	now?: Date;
}

export function bundleOnderbouwing(args: BundleOnderbouwingArgs): OnderbouwingArtifact {
	const filename = deriveOnderbouwingFilename({
		originalFilename: args.originalFilename,
		includeCsv: args.includeCsv,
		now: args.now
	});

	if (!args.includeCsv) {
		return {
			blob: new Blob([args.pdfBytes as BlobPart], { type: 'application/pdf' }),
			filename
		};
	}

	const csv = buildRedactionLogCsv(args.detections);
	const stem = basename(args.originalFilename);
	const stamp = todayStamp(args.now ?? new Date());
	const zipBytes = zipSync({
		[`onderbouwing_${stem}_${stamp}.pdf`]: args.pdfBytes,
		[`onderbouwing_${stem}_${stamp}.csv`]: strToU8(csv)
	});
	return {
		blob: new Blob([zipBytes as BlobPart], { type: 'application/zip' }),
		filename
	};
}
