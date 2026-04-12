<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
	import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';

	import { page } from '$app/state';
	import { detectionStore } from '$lib/stores/detections.svelte';
	import { reviewStore } from '$lib/stores/review.svelte';
	import PdfViewer from '$lib/components/review/PdfViewer.svelte';
	import DetectionList from '$lib/components/review/DetectionList.svelte';
	import DetectionFilters from '$lib/components/review/DetectionFilters.svelte';
	import ProgressBar from '$lib/components/review/ProgressBar.svelte';
	import BatchActions from '$lib/components/review/BatchActions.svelte';
	import KeyboardShortcuts from '$lib/components/review/KeyboardShortcuts.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { getPdf, storePdf } from '$lib/services/pdf-store';
	import { extractText, loadPdfDocument } from '$lib/services/pdf-text-extractor';
	import { exportRedactedPdf, downloadBlob } from '$lib/services/export-service';
	import type { WooArticleCode } from '$lib/types';
	import { ArrowLeft, PanelRightClose, PanelRightOpen, Download, RotateCw } from 'lucide-svelte';

	const docId = $derived(page.params.docId!);

	let pdfData = $state<ArrayBuffer | null>(null);
	let needsPdf = $state(false);
	let exporting = $state(false);
	let exportError = $state<string | null>(null);

	// Load document + detections + local PDF
	$effect(() => {
		reviewStore.loadDocument(docId);
		loadPdfAndDetections(docId);
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

	// Batch action counts
	const tier1Pending = $derived(
		detectionStore.all.filter((d) => d.tier === '1' && d.review_status === 'pending').length
	);
	const tier2HighConfidence = $derived(
		detectionStore.all.filter(
			(d) => d.tier === '2' && d.review_status === 'pending' && d.confidence >= 0.85
		).length
	);

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

	function handleAccept(id: string) {
		const det = detectionStore.all.find((d) => d.id === id);
		detectionStore.accept(id, det?.woo_article ?? undefined);
	}

	function handleRedactWithArticle(id: string, article: WooArticleCode) {
		detectionStore.accept(id, article);
	}

	function handleAcceptAllTier1() {
		const pending = detectionStore.all.filter(
			(d) => d.tier === '1' && d.review_status === 'pending'
		);
		for (const d of pending) {
			detectionStore.accept(d.id, d.woo_article ?? undefined);
		}
	}

	function handleAcceptHighConfidenceTier2() {
		const pending = detectionStore.all.filter(
			(d) => d.tier === '2' && d.review_status === 'pending' && d.confidence >= 0.85
		);
		for (const d of pending) {
			detectionStore.accept(d.id, d.woo_article ?? undefined);
		}
	}

	function handleKeyAccept() {
		if (detectionStore.selectedId) handleAccept(detectionStore.selectedId);
	}
	function handleKeyReject() {
		if (detectionStore.selectedId) detectionStore.reject(detectionStore.selectedId);
	}
	function handleKeyDefer() {
		if (detectionStore.selectedId) detectionStore.defer(detectionStore.selectedId);
	}

	function handleSaveMotivation(id: string, text: string) {
		detectionStore.review(id, { review_status: 'edited', motivation_text: text });
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
	onToggleHelp={() => {}}
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
	{:else if detectionStore.error || reviewStore.error}
		<div class="m-4">
			<Alert variant="danger">{detectionStore.error || reviewStore.error}</Alert>
		</div>
	{:else}
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
						<sl-button variant="primary" onclick={() => { const input = document.createElement('input'); input.type = 'file'; input.accept = '.pdf'; input.onchange = handleFileSelect; input.click(); }}>
							PDF selecteren
						</sl-button>
					</div>
				{:else if reviewStore.document}
					<PdfViewer
						{pdfData}
						detections={detectionStore.filtered}
						selectedDetectionId={detectionStore.selectedId}
						currentPage={reviewStore.currentPage}
						scale={reviewStore.pdfScale}
						onSelectDetection={handleSelectDetection}
						onPageChange={(p) => reviewStore.setPage(p)}
						onTotalPages={() => {}}
					/>
				{/if}
			</div>

			{#if reviewStore.sidebarOpen}
				<div class="w-96 shrink-0 overflow-y-auto border-l border-gray-200 bg-gray-50/80 p-4">
					<DetectionList
						detections={detectionStore.filtered}
						selectedId={detectionStore.selectedId}
						onSelect={handleSelectDetection}
						onAccept={handleAccept}
						onReject={(id) => detectionStore.reject(id)}
						onDefer={(id) => detectionStore.defer(id)}
						onRedactWithArticle={handleRedactWithArticle}
						onSaveMotivation={handleSaveMotivation}
					/>
				</div>
			{/if}
		</div>

		<!-- Bottom toolbar -->
		<div class="flex shrink-0 items-center justify-between border-t border-gray-200 bg-white px-4 py-1.5">
			<BatchActions
				tier1PendingCount={tier1Pending}
				tier2HighConfidenceCount={tier2HighConfidence}
				onAcceptAllTier1={handleAcceptAllTier1}
				onAcceptHighConfidenceTier2={handleAcceptHighConfidenceTier2}
			/>
			<div class="flex items-center gap-1">
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
</div>
