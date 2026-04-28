/**
 * Export-flow state for the review page.
 *
 * Small runes-backed store that owns the export button's busy flag,
 * the retry banner's error string, and the post-export lead-capture
 * visibility (#45). Split out of `/review/[docId]/+page.svelte` so the
 * page component doesn't have to reason about the `try/catch/finally`
 * around `fetch` alongside all the other review state.
 *
 * The store is document-agnostic — `runExport()` takes the docId, PDF
 * bytes, and filename each call, and `reset()` is invoked from the
 * page's document-change effect so a new document starts clean.
 */

import { exportRedactedPdf, downloadBlob } from '$lib/services/export-service';
import { buildDebugExport, downloadDebugExport } from '$lib/services/debug-export';
import {
	buildPublicationBundle,
	deriveBundleFilename,
	type PublicationMetadataInput
} from '$lib/services/diwoo';
import {
	bundleOnderbouwing,
	sha256Hex,
	type OnderbouwingInput,
	type ReviewerInput
} from '$lib/services/onderbouwing';
import type { Detection, Document } from '$lib/types';
import { track } from '$lib/analytics/plausible';
import { bucketPages, bucketRedactions } from '$lib/analytics/events';

let exporting = $state(false);
let exportError = $state<string | null>(null);
let showPostExportLead = $state(false);
// #52 — separate state for the publication-export bundle: the dialog
// open/close flag is decoupled from the simple-export busy flag so the
// reviewer can dismiss the dialog without affecting the inline retry
// banner from a previous failed plain-PDF export.
let publicationDialogOpen = $state(false);
let publicationBundling = $state(false);
// Inline accessibility-confirmation banner that appears once after a
// successful export. Communicates the PDF/A-2b + Dutch language tag
// guarantee so the work the post-processing pipeline does is visible.
// Auto-dismisses on the next export run.
let showAccessibilityBanner = $state(false);

// #64 — onderbouwingsrapport state. The provenance hashes are cached
// across calls so re-opening the dialog after a successful export
// doesn't recompute the SHA-256 of a multi-MB PDF for nothing. The
// redacted hash is populated as a side effect of `runExport`; it
// stays null until the reviewer has actually exported the gelakte
// PDF in this session, so the report can be honest about that.
let onderbouwingDialogOpen = $state(false);
let onderbouwingBusy = $state(false);
let originalPdfHash = $state<string | null>(null);
let redactedPdfHash = $state<string | null>(null);

export interface RunExportArgs {
	pdfBytes: ArrayBuffer;
	filename: string;
	/**
	 * The current detection list. Accepted detections become the
	 * redactions sent to the server in the multipart request body —
	 * #50 anonymous mode means the server can't look them up itself.
	 */
	detections: Detection[];
	/** Number of non-rejected detections at export time — bucketed for analytics. */
	confirmedCount: number;
	/** Page count of the exported document — bucketed for analytics. */
	pageCount: number;
	/**
	 * Optional reviewer-typed title that ends up in the XMP `dc:title`
	 * field. Falls back to no title (i.e. DMSes show the filename) when
	 * blank or omitted.
	 */
	title?: string;
}

async function runExport({
	pdfBytes,
	filename,
	detections,
	confirmedCount,
	pageCount,
	title
}: RunExportArgs): Promise<void> {
	exporting = true;
	exportError = null;
	showAccessibilityBanner = false;
	try {
		const redacted = await exportRedactedPdf(pdfBytes, filename, detections, { title });
		downloadBlob(redacted, `gelakt_${filename}`);
		// Cache the redacted PDF hash so a follow-up onderbouwingsrapport
		// can include it in its provenance block. We deliberately hash
		// after a successful download so a failed export doesn't poison
		// the cache with a stale value.
		try {
			const redactedBytes = await redacted.arrayBuffer();
			redactedPdfHash = await sha256Hex(redactedBytes);
		} catch (hashErr) {
			console.warn('Failed to hash redacted PDF for onderbouwing provenance', hashErr);
			redactedPdfHash = null;
		}
		showPostExportLead = true;
		showAccessibilityBanner = true;
		track('export_completed', {
			redaction_bucket: bucketRedactions(confirmedCount),
			page_bucket: bucketPages(pageCount)
		});
	} catch (e) {
		exportError = e instanceof Error ? e.message : 'Export mislukt';
	} finally {
		exporting = false;
	}
}

/**
 * Client-side diagnostic dump of the analyzer's output. Pulled in here
 * so the review page has a single import surface for "export things".
 */
function runDebugExport(doc: Document | null, detections: Detection[], docId: string): void {
	const payload = buildDebugExport(doc, detections);
	const base = doc?.filename ?? `document-${docId}`;
	downloadDebugExport(payload, base);
}

function setPostExportLead(next: boolean): void {
	showPostExportLead = next;
}

function setAccessibilityBanner(next: boolean): void {
	showAccessibilityBanner = next;
}

function setError(message: string | null): void {
	exportError = message;
}

function clearError(): void {
	exportError = null;
}

function reset(): void {
	exporting = false;
	exportError = null;
	showPostExportLead = false;
	showAccessibilityBanner = false;
	publicationDialogOpen = false;
	publicationBundling = false;
	onderbouwingDialogOpen = false;
	onderbouwingBusy = false;
	originalPdfHash = null;
	redactedPdfHash = null;
}

function openPublicationDialog(): void {
	exportError = null;
	publicationDialogOpen = true;
}

function closePublicationDialog(): void {
	if (publicationBundling) return;
	publicationDialogOpen = false;
}

export interface RunPublicationExportArgs {
	pdfBytes: ArrayBuffer;
	filename: string;
	document: Document | null;
	detections: Detection[];
	input: PublicationMetadataInput;
	tooiSchemaVersion: string;
	confirmedCount: number;
	pageCount: number;
}

/**
 * #52 — Publication-export bundle. Re-uses the inline-redactions
 * endpoint for the gelakte PDF and assembles the DiWoo + GPP-Woo
 * artifacts client-side.
 */
async function runPublicationExport(args: RunPublicationExportArgs): Promise<void> {
	publicationBundling = true;
	exportError = null;
	try {
		const redactedBlob = await exportRedactedPdf(
			args.pdfBytes,
			args.filename,
			args.detections,
			{ title: args.input.officieleTitel }
		);
		const redactedBytes = new Uint8Array(await redactedBlob.arrayBuffer());
		try {
			redactedPdfHash = await sha256Hex(redactedBytes);
		} catch (hashErr) {
			console.warn('Failed to hash redacted PDF for onderbouwing provenance', hashErr);
		}
		const inputWithSize: PublicationMetadataInput = {
			...args.input,
			bestandsomvang: redactedBytes.byteLength
		};
		const bundle = buildPublicationBundle({
			input: inputWithSize,
			redactedPdf: redactedBytes,
			detections: args.detections,
			tooiSchemaVersion: args.tooiSchemaVersion
		});
		const filename = deriveBundleFilename(args.document, bundle.exportedAt);
		downloadBlob(bundle.blob, filename);
		publicationDialogOpen = false;
		showPostExportLead = true;
		track('publication_export_completed', {
			redaction_bucket: bucketRedactions(args.confirmedCount),
			page_bucket: bucketPages(args.pageCount)
		});
	} catch (e) {
		exportError = e instanceof Error ? e.message : 'Bundel-export mislukt';
	} finally {
		publicationBundling = false;
	}
}

// ---------------------------------------------------------------------------
// #64 — Onderbouwingsrapport
// ---------------------------------------------------------------------------

/**
 * Compute and cache the SHA-256 of the original PDF the first time it's
 * needed. Subsequent calls return the cached value so re-opening the
 * dialog after another action doesn't re-hash the (potentially
 * multi-MB) bytes.
 */
async function ensureOriginalHash(pdfBytes: ArrayBuffer): Promise<string> {
	if (originalPdfHash) return originalPdfHash;
	const hash = await sha256Hex(pdfBytes);
	originalPdfHash = hash;
	return hash;
}

function openOnderbouwingDialog(): void {
	exportError = null;
	onderbouwingDialogOpen = true;
}

function closeOnderbouwingDialog(): void {
	if (onderbouwingBusy) return;
	onderbouwingDialogOpen = false;
}

export interface RunOnderbouwingExportArgs {
	pdfBytes: ArrayBuffer;
	filename: string;
	document: Document | null;
	detections: Detection[];
	reviewer: ReviewerInput;
	confirmedCount: number;
	pageCount: number;
	buildCommit: string;
}

/**
 * Generate and download the onderbouwingsrapport. Lazy-imports the
 * pdf-lib-heavy renderer so the toolbar button itself stays
 * cheap — only the click handler pulls the ~250KB module.
 */
async function runOnderbouwingExport(
	args: RunOnderbouwingExportArgs
): Promise<void> {
	onderbouwingBusy = true;
	exportError = null;
	try {
		const originalSha256 = await ensureOriginalHash(args.pdfBytes);
		const { buildOnderbouwingPdf } = await import(
			'$lib/services/onderbouwing/report'
		);
		const input: OnderbouwingInput = {
			document: args.document,
			filename: args.filename,
			detections: args.detections,
			hashes: {
				originalSha256,
				redactedSha256: redactedPdfHash
			},
			reviewer: args.reviewer,
			buildCommit: args.buildCommit,
			generatedAt: new Date()
		};
		const pdfBytes = await buildOnderbouwingPdf(input);
		const artifact = bundleOnderbouwing({
			pdfBytes,
			originalFilename: args.filename,
			includeCsv: args.reviewer.includeCsv,
			detections: args.detections
		});
		downloadBlob(artifact.blob, artifact.filename);
		onderbouwingDialogOpen = false;
		track('onderbouwing_export_completed', {
			redaction_bucket: bucketRedactions(args.confirmedCount),
			page_bucket: bucketPages(args.pageCount)
		});
	} catch (e) {
		exportError =
			e instanceof Error ? e.message : 'Onderbouwingsrapport mislukt';
	} finally {
		onderbouwingBusy = false;
	}
}

export const reviewExportStore = {
	get exporting() {
		return exporting;
	},
	get exportError() {
		return exportError;
	},
	get showPostExportLead() {
		return showPostExportLead;
	},
	get showAccessibilityBanner() {
		return showAccessibilityBanner;
	},
	get publicationDialogOpen() {
		return publicationDialogOpen;
	},
	get publicationBundling() {
		return publicationBundling;
	},
	get onderbouwingDialogOpen() {
		return onderbouwingDialogOpen;
	},
	get onderbouwingBusy() {
		return onderbouwingBusy;
	},
	get hasRedactedHash() {
		return redactedPdfHash !== null;
	},
	runExport,
	runDebugExport,
	runPublicationExport,
	runOnderbouwingExport,
	openPublicationDialog,
	closePublicationDialog,
	openOnderbouwingDialog,
	closeOnderbouwingDialog,
	setPostExportLead,
	setAccessibilityBanner,
	setError,
	clearError,
	reset
};
