/**
 * Shared types for the onderbouwingsrapport (#64) module.
 *
 * Kept in a separate file so the heavy `report.ts` (which imports
 * pdf-lib) can stay behind a dynamic import while the toolbar
 * button's component just imports these types.
 */

import type { Detection, Document } from '$lib/types';

/**
 * Reviewer-supplied metadata captured by the dialog before
 * generating the report. All fields are optional and stored only in
 * memory — nothing is sent to the server, nothing persists past the
 * download.
 */
export interface ReviewerInput {
	zaaknummer: string;
	reviewerName: string;
	opmerkingen: string;
	/** When true, also bundles a `redaction-log.csv` next to the PDF in a zip. */
	includeCsv: boolean;
}

/**
 * Provenance hashes computed in `hash.ts`. The redacted hash is null
 * when the reviewer hasn't exported the gelakte PDF yet in this
 * session — the report is honest about that and prints an explicit
 * "redactie nog niet geëxporteerd" line instead of faking a hash.
 */
export interface ProvenanceHashes {
	originalSha256: string;
	redactedSha256: string | null;
}

/**
 * Everything `buildOnderbouwingPdf` needs to render. Assembled by the
 * review-export store from in-memory state — no fetches, no DB hits.
 */
export interface OnderbouwingInput {
	document: Document | null;
	/** Filename of the source PDF (used for the cover, not for content). */
	filename: string;
	detections: Detection[];
	hashes: ProvenanceHashes;
	reviewer: ReviewerInput;
	/** Build commit short hash, surfaced as "WOO Buddy (<commit>)". */
	buildCommit: string;
	/** ISO timestamp at generation. Defaults to `new Date()` in the renderer. */
	generatedAt?: Date;
}
