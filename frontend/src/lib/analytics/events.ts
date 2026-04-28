/**
 * Enumerated Plausible event names and their allowed props.
 *
 * Having a single file that lists every event keeps the dashboard
 * configuration (goals + custom props) in sync with the code: if an event
 * isn't here, it isn't fired. Adding a new event is deliberately a two-step
 * change — add it here, then fire it — so reviewers of a PR can see at a
 * glance that a new data point is being collected.
 *
 * Keep props coarse. Never include filenames, entity text, exact counts that
 * could fingerprint a specific document, or anything that could identify a
 * user or an organization.
 */

export type DocumentConvertedProps = {
	/** "pdf" | "image" | "txt" | "docx" | "msg" | "eml" | "zip" | "unknown" */
	source_type: string;
	/** Coarse bucket so the dashboard can segment without exact counts. */
	page_bucket: '1' | '2-10' | '11-50' | '51-200' | '201+';
	/** Whether the OCR path was used (true for scanned PDFs / images). */
	used_ocr: boolean;
};

export type RedactionReviewProps = {
	/** "tier1" | "tier2" | "tier3" — which detection tier the reviewer acted on. */
	tier: string;
	/** Entity type (e.g. "bsn", "persoon", "adres"). No content, just the class. */
	entity_type: string;
};

export type ExportCompletedProps = {
	/** Coarse bucket for the number of confirmed redactions on this document. */
	redaction_bucket: '0' | '1-5' | '6-20' | '21-100' | '101+';
	/** Coarse bucket for the page count of the exported document. */
	page_bucket: '1' | '2-10' | '11-50' | '51-200' | '201+';
};

export type LeadCapturedProps = {
	/** Where the form was submitted from. Mirrors `LeadSource` in api/client.ts. */
	source: 'landing' | 'post-export';
	/** Whether the visitor also opted in to the newsletter. */
	newsletter_opt_in: boolean;
};

export type PlausibleEventProps = {
	document_converted: DocumentConvertedProps;
	redaction_confirmed: RedactionReviewProps;
	redaction_rejected: RedactionReviewProps;
	export_completed: ExportCompletedProps;
	/**
	 * #52 — DiWoo / GPP-Woo publication-export bundle. Same shape as the
	 * plain export so the dashboard can compare adoption (how many
	 * reviewers click through to publication-ready output) without
	 * differentiating on document size.
	 */
	publication_export_completed: ExportCompletedProps;
	/**
	 * #45 — successful lead-form submission. The dashboard goal counts
	 * conversions on the "blijf op de hoogte / vraag een teamdemo aan"
	 * funnel, segmented by `source` (landing vs post-export) so we can
	 * see which placement actually converts.
	 */
	lead_captured: LeadCapturedProps;
};

export type PlausibleEventName = keyof PlausibleEventProps;

export function bucketPages(count: number): DocumentConvertedProps['page_bucket'] {
	if (count <= 1) return '1';
	if (count <= 10) return '2-10';
	if (count <= 50) return '11-50';
	if (count <= 200) return '51-200';
	return '201+';
}

export function bucketRedactions(count: number): ExportCompletedProps['redaction_bucket'] {
	if (count === 0) return '0';
	if (count <= 5) return '1-5';
	if (count <= 20) return '6-20';
	if (count <= 100) return '21-100';
	return '101+';
}
