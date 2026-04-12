<script lang="ts">
	import { onMount } from 'svelte';
	import { getDocumentPdfUrl } from '$lib/api/client';
	import type { Detection, BoundingBox } from '$lib/types';

	interface Props {
		documentId: string;
		detections: Detection[];
		selectedDetectionId: string | null;
		currentPage: number;
		scale: number;
		onSelectDetection: (id: string) => void;
		onPageChange: (page: number) => void;
		onTotalPages: (total: number) => void;
	}

	let {
		documentId,
		detections,
		selectedDetectionId,
		currentPage,
		scale,
		onSelectDetection,
		onPageChange,
		onTotalPages
	}: Props = $props();

	let canvasContainer = $state<HTMLDivElement | null>(null);
	let pdfDoc = $state<any>(null);
	let rendering = $state(false);

	const pdfUrl = $derived(getDocumentPdfUrl(documentId));

	// Tier-based overlay styles
	function getOverlayStyle(det: Detection, bbox: BoundingBox): string {
		const isSelected = det.id === selectedDetectionId;
		const border = isSelected ? 'border: 2px solid var(--color-primary);' : '';

		if (det.tier === 1 || det.review_status === 'accepted' || det.review_status === 'auto_accepted') {
			return `background: rgba(0,0,0,0.85); color: white; ${border}`;
		}
		if (det.review_status === 'rejected') {
			return `background: rgba(39,174,96,0.15); border: 1px solid rgba(39,174,96,0.4); ${border}`;
		}
		if (det.tier === 2) {
			return `background: rgba(243,156,18,0.25); border: 1px solid rgba(243,156,18,0.5); ${border}`;
		}
		// Tier 3 — subtle marker
		return `background: rgba(27,79,114,0.1); border-left: 3px solid var(--color-primary); ${border}`;
	}

	onMount(async () => {
		const pdfjsLib = await import('pdfjs-dist');
		pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
			'pdfjs-dist/build/pdf.worker.mjs',
			import.meta.url
		).toString();

		const loadingTask = pdfjsLib.getDocument(pdfUrl);
		pdfDoc = await loadingTask.promise;
		onTotalPages(pdfDoc.numPages);
		renderPage(currentPage);
	});

	async function renderPage(pageNum: number) {
		if (!pdfDoc || rendering) return;
		rendering = true;

		const page = await pdfDoc.getPage(pageNum + 1); // pdf.js is 1-indexed
		const viewport = page.getViewport({ scale });

		if (!canvasContainer) {
			rendering = false;
			return;
		}

		// Clear previous render
		canvasContainer.innerHTML = '';

		const canvas = document.createElement('canvas');
		canvas.width = viewport.width;
		canvas.height = viewport.height;
		canvasContainer.appendChild(canvas);

		const ctx = canvas.getContext('2d')!;
		await page.render({ canvasContext: ctx, viewport }).promise;

		// Add detection overlays
		const overlayContainer = document.createElement('div');
		overlayContainer.style.cssText = `
			position: absolute; top: 0; left: 0;
			width: ${viewport.width}px; height: ${viewport.height}px;
			pointer-events: none;
		`;

		for (const det of detections) {
			if (!det.bounding_boxes) continue;
			for (const bbox of det.bounding_boxes) {
				if (bbox.page !== pageNum) continue;

				const overlay = document.createElement('div');
				const x = bbox.x0 * scale;
				const y = bbox.y0 * scale;
				const w = (bbox.x1 - bbox.x0) * scale;
				const h = (bbox.y1 - bbox.y0) * scale;

				overlay.style.cssText = `
					position: absolute;
					left: ${x}px; top: ${y}px;
					width: ${w}px; height: ${h}px;
					cursor: pointer; pointer-events: auto;
					border-radius: 2px;
					transition: opacity 0.15s;
					${getOverlayStyle(det, bbox)}
				`;

				// Show article code on Tier 1
				if (det.tier === 1 && det.woo_article) {
					overlay.innerHTML = `<span style="font-size:8px;padding:1px 3px;">${det.woo_article}</span>`;
				}

				overlay.addEventListener('click', () => onSelectDetection(det.id));
				overlayContainer.appendChild(overlay);
			}
		}

		canvasContainer.appendChild(overlayContainer);
		rendering = false;
	}

	// Re-render when page or detections change
	$effect(() => {
		if (pdfDoc) {
			renderPage(currentPage);
		}
	});
</script>

<div class="relative overflow-auto rounded-lg border border-gray-200 bg-white">
	<!-- Page navigation -->
	<div class="sticky top-0 z-10 flex items-center justify-between border-b bg-white/95 px-4 py-2 backdrop-blur-sm">
		<button
			class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
			disabled={currentPage <= 0}
			onclick={() => onPageChange(currentPage - 1)}
		>
			&larr; Vorige
		</button>
		<span class="text-sm text-neutral">{currentPage + 1} / {pdfDoc?.numPages ?? '...'}</span>
		<button
			class="rounded px-2 py-1 text-sm hover:bg-gray-100 disabled:opacity-40"
			disabled={!pdfDoc || currentPage >= pdfDoc.numPages - 1}
			onclick={() => onPageChange(currentPage + 1)}
		>
			Volgende &rarr;
		</button>
	</div>

	<!-- PDF canvas -->
	<div bind:this={canvasContainer} class="relative flex justify-center p-4">
		{#if !pdfDoc}
			<div class="flex h-96 items-center justify-center text-neutral">
				PDF laden...
			</div>
		{/if}
	</div>
</div>
