/**
 * Per-page review status (#10). Shared between PageStrip, PageReviewActions,
 * PdfViewerToolbar (status dot) and PdfViewer itself. Lives next to the
 * components rather than in the global `$lib/types` because it's purely a
 * UI concept — the parent route stores it in `pageReviewStore`.
 */

export type PageReviewStatusValue = 'unreviewed' | 'in_progress' | 'complete' | 'flagged';

export function pageStatusLabel(status: PageReviewStatusValue): string {
	switch (status) {
		case 'unreviewed':
			return 'Nog niet beoordeeld';
		case 'in_progress':
			return 'In behandeling';
		case 'complete':
			return 'Beoordeeld';
		case 'flagged':
			return 'Gemarkeerd';
	}
}
