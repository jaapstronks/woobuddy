/**
 * Onderbouwingsrapport (#64) — public surface.
 *
 * Re-exports the lightweight pieces (types, summary, hashing,
 * bundle) so the toolbar component and review-export store can
 * import them without pulling in pdf-lib. The heavy
 * `buildOnderbouwingPdf` lives in `./report` and is dynamically
 * imported by the store the first time the reviewer clicks the
 * toolbar button.
 */

export type {
	OnderbouwingInput,
	ProvenanceHashes,
	ReviewerInput
} from './types';
export { sha256Hex } from './hash';
export {
	buildReportRows,
	buildReportSummary,
	selectReportableDetections,
	motivationFor
} from './summary';
export type { ReportRow, ReportSummary } from './summary';
export {
	bundleOnderbouwing,
	deriveOnderbouwingFilename
} from './bundle';
export type { OnderbouwingArtifact, BundleOnderbouwingArgs } from './bundle';
