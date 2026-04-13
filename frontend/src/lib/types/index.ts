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
	| 'telefoonnummer'
	| 'email'
	| 'adres'
	| 'iban'
	| 'gezondheid'
	| 'datum'
	| 'postcode'
	| 'kenteken'
	| 'creditcard'
	| 'paspoort'
	| 'rijbewijs'
	// Reviewer-drawn area redaction (#07). Has no selectable text — the
	// rectangle comes from a Shift+drag on the PDF stage, used for signatures,
	// stamps, photos, or scanned fragments inside an otherwise digital PDF.
	| 'area';

// ---------------------------------------------------------------------------
// Detection confidence
// ---------------------------------------------------------------------------

export type ConfidenceLevel = 'high' | 'medium' | 'low';

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
	reasoning: string | null;
	propagated_from: string | null;
	reviewer_id: string | null;
	reviewed_at: string | null;
	is_environmental: boolean;
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
// API request/response types
// ---------------------------------------------------------------------------

export interface UpdateDetectionRequest {
	review_status: ReviewStatus;
	woo_article?: WooArticleCode;
	motivation_text?: string;
}
