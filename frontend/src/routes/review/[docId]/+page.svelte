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
		BoundaryAdjustCommand,
	} from '$lib/stores/undo.svelte';
	import { structureSpansStore } from '$lib/stores/structure-spans.svelte';
	import { splitMergeStore } from '$lib/stores/split-merge.svelte';
	import { spanKey } from '$lib/utils/structure-matching';
	import { sweepBlock, sameNameSweep, findEnclosingSpan } from '$lib/services/bulk-sweep';
	import {
		touchDetectionPages,
		handleAccept,
		handleRedactWithArticle,
		handleReject,
		handleDefer,
		handleReopen,
		handleChangeArticle,
		handleSetSubjectRole,
		handleSaveMotivation,
		handleAcceptAllTier1,
		handleAcceptHighConfidenceTier2,
	} from '$lib/services/review-actions';
	import {
		handleAddReferenceName as addReferenceName,
		handleRemoveReferenceName as removeReferenceName,
		handleAddCustomTerm as addCustomTerm,
		handleRemoveCustomTerm as removeCustomTerm,
	} from '$lib/services/list-panel-actions';
	import PdfViewer from '$lib/components/review/PdfViewer.svelte';
	import SelectionActionBar from '$lib/components/review/SelectionActionBar.svelte';
	import ManualRedactionForm from '$lib/components/review/ManualRedactionForm.svelte';
	import SearchPanel from '$lib/components/review/SearchPanel.svelte';
	import type { SearchOccurrence } from '$lib/services/search-redact';
	import { redactSearchOccurrences } from '$lib/services/search-redact-commit';
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
	import type { WooArticleCode, EntityType, DetectionTier } from '$lib/types';
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
	// Art. 5.3 contextual hint — shown when the extracted document date
	// suggests the document may be older than 5 years. Worded as a reminder
	// rather than a declarative claim (our date heuristic can still be fooled
	// by free-form text), and dismissible per reviewer session.
	let fiveYearHintDismissed = $state(false);
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
			splitMergeStore.cancelSplit();
			return;
		}
		splitMergeStore.cancelSplit();
		detectionStore.select(id);
		const det = detectionStore.byId[id];
		if (det?.bounding_boxes?.length) {
			const targetPage = det.bounding_boxes[0].page;
			if (targetPage !== reviewStore.currentPage) {
				reviewStore.setPage(targetPage);
			}
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

	// Bulk sweeps (#20) — real logic lives in $lib/services/bulk-sweep. These
	// wrappers exist only so the page can thread `touchDetectionPages` into
	// each sweep and pass a stable prop into the sidebar.
	const handleSweepBlock = (key: string) => sweepBlock(key, touchDetectionPages);
	const handleSameNameSweep = (detectionId: string) =>
		sameNameSweep(detectionId, touchDetectionPages);

	// Shift+H / Shift+S keyboard handlers — resolve the span enclosing the
	// current selection and delegate to the sweep helper. No-op on missing
	// selection or no matching span; silent failure is the right UX here,
	// the reviewer will just see nothing happen and try a different detection.
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

	// -----------------------------------------------------------------------
	// Search-and-redact (#09)
	// -----------------------------------------------------------------------

	function handleJumpToOccurrence(occ: SearchOccurrence) {
		if (occ.page !== reviewStore.currentPage) {
			reviewStore.setPage(occ.page);
		}
	}

	function handleRedactOccurrences(payload: Parameters<typeof redactSearchOccurrences>[1]) {
		return redactSearchOccurrences(docId, payload);
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
		<!-- Art. 5.3 Woo — contextual reminder, not a declarative claim. The
		     date heuristic can be fooled by cited dates or form fields, so we
		     pitch this as a general hint and let the reviewer dismiss it. -->
		{#if reviewStore.document?.five_year_warning && !fiveYearHintDismissed}
			<div class="mx-4 mt-3">
				<Alert
					variant="primary"
					closable
					onsl-after-hide={() => {
						fiveYearHintDismissed = true;
					}}
				>
					<strong>Ter herinnering — art. 5.3 Woo:</strong> relatieve weigeringsgronden gelden
					niet automatisch voor documenten ouder dan vijf jaar. Als dit document ouder is,
					is extra motivering nodig bij toepassing van een relatieve grond.
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
						splitPendingId={splitMergeStore.pendingId}
						mergeStagingIds={detectionStore.multiSelectedIds}
						onSplitPointClick={splitMergeStore.commitSplit}
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
											disabled={splitMergeStore.pendingId !== null}
											onclick={() => splitMergeStore.startSplit()}
										>
											Splitsen
										</sl-button>
									</div>
								{/if}
							{/if}
							{#if splitMergeStore.pendingId}
								<div class="mt-2 rounded border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs text-gray-700">
									Klik in de PDF op de plek waar de detectie gesplitst moet worden.
									<button
										type="button"
										class="ml-1 underline"
										onclick={() => splitMergeStore.cancelSplit()}
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
										onclick={() => splitMergeStore.confirmMerge()}
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
						onAdd={(name) => addReferenceName(name, docId)}
						onRemove={(id, name) => removeReferenceName(id, name, docId)}
					/>
					<CustomTermsPanel
						onAdd={(term, article) => addCustomTerm(term, article, docId)}
						onRemove={(id, term) => removeCustomTerm(id, term, docId)}
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
