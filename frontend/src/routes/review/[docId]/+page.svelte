<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
	import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';

	import { page } from '$app/state';
	import { detectionStore } from '$lib/stores/detections.svelte';
	import { reviewStore } from '$lib/stores/review.svelte';
	import { manualSelectionStore } from '$lib/stores/manual-selection.svelte';
	import { searchStore } from '$lib/stores/search.svelte';
	import {
		undoStore,
		CreateManualCommand,
		ReviewStatusCommand,
		BatchCommand,
		type Command
	} from '$lib/stores/undo.svelte';
	import PdfViewer from '$lib/components/review/PdfViewer.svelte';
	import SelectionActionBar from '$lib/components/review/SelectionActionBar.svelte';
	import ManualRedactionForm from '$lib/components/review/ManualRedactionForm.svelte';
	import SearchPanel from '$lib/components/review/SearchPanel.svelte';
	import type { SearchOccurrence } from '$lib/services/search-redact';
	import DetectionList from '$lib/components/review/DetectionList.svelte';
	import DetectionFilters from '$lib/components/review/DetectionFilters.svelte';
	import ProgressBar from '$lib/components/review/ProgressBar.svelte';
	import BatchActions from '$lib/components/review/BatchActions.svelte';
	import KeyboardShortcuts from '$lib/components/review/KeyboardShortcuts.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { getPdf, storePdf } from '$lib/services/pdf-store';
	import { extractText, loadPdfDocument } from '$lib/services/pdf-text-extractor';
	import { exportRedactedPdf, downloadBlob } from '$lib/services/export-service';
	import type { WooArticleCode, EntityType, DetectionTier } from '$lib/types';
	import { ArrowLeft, PanelRightClose, PanelRightOpen, Download, RotateCw, Undo2, Redo2, Search } from 'lucide-svelte';

	const docId = $derived(page.params.docId!);

	let pdfData = $state<ArrayBuffer | null>(null);
	let needsPdf = $state(false);
	let exporting = $state(false);
	let exportError = $state<string | null>(null);
	// Exposed by PdfViewer via `bind:stageEl` — the manual selection bar/form
	// use this element's bounding rect to project page-space anchors to
	// viewport pixels, so they follow the PDF through scroll and zoom.
	let pdfStageEl = $state<HTMLDivElement | null>(null);
	// PdfViewer exposes `flashDetections` via `bind:this` for the undo effect
	// below — the viewer flashes affected overlays after each undo/redo push.
	let pdfViewerRef = $state<{ flashDetections: (ids: string[]) => void } | null>(null);

	// Load document + detections + local PDF. The undo stack is per-document
	// and in-memory only — switching docs or reloading should not leave stale
	// commands that target rows from a different document.
	$effect(() => {
		void docId;
		undoStore.clear();
		reviewStore.loadDocument(docId);
		loadPdfAndDetections(docId);
		return () => undoStore.clear();
	});

	// Flash affected overlays after any undo/redo/push that touches detections.
	$effect(() => {
		const ids = undoStore.lastAffected;
		if (ids.length === 0) return;
		pdfViewerRef?.flashDetections(ids);
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

	// Navigate PDF to the page containing a detection
	function handleSelectDetection(id: string) {
		detectionStore.select(id);
		const det = detectionStore.all.find((d) => d.id === id);
		if (det?.bounding_boxes?.length) {
			const targetPage = det.bounding_boxes[0].page;
			if (targetPage !== reviewStore.currentPage) {
				reviewStore.setPage(targetPage);
			}
		}
	}

	/**
	 * Build a ReviewStatusCommand for a detection, capturing its current
	 * review_status and woo_article at command-construction time so that
	 * undoing the action restores the exact prior state.
	 */
	function makeStatusCommand(
		id: string,
		nextStatus: 'accepted' | 'rejected' | 'deferred',
		nextArticle?: WooArticleCode
	): ReviewStatusCommand | null {
		const det = detectionStore.all.find((d) => d.id === id);
		if (!det) return null;
		return new ReviewStatusCommand(
			id,
			det.review_status,
			nextStatus,
			det.woo_article ?? undefined,
			nextArticle ?? det.woo_article ?? undefined
		);
	}

	function handleAccept(id: string) {
		const cmd = makeStatusCommand(id, 'accepted');
		if (cmd) undoStore.push(cmd);
	}

	function handleRedactWithArticle(id: string, article: WooArticleCode) {
		const cmd = makeStatusCommand(id, 'accepted', article);
		if (cmd) undoStore.push(cmd);
	}

	function handleReject(id: string) {
		const cmd = makeStatusCommand(id, 'rejected');
		if (cmd) undoStore.push(cmd);
	}

	function handleDefer(id: string) {
		const cmd = makeStatusCommand(id, 'deferred');
		if (cmd) undoStore.push(cmd);
	}

	function handleKeyAccept() {
		if (detectionStore.selectedId) handleAccept(detectionStore.selectedId);
	}
	function handleKeyReject() {
		if (detectionStore.selectedId) handleReject(detectionStore.selectedId);
	}
	function handleKeyDefer() {
		if (detectionStore.selectedId) handleDefer(detectionStore.selectedId);
	}

	function handleSaveMotivation(id: string, text: string) {
		// Motivation edits are not currently part of the undo stack — they
		// happen inside a form with its own cancel path, and the new command
		// type for motivation-only changes isn't worth the surface area yet.
		detectionStore.review(id, { review_status: 'edited', motivation_text: text });
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
		const HIGH = 0.85;
		const children = buildAcceptBatch(
			detectionStore.all.filter(
				(d) => d.tier === '2' && d.review_status === 'pending' && d.confidence >= HIGH
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

	// Ctrl/Cmd+F opens the search panel. We preventDefault so the browser's
	// native find bar stays closed — our search runs against the extracted
	// PDF text, which the browser find can't reach through pdf.js's text
	// layer anyway.
	function handleGlobalKeydown(e: KeyboardEvent) {
		if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'f' && !e.altKey) {
			e.preventDefault();
			searchStore.setOpen(true);
			// Make sure the sidebar is visible so the panel actually appears.
			if (!reviewStore.sidebarOpen) reviewStore.toggleSidebar();
		}
	}
	$effect(() => {
		window.addEventListener('keydown', handleGlobalKeydown);
		return () => window.removeEventListener('keydown', handleGlobalKeydown);
	});

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
			<ProgressBar tiers={progressTiers} />
		</div>
		<div class="h-5 w-px bg-gray-200"></div>
		<sl-tooltip content="Zoek & Lak (Ctrl+F)">
			<sl-button
				size="small"
				variant={searchStore.open ? 'primary' : 'default'}
				onclick={() => {
					searchStore.toggle();
					if (searchStore.open && !reviewStore.sidebarOpen) reviewStore.toggleSidebar();
				}}
			>
				<Search size={14} />
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
		<div class="flex flex-1 items-center justify-center">
			<sl-spinner style="font-size: 2rem; --indicator-color: var(--color-primary);"></sl-spinner>
		</div>
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
			<div class="flex-1 overflow-auto bg-gray-100 p-4">
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
						currentPage={reviewStore.currentPage}
						scale={reviewStore.pdfScale}
						mode={reviewStore.mode}
						searchHighlights={searchHighlights}
						focusedSearchId={searchStore.focusedId}
						onSelectDetection={handleSelectDetection}
						onDeselect={() => detectionStore.select(null)}
						onPageChange={(p) => {
							// Changing pages invalidates any in-progress selection.
							manualSelectionStore.cancel();
							reviewStore.setPage(p);
						}}
						onModeChange={(m) => {
							if (m === 'review') manualSelectionStore.cancel();
							reviewStore.setMode(m);
						}}
						onManualSelection={(s) => manualSelectionStore.setSelection(s)}
						onManualSelectionCleared={() => manualSelectionStore.clearIfInBar()}
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
							{/if}
						</div>
					{/if}
					<div class="flex-1 overflow-y-auto p-4">
						<DetectionList
							detections={detectionStore.filtered}
							selectedId={detectionStore.selectedId}
							onSelect={handleSelectDetection}
							onAccept={handleAccept}
							onReject={handleReject}
							onDefer={handleDefer}
							onRedactWithArticle={handleRedactWithArticle}
							onSaveMotivation={handleSaveMotivation}
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
				<span class="min-w-[3rem] text-center text-xs text-neutral">{Math.round(reviewStore.pdfScale * 100)}%</span>
				<sl-tooltip content="Inzoomen">
					<sl-button size="small" variant="default" onclick={() => reviewStore.zoomIn()}>+</sl-button>
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
