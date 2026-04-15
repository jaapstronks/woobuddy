<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
	import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';

	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { detectionStore } from '$lib/stores/detections.svelte';
	import { reviewStore } from '$lib/stores/review.svelte';
	import { manualSelectionStore } from '$lib/stores/manual-selection.svelte';
	import { searchStore } from '$lib/stores/search.svelte';
	import { pageReviewStore } from '$lib/stores/page-reviews.svelte';
	import { referenceNamesStore } from '$lib/stores/reference-names.svelte';
	import { customTermsStore } from '$lib/stores/custom-terms.svelte';
	import {
		undoStore,
		CreateManualCommand,
		ReviewStatusCommand,
		BoundaryAdjustCommand,
		ChangeArticleCommand,
		SetSubjectRoleCommand,
		AddReferenceNameCommand,
		RemoveReferenceNameCommand,
		AddCustomTermCommand,
		RemoveCustomTermCommand,
		SweepBlockCommand,
		SameNameSweepCommand,
		BatchCommand,
		type Command
	} from '$lib/stores/undo.svelte';
	import { structureSpansStore } from '$lib/stores/structure-spans.svelte';
	import {
		spanKey,
		detectionInsideSpan,
		findSameNameDetections
	} from '$lib/utils/structure-matching';
	import type { StructureSpan, ReviewStatus } from '$lib/types';
	import PdfViewer from '$lib/components/review/PdfViewer.svelte';
	import SelectionActionBar from '$lib/components/review/SelectionActionBar.svelte';
	import ManualRedactionForm from '$lib/components/review/ManualRedactionForm.svelte';
	import SearchPanel from '$lib/components/review/SearchPanel.svelte';
	import type { SearchOccurrence } from '$lib/services/search-redact';
	import DetectionList from '$lib/components/review/DetectionList.svelte';
	import ReferenceNamesPanel from '$lib/components/review/ReferenceNamesPanel.svelte';
	import CustomTermsPanel from '$lib/components/review/CustomTermsPanel.svelte';
	import DetectionFilters from '$lib/components/review/DetectionFilters.svelte';
	import ProgressBar from '$lib/components/review/ProgressBar.svelte';
	import BatchActions from '$lib/components/review/BatchActions.svelte';
	import KeyboardShortcuts from '$lib/components/review/KeyboardShortcuts.svelte';
	import ReviewSkeleton from '$lib/components/review/ReviewSkeleton.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import LeadCaptureForm from '$lib/components/marketing/LeadCaptureForm.svelte';
	import { getPdf, storePdf } from '$lib/services/pdf-store';
	import { extractText, loadPdfDocument } from '$lib/services/pdf-text-extractor';
	import { exportRedactedPdf, downloadBlob } from '$lib/services/export-service';
	import { buildDebugExport, downloadDebugExport } from '$lib/services/debug-export';
	import { computeSplitBboxes } from '$lib/services/boundary-edit-geometry';
	import { HIGH_CONFIDENCE_THRESHOLD } from '$lib/config/thresholds';
	import type { WooArticleCode, EntityType, DetectionTier, SubjectRole } from '$lib/types';
	import {
		ArrowLeft,
		PanelRightClose,
		PanelRightOpen,
		Download,
		FileJson,
		RotateCw,
		Undo2,
		Redo2,
		Search,
		ListOrdered,
		StretchHorizontal,
		Maximize2,
		X
	} from 'lucide-svelte';

	const docId = $derived(page.params.docId!);

	let pdfData = $state<ArrayBuffer | null>(null);
	let needsPdf = $state(false);
	let exporting = $state(false);
	let exportError = $state<string | null>(null);
	// #45 — After a successful export we surface the lead-capture form as a
	// dismissible card. The flag is reviewer-session-scoped; dismissing (or
	// successfully submitting) hides it until the next export completes.
	let showPostExportLead = $state(false);
	// Exposed by PdfViewer via `bind:stageEl` — the manual selection bar/form
	// use this element's bounding rect to project page-space anchors to
	// viewport pixels, so they follow the PDF through scroll and zoom.
	let pdfStageEl = $state<HTMLDivElement | null>(null);
	// Scrollable wrapper around the PDF stage. We observe its size to drive
	// fit-to-width / fit-to-page scaling — the natural page size from
	// PdfViewer divided by this container's width gives the right scale.
	let pdfScrollEl = $state<HTMLDivElement | null>(null);
	// PdfViewer exposes `flashDetections` via `bind:this` for the undo effect
	// below — the viewer flashes affected overlays after each undo/redo push.
	let pdfViewerRef = $state<{ flashDetections: (ids: string[]) => void } | null>(null);

	// Recompute fit-to-width / fit-to-page whenever the PDF column is
	// resized (sidebar toggle, window resize) or the natural page size
	// becomes known. Re-runs when the reviewer flips the fit mode too, so
	// switching from explicit zoom back to a fit option snaps immediately.
	$effect(() => {
		if (!pdfScrollEl) return;
		void reviewStore.pdfFitMode;
		void reviewStore.pdfPageNaturalSize;

		const recompute = () => {
			if (!pdfScrollEl) return;
			reviewStore.applyFit(pdfScrollEl.clientWidth, pdfScrollEl.clientHeight);
		};
		recompute();

		const ro = new ResizeObserver(recompute);
		ro.observe(pdfScrollEl);
		return () => ro.disconnect();
	});

	// Load document + detections + local PDF. The undo stack is per-document
	// and in-memory only — switching docs or reloading should not leave stale
	// commands that target rows from a different document.
	$effect(() => {
		void docId;
		undoStore.clear();
		pageReviewStore.clear();
		referenceNamesStore.clear();
		customTermsStore.clear();
		reviewStore.loadDocument(docId);
		loadPdfAndDetections(docId);
		pageReviewStore.load(docId);
		// #17 — load the per-document reference list so the panel shows
		// the reviewer's previous entries on reload, and so a re-analysis
		// triggered by an add/remove has the full list on hand.
		referenceNamesStore.load(docId);
		// #21 — same story for the per-document custom wordlist. Loaded
		// before the first analyze run so the pipeline sees it on page
		// refresh, not only after the reviewer touches the panel.
		customTermsStore.load(docId);
		// #20 — hydrate the structure-spans cache from sessionStorage so the
		// bulk-sweep chips show up after a soft reload (analyze isn't
		// re-run when the page refreshes).
		structureSpansStore.load(docId);
		return () => {
			undoStore.clear();
			pageReviewStore.clear();
			referenceNamesStore.clear();
			customTermsStore.clear();
		};
	});

	// Flash affected overlays after any undo/redo/push that touches detections.
	$effect(() => {
		const ids = undoStore.lastAffected;
		if (ids.length === 0) return;
		pdfViewerRef?.flashDetections(ids);
	});

	/**
	 * #19 — deep-link from the redaction log. When a reviewer clicks
	 * "Bekijk" in the log table we navigate here with `?detection=<id>`;
	 * once detections are loaded, auto-select that row and scroll the PDF
	 * to its page. The param is consumed after the first successful
	 * selection so a stray rerun of the effect does not keep re-scrolling.
	 *
	 * Consuming means stripping the query from the URL with history
	 * replace — no reload, no extra history entry, and the review page
	 * behaves like a normal in-app navigation the moment the jump has
	 * happened.
	 */
	let consumedDetectionQuery = $state<string | null>(null);
	$effect(() => {
		const target = page.url.searchParams.get('detection');
		if (!target) return;
		if (consumedDetectionQuery === target) return;
		// Wait for the detections store to actually contain this id —
		// navigating in from the log means detections are already hydrated,
		// but on a full reload we could land here before `load()` resolves.
		const det = detectionStore.byId[target];
		if (!det) return;
		handleSelectDetection(target);
		consumedDetectionQuery = target;
		const cleaned = new URL(page.url);
		cleaned.searchParams.delete('detection');
		history.replaceState(history.state, '', cleaned.pathname + cleaned.search);
	});

	async function loadPdfAndDetections(documentId: string) {
		const stored = await getPdf(documentId);
		if (stored) {
			pdfData = stored.pdfBytes;
			await extractAndSetText(stored.pdfBytes);
		} else {
			needsPdf = true;
		}
		await detectionStore.load(documentId);
	}

	async function extractAndSetText(bytes: ArrayBuffer) {
		// `loadPdfDocument` wraps pdf.js errors into a typed `PdfError` —
		// we swallow errors here because the review screen already has a
		// valid detections payload from the server; the client-side extraction
		// is only needed for features like manual search-and-redact. A scanned
		// or corrupt PDF should not break the review view.
		try {
			const doc = await loadPdfDocument(bytes);
			const extraction = await extractText(doc);
			detectionStore.setExtraction(extraction);
		} catch (e) {
			console.warn('Review page: could not re-extract text from PDF', e);
		}
	}

	async function handleFileSelect(event: Event) {
		const input = event.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;

		const bytes = await file.arrayBuffer();
		await storePdf(docId, file.name, bytes);
		pdfData = bytes;
		needsPdf = false;
		await extractAndSetText(bytes);
		await detectionStore.load(docId);
	}

	function openPdfFilePicker() {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = '.pdf';
		input.onchange = handleFileSelect;
		input.click();
	}

	function handleDebugExport() {
		// Diagnostic dump of the analyzer's output for the current document.
		// Runs entirely client-side: pulls from the in-memory detection
		// store, no server round-trip. Intended for comparing the sidebar
		// against a fixture PDF when triaging false positives/negatives.
		const payload = buildDebugExport(reviewStore.document, detectionStore.all);
		const base = reviewStore.document?.filename ?? `document-${docId}`;
		downloadDebugExport(payload, base);
	}

	async function handleExport() {
		if (!pdfData) {
			exportError = 'Geen PDF beschikbaar om te exporteren.';
			return;
		}
		exporting = true;
		exportError = null;
		try {
			const filename = reviewStore.document?.filename ?? 'document.pdf';
			const redacted = await exportRedactedPdf(docId, pdfData);
			downloadBlob(redacted, `gelakt_${filename}`);
			showPostExportLead = true;
		} catch (e) {
			exportError = e instanceof Error ? e.message : 'Export mislukt';
		} finally {
			exporting = false;
		}
	}

	// Progress data
	const progressTiers = $derived([
		{ tier: '1' as const, reviewed: detectionStore.counts.reviewedByTier['1'], total: detectionStore.counts.byTier['1'] },
		{ tier: '2' as const, reviewed: detectionStore.counts.reviewedByTier['2'], total: detectionStore.counts.byTier['2'] },
		{ tier: '3' as const, reviewed: detectionStore.counts.reviewedByTier['3'], total: detectionStore.counts.byTier['3'] }
	]);

	// Navigate PDF to the page containing a detection. A plain click picks
	// the single selection; Ctrl/Cmd+click toggles the detection into the
	// merge-staging set (#18) without moving the single selection. Split
	// mode (#18) is also cancelled on any click — picking a new target or
	// queueing a merge both imply the reviewer is no longer waiting to
	// place a split point on the previously selected row.
	function handleSelectDetection(id: string, modifier?: 'ctrl') {
		if (modifier === 'ctrl') {
			detectionStore.toggleMultiSelect(id);
			splitPendingId = null;
			return;
		}
		splitPendingId = null;
		detectionStore.select(id);
		const det = detectionStore.byId[id];
		if (det?.bounding_boxes?.length) {
			const targetPage = det.bounding_boxes[0].page;
			if (targetPage !== reviewStore.currentPage) {
				reviewStore.setPage(targetPage);
			}
		}
	}

	// -----------------------------------------------------------------------
	// Split and merge (#18)
	// -----------------------------------------------------------------------

	/** Id of the detection waiting for a split-point click on the PDF, or null. */
	let splitPendingId = $state<string | null>(null);

	function handleStartSplit() {
		const selected = detectionStore.selected;
		if (!selected || !selected.bounding_boxes?.length) return;
		splitPendingId = selected.id;
	}

	function handleCancelSplit() {
		splitPendingId = null;
	}

	/**
	 * The reviewer clicked inside the split-target detection's overlay.
	 * `computeSplitBboxes` derives the two new bbox sets from the target
	 * bbox and the clicked x-coordinate; we forward them to the store.
	 */
	async function handleSplitPointClick(args: {
		detectionId: string;
		bboxIndex: number;
		pdfX: number;
		pdfY: number;
	}) {
		const det = detectionStore.byId[args.detectionId];
		if (!det || !det.bounding_boxes?.length) {
			splitPendingId = null;
			return;
		}
		const split = computeSplitBboxes(det.bounding_boxes, args.bboxIndex, args.pdfX);
		if (!split) {
			splitPendingId = null;
			return;
		}

		// Clear pending state before the async call — if the request fails
		// the reviewer should be able to re-trigger split without being stuck
		// in a stale pending mode.
		splitPendingId = null;
		await detectionStore.split(args.detectionId, split.bboxesA, split.bboxesB);
	}

	async function handleMergeConfirm() {
		await detectionStore.merge();
	}

	/**
	 * Build a ReviewStatusCommand for a detection, capturing its current
	 * review_status and woo_article at command-construction time so that
	 * undoing the action restores the exact prior state.
	 */
	function makeStatusCommand(
		id: string,
		nextStatus: 'accepted' | 'rejected' | 'deferred' | 'pending',
		nextArticle?: WooArticleCode
	): ReviewStatusCommand | null {
		const det = detectionStore.byId[id];
		if (!det) return null;
		return new ReviewStatusCommand(
			id,
			det.review_status,
			nextStatus,
			det.woo_article ?? undefined,
			nextArticle ?? det.woo_article ?? undefined
		);
	}

	/**
	 * When a detection on a page is reviewed, nudge that page from
	 * `unreviewed` to `in_progress` (#10 auto-status). Pages the reviewer
	 * has already marked `complete` or `flagged` are left alone — those
	 * are deliberate decisions and must not be silently downgraded.
	 *
	 * We bump every page the detection touches, since a single detection
	 * can span a page break. `markInProgressIfUnreviewed` is itself a
	 * no-op on pages already past `unreviewed`, so the fire-and-forget
	 * calls are safe to duplicate.
	 */
	function touchDetectionPages(id: string) {
		const det = detectionStore.byId[id];
		if (!det?.bounding_boxes) return;
		const pages = new Set(det.bounding_boxes.map((b) => b.page));
		for (const p of pages) void pageReviewStore.markInProgressIfUnreviewed(p);
	}

	function handleAccept(id: string) {
		const cmd = makeStatusCommand(id, 'accepted');
		if (cmd) {
			undoStore.push(cmd);
			touchDetectionPages(id);
		}
	}

	function handleRedactWithArticle(id: string, article: WooArticleCode) {
		const cmd = makeStatusCommand(id, 'accepted', article);
		if (cmd) {
			undoStore.push(cmd);
			touchDetectionPages(id);
		}
	}

	function handleReject(id: string) {
		const cmd = makeStatusCommand(id, 'rejected');
		if (cmd) {
			undoStore.push(cmd);
			touchDetectionPages(id);
		}
	}

	function handleDefer(id: string) {
		const cmd = makeStatusCommand(id, 'deferred');
		if (cmd) {
			undoStore.push(cmd);
			touchDetectionPages(id);
		}
	}

	// Revert a reviewed detection back to `pending` so the reviewer sees the
	// full decision form again. Used by Tier 3 "Opnieuw beoordelen" where
	// re-accepting requires picking an article and writing motivation — we
	// can't one-click flip it back to accepted.
	function handleReopen(id: string) {
		const cmd = makeStatusCommand(id, 'pending');
		if (cmd) {
			undoStore.push(cmd);
			touchDetectionPages(id);
		}
	}

	// Page completeness (#10). The mark button toggles between
	// `unreviewed`/`in_progress` and `complete`; the flag button toggles
	// `flagged`. Both persist immediately via the store.
	function handleMarkPageReviewed(pageNum: number) {
		const current = pageReviewStore.getStatus(pageNum);
		if (current === 'complete') {
			void pageReviewStore.setStatus(pageNum, 'unreviewed');
		} else {
			void pageReviewStore.markComplete(pageNum);
		}
	}

	function handleFlagPage(pageNum: number) {
		const current = pageReviewStore.getStatus(pageNum);
		if (current === 'flagged') {
			void pageReviewStore.setStatus(pageNum, 'unreviewed');
		} else {
			void pageReviewStore.flag(pageNum);
		}
	}

	// Keyboard: P marks current page reviewed, F flags it — edit mode only
	// so letter shortcuts don't collide with the review-mode accept/reject
	// hotkeys (A/R/D).
	function handleKeyMarkPage() {
		if (reviewStore.mode !== 'edit') return;
		handleMarkPageReviewed(reviewStore.currentPage);
	}
	function handleKeyFlagPage() {
		if (reviewStore.mode !== 'edit') return;
		handleFlagPage(reviewStore.currentPage);
	}

	// Progress text shown beside the tier progress bar.
	const pageProgressText = $derived.by(() => {
		const total = reviewStore.totalPages;
		if (total === 0) return '';
		const complete = pageReviewStore.completedCount;
		const openDetections = detectionStore.counts.byStatus['pending'] ?? 0;
		const base = `${complete}/${total} pagina's beoordeeld`;
		if (openDetections > 0) return `${base} · ${openDetections} detecties openstaand`;
		return base;
	});

	function handleKeyAccept() {
		if (detectionStore.selectedId) handleAccept(detectionStore.selectedId);
	}
	function handleKeyReject() {
		if (detectionStore.selectedId) handleReject(detectionStore.selectedId);
	}
	function handleKeyDefer() {
		if (detectionStore.selectedId) handleDefer(detectionStore.selectedId);
	}

	// #15 — Tier 2 card in-place article change. Pushes a dedicated command
	// onto the undo stack so Ctrl+Z restores the previous Woo-grond exactly.
	async function handleChangeArticle(id: string, nextArticle: WooArticleCode) {
		const det = detectionStore.byId[id];
		if (!det) return;
		if (det.woo_article === nextArticle) return;
		const cmd = new ChangeArticleCommand(id, det.woo_article, nextArticle);
		try {
			await undoStore.push(cmd);
		} catch {
			// detectionStore.error carries the message.
		}
	}

	// #15 — Tier 2 role classification chip. Pushes a single command that
	// captures the previous role AND status (because the publiek_functionaris
	// path also flips the status to rejected). Undo restores both.
	async function handleSetSubjectRole(id: string, role: SubjectRole) {
		const det = detectionStore.byId[id];
		if (!det) return;
		if (det.subject_role === role) return;
		const cmd = new SetSubjectRoleCommand(
			id,
			det.subject_role ?? null,
			role,
			det.review_status
		);
		try {
			await undoStore.push(cmd);
			touchDetectionPages(id);
		} catch {
			// detectionStore.error carries the message.
		}
	}

	// -----------------------------------------------------------------------
	// #20 — bulk sweeps (email header / signature block / same-name)
	// -----------------------------------------------------------------------

	/**
	 * Sweep every pending detection inside the structure span identified by
	 * `key`. Detections that already have a non-pending decision are left
	 * alone — the reviewer explicitly decided those and must not be
	 * overwritten. Builds a single undo command covering the whole block.
	 */
	async function handleSweepBlock(key: string) {
		const span = structureSpansStore.spans.find((s) => spanKey(s) === key);
		if (!span) return;
		if (span.kind !== 'email_header' && span.kind !== 'signature_block') return;

		// Resolve targets against the full detection list, not the filtered
		// view — the reviewer clicked "sweep this whole block" and expects
		// every pending row inside it to be accepted regardless of the
		// current sidebar filter.
		const inBlock = detectionStore.all.filter(
			(d) => d.review_status === 'pending' && detectionInsideSpan(d, span)
		);
		if (inBlock.length === 0) return;

		const targets = inBlock.map((d) => ({
			id: d.id,
			previousStatus: d.review_status,
			previousArticle: d.woo_article ?? null,
			nextArticle: d.woo_article ?? null
		}));
		const cmd = new SweepBlockCommand(span.kind, targets);
		try {
			await undoStore.push(cmd);
			for (const t of targets) touchDetectionPages(t.id);
		} catch {
			// detectionStore.error already carries the banner message.
		}
	}

	/**
	 * Apply the selected detection's in-card decision to every other
	 * occurrence of the same normalized name. The "decision" here means
	 * accept: in practice the reviewer clicks the link on a pending card
	 * right as they're about to accept it, and the expectation is that
	 * every other identical row gets the same treatment. Rows that already
	 * have an explicit non-pending decision are skipped — we never
	 * overwrite a reviewer's prior choice.
	 */
	async function handleSameNameSweep(detectionId: string) {
		const target = detectionStore.byId[detectionId];
		if (!target || !target.entity_text) return;

		const matches = findSameNameDetections(target, detectionStore.all);
		// Only rows still awaiting a decision are swept; the target itself is
		// always included so the action feels like "click once, whole name
		// handled" even if the reviewer forgot to press A first.
		const pending = matches.filter((d) => d.review_status === 'pending');
		if (pending.length === 0) return;

		const nextStatus: ReviewStatus = 'accepted';
		const targets = pending.map((d) => ({
			id: d.id,
			previousStatus: d.review_status
		}));
		const cmd = new SameNameSweepCommand(target.entity_text, nextStatus, targets);
		try {
			await undoStore.push(cmd);
			for (const t of targets) touchDetectionPages(t.id);
		} catch {
			// detectionStore.error already carries the banner message.
		}
	}

	/**
	 * Shift+H / Shift+S keyboard handlers. Resolve the span enclosing the
	 * currently selected detection and delegate to `handleSweepBlock`.
	 * No-op if there is no selection, no char offsets, or no matching span
	 * of the requested kind — silent failure is the right UX here, the
	 * reviewer will just see nothing happen and try a different detection.
	 */
	function findEnclosingSpan(
		detectionId: string,
		kind: 'email_header' | 'signature_block'
	): StructureSpan | null {
		const det = detectionStore.byId[detectionId];
		if (!det) return null;
		const candidates = structureSpansStore.spans.filter(
			(s) => s.kind === kind && detectionInsideSpan(det, s)
		);
		if (candidates.length === 0) return null;
		// Narrowest enclosing span wins — matches the sidebar chip assignment.
		return candidates.sort(
			(a, b) => a.end_char - a.start_char - (b.end_char - b.start_char)
		)[0];
	}

	function handleKeySweepHeader() {
		const id = detectionStore.selectedId;
		if (!id) return;
		const span = findEnclosingSpan(id, 'email_header');
		if (!span) return;
		void handleSweepBlock(spanKey(span));
	}

	function handleKeySweepSignature() {
		const id = detectionStore.selectedId;
		if (!id) return;
		const span = findEnclosingSpan(id, 'signature_block');
		if (!span) return;
		void handleSweepBlock(spanKey(span));
	}

	function handleSaveMotivation(id: string, text: string) {
		// Motivation edits are not currently part of the undo stack — they
		// happen inside a form with its own cancel path, and the new command
		// type for motivation-only changes isn't worth the surface area yet.
		detectionStore.review(id, { review_status: 'edited', motivation_text: text });
	}

	/**
	 * Boundary adjustment commit (#11). The PdfViewer owns the edit state
	 * and hands us the final bbox set when the reviewer clicks Opslaan or
	 * presses Enter. We capture the current (pre-adjust) bboxes + status
	 * from the store so the command can reverse cleanly — after the push
	 * they'll already be overwritten.
	 */
	async function handleBoundaryAdjust(
		detectionId: string,
		nextBboxes: import('$lib/types').BoundingBox[]
	) {
		const current = detectionStore.byId[detectionId];
		if (!current) return;
		const cmd = new BoundaryAdjustCommand(
			detectionId,
			current.bounding_boxes.map((b) => ({ ...b })),
			nextBboxes,
			current.review_status
		);
		try {
			await undoStore.push(cmd);
		} catch {
			// detectionStore.error carries the message; the banner will show.
		}
	}

	async function handleFormConfirm(payload: {
		article: WooArticleCode;
		entityType: EntityType;
		tier: DetectionTier;
		motivation: string;
	}) {
		const selection = manualSelectionStore.selection;
		if (!selection) return;
		const cmd = new CreateManualCommand({
			documentId: docId,
			bboxes: selection.bboxes,
			selectedText: selection.text,
			entityType: payload.entityType,
			tier: payload.tier,
			wooArticle: payload.article,
			motivation: payload.motivation
		});
		try {
			await undoStore.push(cmd);
		} catch {
			// detectionStore.error already has the message; fall through and
			// close the form so the reviewer sees the banner.
		}
		manualSelectionStore.cancel();
	}

	async function handleAcceptAllTier1() {
		const children = buildAcceptBatch(
			detectionStore.all.filter((d) => d.tier === '1' && d.review_status === 'pending')
		);
		if (children.length === 0) return;
		await undoStore.push(new BatchCommand(`Accepteer alle Tier 1 (${children.length})`, children));
	}

	async function handleAcceptHighConfidenceTier2() {
		const children = buildAcceptBatch(
			detectionStore.all.filter(
				(d) =>
					d.tier === '2' &&
					d.review_status === 'pending' &&
					d.confidence >= HIGH_CONFIDENCE_THRESHOLD
			)
		);
		if (children.length === 0) return;
		await undoStore.push(
			new BatchCommand(`Accepteer hoge-zekerheid Tier 2 (${children.length})`, children)
		);
	}

	function buildAcceptBatch(dets: typeof detectionStore.all): Command[] {
		return dets.map(
			(d) =>
				new ReviewStatusCommand(
					d.id,
					d.review_status,
					'accepted',
					d.woo_article ?? undefined,
					d.woo_article ?? undefined
				)
		);
	}

	// -----------------------------------------------------------------------
	// Search-and-redact (#09)
	// -----------------------------------------------------------------------

	function handleJumpToOccurrence(occ: SearchOccurrence) {
		if (occ.page !== reviewStore.currentPage) {
			reviewStore.setPage(occ.page);
		}
	}

	async function handleRedactOccurrences(payload: {
		occurrences: SearchOccurrence[];
		article: WooArticleCode;
		entityType: EntityType;
		tier: DetectionTier;
		motivation: string;
	}) {
		if (payload.occurrences.length === 0) return;
		const children: Command[] = payload.occurrences.map(
			(occ) =>
				new CreateManualCommand({
					documentId: docId,
					bboxes: occ.bboxes,
					// `matchText` is client-only — kept in the in-memory detection
					// so the sidebar can show it, never sent to the server.
					selectedText: occ.matchText,
					entityType: payload.entityType,
					tier: payload.tier,
					wooArticle: payload.article,
					motivation: payload.motivation,
					source: 'search_redact'
				})
		);
		try {
			await undoStore.push(
				new BatchCommand(
					`Zoek & lak (${children.length})`,
					children
				)
			);
		} catch {
			// detectionStore.error already carries the message — the banner
			// above the viewer will render it.
		}
	}

	// Search highlights consumed by PdfViewer — strip the UI-only fields
	// (context, matchText) so the viewer stays agnostic of the store.
	const searchHighlights = $derived(
		searchStore.open
			? searchStore.results.map((r) => ({
					id: r.id,
					page: r.page,
					bboxes: r.bboxes,
					alreadyRedacted: r.alreadyRedacted
				}))
			: []
	);

	// -----------------------------------------------------------------------
	// Reference-names panel (#17)
	// -----------------------------------------------------------------------

	/**
	 * Re-run the analyze pipeline with the current extraction and the
	 * latest reference-name list. Called after every add/remove (and
	 * every undo/redo of those) so newly-matched detections flip to
	 * `rejected` in place and previously-rejected ones flip back to
	 * `pending`. No-op if the extraction isn't loaded yet (e.g. the user
	 * is still picking a PDF after a reload) — the panel is still
	 * usable, the pipeline just won't re-run until the extraction is
	 * available on the next mount.
	 */
	async function reanalyzeWithReferenceList() {
		const extraction = detectionStore.extraction;
		if (!extraction) return;
		// #17 + #21 — the reference list and the custom wordlist are
		// both per-document reviewer lists that feed into the same
		// analyze pass. Threading them together here (instead of via
		// two separate analyze calls) keeps the pipeline deterministic:
		// the server merges overlapping hits in one pass.
		await detectionStore.analyze(
			docId,
			extraction.pages,
			referenceNamesStore.displayNames,
			customTermsStore.analyzePayload
		);
	}

	async function handleAddReferenceName(displayName: string) {
		const cmd = new AddReferenceNameCommand(displayName, reanalyzeWithReferenceList);
		try {
			await undoStore.push(cmd);
		} catch {
			// referenceNamesStore.error carries the message — the panel
			// renders it inline so the reviewer sees the banner.
		}
	}

	async function handleRemoveReferenceName(id: string, displayName: string) {
		const cmd = new RemoveReferenceNameCommand(id, displayName, reanalyzeWithReferenceList);
		try {
			await undoStore.push(cmd);
		} catch {
			// referenceNamesStore.error carries the message.
		}
	}

	// #21 — per-document custom wordlist handlers. Same shape as the
	// reference-name variants above; the re-analysis callback is the
	// shared one so both features contribute to a single pipeline pass.
	async function handleAddCustomTerm(term: string, wooArticle: string) {
		const cmd = new AddCustomTermCommand(term, wooArticle, reanalyzeWithReferenceList);
		try {
			await undoStore.push(cmd);
		} catch {
			// customTermsStore.error carries the message.
		}
	}

	async function handleRemoveCustomTerm(id: string, term: string) {
		// Look up the full row so reverse() can re-create it with the
		// same Woo-artikel the reviewer originally picked.
		const existing = customTermsStore.terms.find((t) => t.id === id);
		const wooArticle = existing?.woo_article ?? '5.1.2e';
		const cmd = new RemoveCustomTermCommand(
			id,
			term,
			wooArticle,
			reanalyzeWithReferenceList
		);
		try {
			await undoStore.push(cmd);
		} catch {
			// customTermsStore.error carries the message.
		}
	}

	// Map from normalized term → number of live `custom` detections. For
	// each known term we count detections whose reasoning contains
	// `'<term>'` (the pipeline writes "Zoekterm '<term>' uit ..." so the
	// quoted form is unambiguous). Iterating terms × custom-detections is
	// cheap — term lists are short and custom detections are a tiny
	// fraction of the total — and it avoids regex-parsing UI strings.
	const customTermMatchCounts = $derived.by(() => {
		const counts: Record<string, number> = {};
		const customDetections = detectionStore.all.filter((d) => d.entity_type === 'custom');
		for (const t of customTermsStore.terms) {
			const needle = `'${t.term}'`;
			counts[t.normalized_term] = customDetections.filter(
				(d) => d.reasoning?.includes(needle) ?? false
			).length;
		}
		return counts;
	});

	async function handleUndo() {
		try {
			await undoStore.undo();
		} catch (e) {
			console.warn('Undo mislukt', e);
		}
	}

	async function handleRedo() {
		try {
			await undoStore.redo();
		} catch (e) {
			console.warn('Redo mislukt', e);
		}
	}
</script>

<svelte:head>
	<title>Review — WOO Buddy</title>
</svelte:head>

<KeyboardShortcuts
	onAccept={handleKeyAccept}
	onReject={handleKeyReject}
	onDefer={handleKeyDefer}
	onNext={() => { detectionStore.selectNext(); if (detectionStore.selectedId) handleSelectDetection(detectionStore.selectedId); }}
	onPrev={() => { detectionStore.selectPrevious(); if (detectionStore.selectedId) handleSelectDetection(detectionStore.selectedId); }}
	onToggleMode={() => reviewStore.toggleMode()}
	onUndo={handleUndo}
	onRedo={handleRedo}
	onMarkPage={handleKeyMarkPage}
	onFlagPage={handleKeyFlagPage}
	onSweepHeader={handleKeySweepHeader}
	onSweepSignature={handleKeySweepSignature}
	onOpenSearch={() => {
		searchStore.setOpen(true);
		if (!reviewStore.sidebarOpen) reviewStore.toggleSidebar();
	}}
/>

<div class="flex h-full flex-col">
	<!-- Top bar: back + filters + progress + export + sidebar toggle -->
	<div class="flex shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-4 py-2">
		<a
			href="/"
			class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-neutral hover:bg-gray-100 hover:text-gray-900"
			title="Terug naar start"
		>
			<ArrowLeft size={16} />
			<span class="hidden sm:inline">Terug</span>
		</a>
		<div class="h-5 w-px bg-gray-200"></div>
		<div class="flex flex-1 flex-wrap items-center justify-between gap-3">
			<DetectionFilters
				currentTier={detectionStore.filters.tier}
				currentStatus={detectionStore.filters.status}
				currentEntityType={detectionStore.filters.entityType}
				onFilterChange={(key, val) => detectionStore.setFilter(key, val)}
				onClear={() => detectionStore.clearFilters()}
			/>
			<div class="flex items-center gap-4">
				<ProgressBar tiers={progressTiers} />
				{#if pageProgressText}
					<span class="text-xs text-neutral">{pageProgressText}</span>
				{/if}
			</div>
		</div>
		<div class="h-5 w-px bg-gray-200"></div>
		<sl-tooltip content="Lak-logboek">
			<sl-button size="small" variant="default" onclick={() => goto(`/review/${docId}/log`)}>
				<span slot="prefix"><ListOrdered size={14} /></span>
				Logboek
			</sl-button>
		</sl-tooltip>
		<sl-tooltip content="Zoek & Lak (Ctrl+F)">
			<sl-button
				size="small"
				variant={searchStore.open ? 'primary' : 'default'}
				onclick={() => {
					searchStore.toggle();
					if (searchStore.open && !reviewStore.sidebarOpen) reviewStore.toggleSidebar();
				}}
			>
				<span style="display: inline-flex; align-items: center;"><Search size={14} /></span>
			</sl-button>
		</sl-tooltip>
		<sl-tooltip content="Exporteer detecties als JSON (diagnostiek)">
			<sl-button
				size="small"
				variant="text"
				onclick={handleDebugExport}
				disabled={detectionStore.all.length === 0}
			>
				<FileJson size={14} />
			</sl-button>
		</sl-tooltip>
		<sl-button size="small" variant="primary" onclick={handleExport} disabled={exporting || !pdfData}>
			{#if exporting}
				<sl-spinner slot="prefix" style="font-size: 1rem; --indicator-color: white;"></sl-spinner>
				Exporteren...
			{:else}
				<span slot="prefix"><Download size={14} /></span>
				Gelakte PDF
			{/if}
		</sl-button>
		<sl-tooltip content={reviewStore.sidebarOpen ? 'Verberg detecties' : 'Toon detecties'}>
			<sl-button size="small" variant="text" onclick={() => reviewStore.toggleSidebar()}>
				{#if reviewStore.sidebarOpen}
					<PanelRightClose size={16} />
				{:else}
					<PanelRightOpen size={16} />
				{/if}
			</sl-button>
		</sl-tooltip>
	</div>

	{#if detectionStore.loading || reviewStore.loading}
		<!-- Skeleton matches the real two-column layout so the hand-off to
		     the live PDF + detection sidebar has no layout shift. -->
		<ReviewSkeleton />
	{:else if reviewStore.error && !reviewStore.document}
		<!-- Fatal load error: the document itself couldn't be fetched, so
		     there is nothing to show. Detection-store errors (e.g. from a
		     failed manual redaction POST) are handled as a dismissible
		     banner below — they must not tear down the review screen. -->
		<div class="m-4">
			<Alert variant="danger">{reviewStore.error}</Alert>
		</div>
	{:else}
		{#if detectionStore.error}
			<div class="mx-4 mt-3 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
				<span>{detectionStore.error}</span>
				<button
					onclick={() => detectionStore.clearError()}
					class="inline-flex items-center rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
				>
					Sluiten
				</button>
			</div>
		{/if}
		{#if exportError}
			<!-- Inline export retry: the PDF bytes are still in memory, so the
			     retry button re-runs only the redact-stream request without
			     forcing a re-upload from IndexedDB. -->
			<div class="mx-4 mt-3 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
				<span>{exportError}</span>
				<button
					onclick={handleExport}
					disabled={exporting}
					class="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
				>
					<RotateCw size={14} />
					Opnieuw proberen
				</button>
			</div>
		{/if}
		{#if showPostExportLead}
			<!-- #45 — post-export lead capture. Appears once per successful
			     export and is dismissible so a repeat exporter isn't nagged. -->
			<div class="mx-4 mt-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
				<div class="flex items-start justify-between gap-3">
					<div>
						<p class="text-sm font-medium text-ink">
							Fijn dat je WOO Buddy hebt geprobeerd.
						</p>
						<p class="mt-1 text-sm text-ink-soft">
							Wil je gemaild worden zodra er teamfuncties zijn? Geen nieuwsbrief,
							geen spam.
						</p>
					</div>
					<button
						type="button"
						onclick={() => (showPostExportLead = false)}
						class="shrink-0 rounded-md p-1 text-ink-mute hover:bg-primary/10 hover:text-ink"
						aria-label="Sluiten"
					>
						<X size={16} />
					</button>
				</div>
				<div class="mt-3">
					<LeadCaptureForm source="post-export" compact />
				</div>
			</div>
		{/if}
		<!-- Five-year rule warning (Art. 5.3 Woo) -->
		{#if reviewStore.document?.five_year_warning}
			<div class="mx-4 mt-3">
				<Alert variant="warning">
					<strong>Let op — Vijfjaarstermijn (art. 5.3 Woo):</strong> Dit document is ouder dan 5 jaar.
					Relatieve weigeringsgronden gelden niet automatisch. Extra motivering is vereist bij toepassing van
					een relatieve grond.
				</Alert>
			</div>
		{/if}

		<!-- Main content: PDF + sidebar -->
		<div class="flex min-h-0 flex-1">
			<div bind:this={pdfScrollEl} class="flex-1 overflow-auto bg-gray-100 p-4">
				{#if needsPdf}
					<div class="flex h-full flex-col items-center justify-center gap-4 text-center">
						<p class="text-sm text-neutral">
							PDF niet gevonden in de browser. Selecteer het bestand om te beoordelen.
						</p>
						<sl-button variant="primary" onclick={openPdfFilePicker}>
							PDF selecteren
						</sl-button>
					</div>
				{:else if reviewStore.document}
					<PdfViewer
						bind:this={pdfViewerRef}
						bind:stageEl={pdfStageEl}
						{pdfData}
						detections={detectionStore.filtered}
						selectedDetectionId={detectionStore.selectedId}
						splitPendingId={splitPendingId}
						mergeStagingIds={detectionStore.multiSelectedIds}
						onSplitPointClick={handleSplitPointClick}
						currentPage={reviewStore.currentPage}
						scale={reviewStore.pdfScale}
						mode={reviewStore.mode}
						searchHighlights={searchHighlights}
						focusedSearchId={searchStore.focusedId}
						pageStatuses={pageReviewStore.statuses}
						onPageNaturalSize={(s) => reviewStore.setPageNaturalSize(s)}
						onMarkPageReviewed={handleMarkPageReviewed}
						onFlagPage={handleFlagPage}
						onSelectDetection={handleSelectDetection}
						onDeselect={() => detectionStore.select(null)}
						onPageChange={(p) => {
							// Changing pages invalidates any in-progress selection.
							manualSelectionStore.cancel();
							reviewStore.setPage(p);
						}}
						onModeChange={(m) => {
							// Hybrid model: both modes support text-drag /
							// Shift+drag manual redaction, so the mode switch
							// no longer has to discard an in-flight selection.
							reviewStore.setMode(m);
						}}
						onManualSelection={(s) => manualSelectionStore.setSelection(s)}
						onManualSelectionCleared={() => manualSelectionStore.clearIfInBar()}
						onBoundaryAdjust={handleBoundaryAdjust}
					/>
				{/if}
			</div>

			{#if reviewStore.sidebarOpen}
				<div class="flex w-96 shrink-0 flex-col overflow-hidden border-l border-gray-200 bg-gray-50/80">
					{#if searchStore.open}
						<SearchPanel
							onClose={() => searchStore.setOpen(false)}
							onJumpToOccurrence={handleJumpToOccurrence}
							onRedactOccurrences={handleRedactOccurrences}
						/>
					{/if}
					{#if reviewStore.mode === 'edit'}
						<div class="shrink-0 border-b border-gray-200 bg-white px-4 py-3">
							<div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
								Bewerken
							</div>
							<p class="mb-3 text-xs leading-relaxed text-neutral">
								Sleep over tekst om te lakken. Houd
								<kbd class="rounded border border-gray-300 bg-gray-50 px-1 font-mono text-[10px]">Alt</kbd>
								voor letterprecisie, of
								<kbd class="rounded border border-gray-300 bg-gray-50 px-1 font-mono text-[10px]">Shift</kbd>
								+ slepen om een gebied te lakken (voor handtekeningen, stempels en scans).
							</p>
							{#if detectionStore.selected}
								<div class="mb-1 text-[11px] font-medium text-gray-700">
									Geselecteerde detectie
								</div>
								<div class="rounded border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs text-neutral">
									Tier {detectionStore.selected.tier} · {detectionStore.selected.entity_type ?? '—'}
									{#if detectionStore.selected.woo_article}
										· Art. {detectionStore.selected.woo_article}
									{/if}
								</div>
								<!-- #18 — split action. Disabled for area detections (no text
								     layer to click into) and while a split is already pending. -->
								{#if detectionStore.selected.entity_type !== 'area'}
									<div class="mt-2">
										<sl-button
											size="small"
											variant="default"
											disabled={splitPendingId !== null}
											onclick={handleStartSplit}
										>
											Splitsen
										</sl-button>
									</div>
								{/if}
							{/if}
							{#if splitPendingId}
								<div class="mt-2 rounded border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs text-gray-700">
									Klik in de PDF op de plek waar de detectie gesplitst moet worden.
									<button
										type="button"
										class="ml-1 underline"
										onclick={handleCancelSplit}
									>
										Annuleren
									</button>
								</div>
							{/if}
							{#if detectionStore.multiSelectedIds.length >= 2}
								<!-- #18 — merge action. Only shows once the reviewer has
								     Ctrl+clicked at least two cards in the sidebar. -->
								<div class="mt-2 flex items-center gap-2">
									<sl-button
										size="small"
										variant="primary"
										onclick={handleMergeConfirm}
									>
										Samenvoegen ({detectionStore.multiSelectedIds.length})
									</sl-button>
									<button
										type="button"
										class="text-xs text-neutral underline"
										onclick={() => detectionStore.clearMultiSelect()}
									>
										Annuleren
									</button>
								</div>
							{/if}
						</div>
					{/if}
					<ReferenceNamesPanel
						onAdd={handleAddReferenceName}
						onRemove={handleRemoveReferenceName}
					/>
					<CustomTermsPanel
						onAdd={handleAddCustomTerm}
						onRemove={handleRemoveCustomTerm}
						matchCounts={customTermMatchCounts}
					/>
					<div data-sidebar-scroll class="flex-1 overflow-y-auto p-4">
						<DetectionList
							detections={detectionStore.filtered}
							selectedId={detectionStore.selectedId}
							multiSelectedIds={detectionStore.multiSelectedIds}
							structureSpans={structureSpansStore.spans}
							allDetections={detectionStore.all}
							onSelect={handleSelectDetection}
							onAccept={handleAccept}
							onReject={handleReject}
							onDefer={handleDefer}
							onReopen={handleReopen}
							onRedactWithArticle={handleRedactWithArticle}
							onChangeArticle={handleChangeArticle}
							onSetSubjectRole={handleSetSubjectRole}
							onSaveMotivation={handleSaveMotivation}
							onSweepBlock={handleSweepBlock}
							onSameNameSweep={handleSameNameSweep}
						/>
					</div>
				</div>
			{/if}
		</div>

		<!-- Bottom toolbar -->
		<div class="flex shrink-0 items-center justify-between border-t border-gray-200 bg-white px-4 py-1.5">
			<BatchActions
				tier1PendingCount={detectionStore.tier1PendingCount}
				tier2HighConfidenceCount={detectionStore.tier2HighConfidencePendingCount}
				onAcceptAllTier1={handleAcceptAllTier1}
				onAcceptHighConfidenceTier2={handleAcceptHighConfidenceTier2}
			/>
			<div class="flex items-center gap-1">
				{#if reviewStore.mode === 'edit'}
					<sl-tooltip content="Ongedaan maken (Ctrl+Z)">
						<sl-button
							size="small"
							variant="default"
							disabled={!undoStore.canUndo}
							onclick={handleUndo}
						>
							<Undo2 size={14} />
						</sl-button>
					</sl-tooltip>
					<sl-tooltip content="Opnieuw (Ctrl+Shift+Z)">
						<sl-button
							size="small"
							variant="default"
							disabled={!undoStore.canRedo}
							onclick={handleRedo}
						>
							<Redo2 size={14} />
						</sl-button>
					</sl-tooltip>
					<div class="mx-1 h-5 w-px bg-gray-200"></div>
				{/if}
				<sl-tooltip content="Uitzoomen">
					<sl-button size="small" variant="default" onclick={() => reviewStore.zoomOut()}>−</sl-button>
				</sl-tooltip>
				<button
					type="button"
					class="min-w-[3rem] rounded px-1 text-center text-xs text-neutral hover:bg-gray-100"
					title="Klik om naar 100% te gaan"
					onclick={() => reviewStore.setScale(1)}
				>
					{Math.round(reviewStore.pdfScale * 100)}%
				</button>
				<sl-tooltip content="Inzoomen">
					<sl-button size="small" variant="default" onclick={() => reviewStore.zoomIn()}>+</sl-button>
				</sl-tooltip>
				<div class="mx-1 h-5 w-px bg-gray-200"></div>
				<sl-tooltip content="Pas op breedte">
					<sl-button
						size="small"
						variant={reviewStore.pdfFitMode === 'width' ? 'primary' : 'default'}
						onclick={() => reviewStore.setFitMode('width')}
					>
						<StretchHorizontal size={14} />
					</sl-button>
				</sl-tooltip>
				<sl-tooltip content="Hele pagina">
					<sl-button
						size="small"
						variant={reviewStore.pdfFitMode === 'page' ? 'primary' : 'default'}
						onclick={() => reviewStore.setFitMode('page')}
					>
						<Maximize2 size={14} />
					</sl-button>
				</sl-tooltip>
			</div>
		</div>
	{/if}

	<!-- Manual text-selection redaction overlays. Rendered at the root so
	     they escape `overflow: hidden` on the PDF scroller. -->
	{#if manualSelectionStore.selection && manualSelectionStore.stage === 'bar'}
		<SelectionActionBar
			anchor={manualSelectionStore.selection.anchor}
			stageEl={pdfStageEl}
			scale={reviewStore.pdfScale}
			onConfirm={() => manualSelectionStore.confirmBar()}
			onCancel={() => manualSelectionStore.cancel()}
		/>
	{:else if manualSelectionStore.selection && manualSelectionStore.stage === 'form'}
		<ManualRedactionForm
			anchor={manualSelectionStore.selection.anchor}
			stageEl={pdfStageEl}
			scale={reviewStore.pdfScale}
			selectedText={manualSelectionStore.selection.text}
			initialEntityType={manualSelectionStore.selection.text === '' ? 'area' : undefined}
			onConfirm={handleFormConfirm}
			onCancel={() => manualSelectionStore.cancel()}
		/>
	{/if}
</div>

<style>
	/* Lucide SVGs render inline and sit on the text baseline, which pushes
	   them to the top of a Shoelace button's flex slot. Making them
	   block-level lets Shoelace's internal flexbox center them vertically. */
	:global(sl-button svg) {
		display: block;
	}
</style>
