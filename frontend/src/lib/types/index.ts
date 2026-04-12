// ---------------------------------------------------------------------------
// Domain types — mirrors the backend database schema
// ---------------------------------------------------------------------------

export type DossierStatus = 'open' | 'in_review' | 'completed';

export type DocumentStatus =
	| 'uploaded'
	| 'processing'
	| 'review'
	| 'approved'
	| 'exported';

export type DetectionTier = 1 | 2 | 3;

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
	| 'rijbewijs';

// ---------------------------------------------------------------------------
// Detection confidence
// ---------------------------------------------------------------------------

export type ConfidenceLevel = 'high' | 'medium' | 'low';

// ---------------------------------------------------------------------------
// Domain models
// ---------------------------------------------------------------------------

export interface Dossier {
	id: string;
	title: string;
	request_number: string;
	organization: string;
	status: DossierStatus;
	created_at: string;
	updated_at: string;
}

export interface Document {
	id: string;
	dossier_id: string;
	filename: string;
	page_count: number;
	document_date: string | null;
	status: DocumentStatus;
	created_at: string;
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
	entity_text: string;
	entity_type: EntityType;
	tier: DetectionTier;
	confidence: number;
	woo_article: WooArticleCode | null;
	review_status: ReviewStatus;
	bounding_boxes: BoundingBox[];
	reasoning: string | null;
	propagated_from: string | null;
	reviewer_id: string | null;
	reviewed_at: string | null;
}

export interface PublicOfficial {
	id: string;
	dossier_id: string;
	name: string;
	role: string | null;
}

export interface MotivationText {
	id: string;
	detection_id: string;
	text: string;
	is_edited: boolean;
}

// ---------------------------------------------------------------------------
// API request/response types
// ---------------------------------------------------------------------------

export interface CreateDossierRequest {
	title: string;
	request_number: string;
	organization: string;
}

export interface UpdateDetectionRequest {
	review_status: ReviewStatus;
	woo_article?: WooArticleCode;
	motivation_text?: string;
}

export interface DossierWithStats extends Dossier {
	document_count: number;
	detection_counts: {
		total: number;
		by_tier: Record<DetectionTier, number>;
		by_status: Record<ReviewStatus, number>;
	};
}
