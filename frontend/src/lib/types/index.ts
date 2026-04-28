// ---------------------------------------------------------------------------
// Domain types — mirrors the backend database schema
// ---------------------------------------------------------------------------

export type DocumentStatus =
	| 'uploaded'
	| 'processing'
	| 'review'
	| 'approved'
	| 'exported';

export type DetectionTier = '1' | '2' | '3';

export type ReviewStatus =
	| 'pending'
	| 'auto_accepted'
	| 'accepted'
	| 'rejected'
	| 'edited'
	| 'deferred';

// ---------------------------------------------------------------------------
// Woo article codes (Art. 5.x)
// ---------------------------------------------------------------------------

export type WooArticleCode =
	| '5.1.1c'
	| '5.1.1d'
	| '5.1.1e'
	| '5.1.2a'
	| '5.1.2c'
	| '5.1.2d'
	| '5.1.2e'
	| '5.1.2f'
	| '5.1.2h'
	| '5.1.2i'
	| '5.2'
	| '5.1.5';

// ---------------------------------------------------------------------------
// Entity types detected by the system
// ---------------------------------------------------------------------------

export type EntityType =
	| 'persoon'
	| 'bsn'
	| 'telefoon'
	| 'email'
	| 'adres'
	| 'iban'
	| 'datum'
	| 'geboortedatum'
	| 'postcode'
	| 'kenteken'
	| 'creditcard'
	| 'kvk'
	| 'btw'
	| 'url'
	| 'organisatie'
	// Label-anchored reference numbers — klantnummer, factuurnummer,
	// dossiernummer, kenmerk, … Tiered confidence per label. Span
	// covers the number only so the redacted output still shows the
	// label ("Klantnummer: ███").
	| 'referentie'
	// Reviewer-drawn area redaction (#07). Has no selectable text — the
	// rectangle comes from a Shift+drag on the PDF stage, used for signatures,
	// stamps, photos, or scanned fragments inside an otherwise digital PDF.
	| 'area'
	// #21 — match from the per-document custom wordlist. The reviewer
	// typed the term into the "Eigen zoektermen" panel and the analyze
	// pipeline scanned the full text for every occurrence. These rows
	// come in at `review_status="accepted"` (the reviewer already made
	// the decision by typing the term) with `source="custom_wordlist"`.
	| 'custom';

// ---------------------------------------------------------------------------
// Detection confidence
// ---------------------------------------------------------------------------

export type ConfidenceLevel = 'high' | 'medium' | 'low';

// ---------------------------------------------------------------------------
// Tier 2 reden-voor-niet-lakken (#15, extended for false positives)
//
// Reviewer-assigned label captured on the Niet-lakken path. The field
// originally classified the *person* (burger / ambtenaar / publiek
// functionaris), but in practice the most common reason a reviewer chooses
// Niet lakken is that the detection isn't a person at all — typically a
// CBS-surname collision with a Dutch noun ("Engels", "Bos", "Visser"), a
// place name, or an organisation. `geen_persoon` captures that signal so
// we can distinguish "keep visible because of role" from "keep visible
// because the detector misfired".
//
// The role is orthogonal to the redact/keep decision: Lakken/Niet lakken is
// the reviewer's binary choice, and the role annotates *why*. Setting a
// role does NOT flip `review_status` — the buttons are the single source
// of truth for that.
// ---------------------------------------------------------------------------

export type SubjectRole =
	| 'burger'
	| 'ambtenaar'
	| 'publiek_functionaris'
	| 'geen_persoon';

// ---------------------------------------------------------------------------
// Detection source — where did this row come from?
//
// Used by the redaction log (#19) to distinguish automatic detections
// (regex / Deduce NER / rule / structure / ...) from reviewer-authored
// rows (manual selection, search-and-redact). Surfaced in the log
// table's "Source" column and in the filter bar.
//
// The `llm` value is legacy — kept for backwards compatibility with any
// persisted rows produced before the LLM pass was removed. Nothing in
// the live pipeline produces it anymore.
// ---------------------------------------------------------------------------

export type DetectionSource =
	| 'regex'
	| 'deduce'
	| 'llm'
	| 'manual'
	| 'search_redact'
	// #17 — per-document reference list short-circuit (publiek functionaris).
	| 'reference_list'
	// #14 — structure-engine hit (email header, signature block, salutation).
	| 'structure'
	// #13 — rule-based function-title classifier.
	| 'rule'
	// #21 — per-document custom wordlist ("eigen zoektermen").
	| 'custom_wordlist';

// ---------------------------------------------------------------------------
// Domain models
// ---------------------------------------------------------------------------

export interface Document {
	id: string;
	filename: string;
	page_count: number;
	document_date: string | null;
	status: DocumentStatus;
	created_at: string;
	five_year_warning: boolean;
}

export interface BoundingBox {
	page: number;
	x0: number;
	y0: number;
	x1: number;
	y1: number;
}

export interface Detection {
	id: string;
	document_id: string;
	entity_text?: string;
	entity_type: EntityType;
	tier: DetectionTier;
	confidence: number;
	confidence_level?: ConfidenceLevel;
	woo_article: WooArticleCode | null;
	review_status: ReviewStatus;
	bounding_boxes: BoundingBox[];
	/**
	 * Snapshot of the analyzer's original bboxes, captured server-side the
	 * very first time a reviewer adjusts this detection (#11). Null means
	 * "never adjusted"; a value means `bounding_boxes` currently reflects a
	 * reviewer edit and this is the audit baseline.
	 */
	original_bounding_boxes?: BoundingBox[] | null;
	reasoning: string | null;
	/**
	 * #19 — redaction log. Pipeline label for where the row came from:
	 * `regex`/`deduce`/`rule`/`structure`/... for automatic detections,
	 * `manual` for reviewer-drawn redactions, `search_redact` for bulk
	 * search-and-redact hits. Used for filtering and for the "Auto vs
	 * handmatig" stats tile. (`llm` is legacy — see DetectionSource.)
	 */
	source?: DetectionSource;
	propagated_from: string | null;
	reviewer_id: string | null;
	reviewed_at: string | null;
	is_environmental: boolean;
	/**
	 * #15 — Tier 2 person-role classification. Null when the reviewer has
	 * not yet picked a role for this detection; set to one of the three
	 * values once they click a chip on the card.
	 */
	subject_role?: SubjectRole | null;
	/**
	 * #18 — split/merge audit. `split_from` is the uuid of the detection
	 * that was split to produce this row; `merged_from` is the list of
	 * detection uuids that were merged into this one. Both are null for
	 * rows produced by the analyzer or a plain manual selection, and
	 * populated only on the reviewer-authored products of a split/merge
	 * action.
	 */
	split_from?: string | null;
	merged_from?: string[] | null;
	/**
	 * #20 — character offsets in the server-joined full text. Present on
	 * automatically-detected rows (`regex`, `deduce`, `structure`,
	 * `rule`, `reference_list`), null on reviewer-authored ones (`manual`,
	 * `search_redact`) that have no position in the analyzed text. The
	 * bulk-sweep UI compares these offsets against `StructureSpan` bounds
	 * to decide whether a detection belongs to an email header / signature
	 * block / salutation.
	 */
	start_char?: number | null;
	end_char?: number | null;
}

// ---------------------------------------------------------------------------
// Client-side text extraction (pdf.js output, matches backend ExtractionResult)
// ---------------------------------------------------------------------------

export interface ExtractedTextItem {
	text: string;
	x0: number;
	y0: number;
	x1: number;
	y1: number;
}

export interface PageExtraction {
	pageNumber: number;
	fullText: string;
	textItems: ExtractedTextItem[];
}

export interface ExtractionResult {
	pages: PageExtraction[];
	pageCount: number;
	fullText: string;
}

// ---------------------------------------------------------------------------
// Structure spans (#14) — email headers, signature blocks, salutations.
// Ephemeral: returned with the analysis response so bulk-sweep UI (#20)
// can render "lak dit blok" affordances on top of the PDF. Character
// offsets are into the server-side joined full text.
// ---------------------------------------------------------------------------

export type StructureSpanKind = 'email_header' | 'signature_block' | 'salutation';

export interface StructureSpan {
	kind: StructureSpanKind;
	start_char: number;
	end_char: number;
	confidence: number;
	evidence: string;
}

// ---------------------------------------------------------------------------
// Reference names (#17 — per-document "niet lakken" list)
//
// A reviewer-maintained list of names that should not be redacted in the
// current document — typically the members of the relevant college van
// B&W, gemeenteraad, or other publiek functionaris whose names the
// reviewer knows ahead of time. Matching happens server-side in the
// analyze pipeline against the normalized display name.
// ---------------------------------------------------------------------------

export type ReferenceRoleHint = 'publiek_functionaris' | 'ambtenaar' | 'burger';

export interface ReferenceName {
	id: string;
	document_id: string;
	display_name: string;
	normalized_name: string;
	role_hint: ReferenceRoleHint;
	created_at: string;
}

// ---------------------------------------------------------------------------
// Custom terms (#21 — per-document "eigen zoektermen")
//
// Opposite intent to reference names: a reviewer-maintained list of strings
// that MUST be redacted throughout the current document — a bedrijfsnaam, a
// straatnaam that identifies a specific complaint, the codename of an intern
// project. Matching is case-insensitive substring; `exact` is the only
// implemented mode in v1.
// ---------------------------------------------------------------------------

export type CustomTermMatchMode = 'exact';

export interface CustomTerm {
	id: string;
	document_id: string;
	term: string;
	normalized_term: string;
	match_mode: CustomTermMatchMode;
	woo_article: string;
	created_at: string;
}

// ---------------------------------------------------------------------------
// Page reviews (#10 — page completeness)
// ---------------------------------------------------------------------------

export type PageReviewStatus = 'unreviewed' | 'in_progress' | 'complete' | 'flagged';

// ---------------------------------------------------------------------------
// API request/response types
// ---------------------------------------------------------------------------

export interface UpdateDetectionRequest {
	review_status?: ReviewStatus;
	woo_article?: WooArticleCode;
	motivation_text?: string;
	/**
	 * Boundary adjustment (#11). When present, replaces the detection's
	 * bounding boxes; server also flips `review_status` to "edited" unless
	 * the same request already specifies a status (undo/redo restoring
	 * e.g. "accepted" alongside a bbox revert).
	 */
	bounding_boxes?: BoundingBox[];
	/**
	 * #15 — Tier 2 person-role classification. Sent alone when the reviewer
	 * just clicks a chip, or together with `review_status: 'rejected'` when
	 * they pick `publiek_functionaris` (which implies "don't redact").
	 */
	subject_role?: SubjectRole;
	/**
	 * #15 — undo support: explicitly clear an already set `subject_role`
	 * back to null. Sending `subject_role: undefined` alone would only be
	 * interpreted as "don't touch" by the server; this flag disambiguates.
	 */
	clear_subject_role?: boolean;
}
