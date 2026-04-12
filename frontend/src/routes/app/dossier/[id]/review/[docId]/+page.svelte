<script lang="ts">
	export const ssr = false;

	import { page } from '$app/state';
	import { detectionStore } from '$lib/stores/detections';
	import { reviewStore } from '$lib/stores/review';
	import PdfViewer from '$lib/components/review/PdfViewer.svelte';
	import DetectionList from '$lib/components/review/DetectionList.svelte';
	import DetectionFilters from '$lib/components/review/DetectionFilters.svelte';
	import ProgressBar from '$lib/components/review/ProgressBar.svelte';
	import BatchActions from '$lib/components/review/BatchActions.svelte';
	import KeyboardShortcuts from '$lib/components/review/KeyboardShortcuts.svelte';
	import NamePropagation from '$lib/components/review/NamePropagation.svelte';
	import type { WooArticleCode } from '$lib/types';

	const dossierId = $derived(page.params.id!);
	const docId = $derived(page.params.docId!);

	// Load document + detections
	$effect(() => {
		reviewStore.loadDocument(docId);
		detectionStore.load(docId);
	});

	// Progress data
	const progressTiers = $derived([
		{ tier: 1 as const, reviewed: detectionStore.counts.reviewedByTier[1], total: detectionStore.counts.byTier[1] },
		{ tier: 2 as const, reviewed: detectionStore.counts.reviewedByTier[2], total: detectionStore.counts.byTier[2] },
		{ tier: 3 as const, reviewed: detectionStore.counts.reviewedByTier[3], total: detectionStore.counts.byTier[3] }
	]);

	// Batch action counts
	const tier1Pending = $derived(
		detectionStore.all.filter((d) => d.tier === 1 && d.review_status === 'pending').length
	);
	const tier2HighConfidence = $derived(
		detectionStore.all.filter(
			(d) => d.tier === 2 && d.review_status === 'pending' && d.confidence >= 0.85
		).length
	);

	// Propagated detections
	const propagated = $derived(detectionStore.all.filter((d) => d.propagated_from));

	// Handlers
	function handleAccept(id: string) {
		const det = detectionStore.all.find((d) => d.id === id);
		detectionStore.accept(id, det?.woo_article ?? undefined);
	}

	function handleRedactWithArticle(id: string, article: WooArticleCode) {
		detectionStore.accept(id, article);
	}

	function handleAcceptAllTier1() {
		const pending = detectionStore.all.filter(
			(d) => d.tier === 1 && d.review_status === 'pending'
		);
		for (const d of pending) {
			detectionStore.accept(d.id, d.woo_article ?? undefined);
		}
	}

	function handleAcceptHighConfidenceTier2() {
		const pending = detectionStore.all.filter(
			(d) => d.tier === 2 && d.review_status === 'pending' && d.confidence >= 0.85
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
</script>

<svelte:head>
	<title>Review — WOO Buddy</title>
</svelte:head>

<KeyboardShortcuts
	onAccept={handleKeyAccept}
	onReject={handleKeyReject}
	onDefer={handleKeyDefer}
	onNext={() => detectionStore.selectNext()}
	onPrev={() => detectionStore.selectPrevious()}
	onToggleHelp={() => {}}
/>

<div class="flex h-full flex-col">
	<!-- Top bar: filters + progress -->
	<div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 bg-white px-4 py-3">
		<DetectionFilters
			currentTier={detectionStore.filters.tier}
			currentStatus={detectionStore.filters.status}
			currentEntityType={detectionStore.filters.entityType}
			onFilterChange={(key, val) => detectionStore.setFilter(key, val)}
			onClear={() => detectionStore.clearFilters()}
		/>
		<ProgressBar tiers={progressTiers} />
	</div>

	{#if detectionStore.loading || reviewStore.loading}
		<div class="flex flex-1 items-center justify-center">
			<div class="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
		</div>
	{:else if detectionStore.error || reviewStore.error}
		<div class="m-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
			{detectionStore.error || reviewStore.error}
		</div>
	{:else}
		<!-- Main content: PDF + sidebar -->
		<div class="flex flex-1 overflow-hidden">
			<!-- Left: PDF viewer -->
			<div class="flex-1 overflow-auto p-4">
				{#if reviewStore.document}
					<PdfViewer
						documentId={docId}
						detections={detectionStore.filtered}
						selectedDetectionId={detectionStore.selectedId}
						currentPage={reviewStore.currentPage}
						scale={reviewStore.pdfScale}
						onSelectDetection={(id) => detectionStore.select(id)}
						onPageChange={(p) => reviewStore.setPage(p)}
						onTotalPages={() => {}}
					/>
				{/if}
			</div>

			<!-- Right: Detection sidebar -->
			{#if reviewStore.sidebarOpen}
				<div class="w-96 shrink-0 overflow-y-auto border-l border-gray-200 bg-gray-50 p-4">
					<!-- Name propagation banner -->
					{#if propagated.length > 0}
						<div class="mb-4">
							<NamePropagation
								propagatedDetections={propagated}
								onUndoPropagate={(sourceId) => {
									/* TODO: wire undo propagation */
								}}
							/>
						</div>
					{/if}

					<!-- Detection list -->
					<DetectionList
						detections={detectionStore.filtered}
						selectedId={detectionStore.selectedId}
						onSelect={(id) => detectionStore.select(id)}
						onAccept={handleAccept}
						onReject={(id) => detectionStore.reject(id)}
						onDefer={(id) => detectionStore.defer(id)}
						onPropagate={(id) => detectionStore.propagate(id)}
						onRedactWithArticle={handleRedactWithArticle}
					/>
				</div>
			{/if}
		</div>

		<!-- Bottom toolbar -->
		<div class="flex items-center justify-between border-t border-gray-200 bg-white px-4 py-2">
			<BatchActions
				tier1PendingCount={tier1Pending}
				tier2HighConfidenceCount={tier2HighConfidence}
				onAcceptAllTier1={handleAcceptAllTier1}
				onAcceptHighConfidenceTier2={handleAcceptHighConfidenceTier2}
			/>
			<div class="flex gap-2">
				<button
					class="rounded border border-gray-300 px-3 py-1 text-xs text-neutral hover:bg-gray-100"
					onclick={() => reviewStore.zoomOut()}
				>
					-
				</button>
				<span class="text-xs text-neutral leading-7">{Math.round(reviewStore.pdfScale * 100)}%</span>
				<button
					class="rounded border border-gray-300 px-3 py-1 text-xs text-neutral hover:bg-gray-100"
					onclick={() => reviewStore.zoomIn()}
				>
					+
				</button>
				<button
					class="rounded border border-gray-300 px-3 py-1 text-xs text-neutral hover:bg-gray-100"
					onclick={() => reviewStore.toggleSidebar()}
				>
					{reviewStore.sidebarOpen ? 'Verberg' : 'Toon'} sidebar
				</button>
			</div>
		</div>
	{/if}
</div>
