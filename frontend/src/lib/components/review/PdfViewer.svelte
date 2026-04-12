<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import type { Detection, BoundingBox } from '$lib/types';

	interface Props {
		pdfData: ArrayBuffer | null;
		detections: Detection[];
		selectedDetectionId: string | null;
		currentPage: number;
		scale: number;
		onSelectDetection: (id: string) => void;
		onPageChange: (page: number) => void;
		onTotalPages: (total: number) => void;
	}

	let {
		pdfData,
		detections,
		selectedDetectionId,
		currentPage,
		scale,
		onSelectDetection,
		onPageChange,
		onTotalPages
	}: Props = $props();

	let canvasEl = $state<HTMLCanvasElement | null>(null);
	let overlayEl = $state<HTMLDivElement | null>(null);
	let pdfDoc = $state<any>(null);
	let rendering = false; // not reactive — just a guard flag
	let viewportSize = { width: 0, height: 0 };

	// Tier-based overlay styles
	function getOverlayStyle(det: Detection): string {
		const isSelected = det.id === selectedDetectionId;
		const border = isSelected ? 'border: 2px solid var(--color-primary);' : '';

		if (det.tier === '1' || det.review_status === 'accepted' || det.review_status === 'auto_accepted') {
			return `background: rgba(0,0,0,0.7); color: white; ${border}`;
		}
		if (det.review_status === 'rejected') {
			return `background: rgba(39,174,96,0.08); border: 1px dashed rgba(39,174,96,0.4); ${border}`;
		}
		if (det.tier === '2') {
			return `background: rgba(243,156,18,0.1); border: 2px solid rgba(243,156,18,0.6); ${border}`;
		}
		return `background: rgba(27,79,114,0.05); border-left: 3px solid var(--color-primary); ${border}`;
	}

	onMount(async () => {
		const pdfjsLib = await import('pdfjs-dist');
		pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
			'pdfjs-dist/build/pdf.worker.mjs',
			import.meta.url
		).toString();

		// Client-first: PDF comes from the in-memory ArrayBuffer only.
		// .slice(0) copies the buffer so pdf.js Worker transfer doesn't detach the original.
		if (!pdfData) return;
		const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(pdfData.slice(0)) });
		pdfDoc = await loadingTask.promise;
		onTotalPages(pdfDoc.numPages);
	});

	async function renderPdf(pageNum: number) {
		if (!pdfDoc || !canvasEl || rendering) return;
		rendering = true;

		try {
			const page = await pdfDoc.getPage(pageNum + 1);
			const viewport = page.getViewport({ scale });
			viewportSize = { width: viewport.width, height: viewport.height };

			canvasEl.width = viewport.width;
			canvasEl.height = viewport.height;

			const ctx = canvasEl.getContext('2d')!;
			await page.render({ canvasContext: ctx, viewport }).promise;
		} finally {
			rendering = false;
		}
	}

	function drawOverlays(pageNum: number) {
		if (!overlayEl) return;

		overlayEl.innerHTML = '';
		overlayEl.style.width = `${viewportSize.width}px`;
		overlayEl.style.height = `${viewportSize.height}px`;

		for (const det of detections) {
			if (!det.bounding_boxes) continue;
			for (const bbox of det.bounding_boxes) {
				if (bbox.page !== pageNum) continue;

				const el = document.createElement('div');
				const x = bbox.x0 * scale;
				const y = bbox.y0 * scale;
				const w = (bbox.x1 - bbox.x0) * scale;
				const h = (bbox.y1 - bbox.y0) * scale;

				el.style.cssText = `
					position: absolute;
					left: ${x}px; top: ${y}px;
					width: ${w}px; height: ${h}px;
					cursor: pointer; pointer-events: auto;
					border-radius: 2px;
					${getOverlayStyle(det)}
				`;

				if (det.tier === '1' && det.woo_article) {
					el.innerHTML = `<span style="font-size:8px;padding:1px 3px;">${det.woo_article}</span>`;
				}

				el.addEventListener('click', () => onSelectDetection(det.id));
				overlayEl.appendChild(el);
			}
		}
	}

	// Render PDF when page or doc changes — untrack to avoid tracking internal state
	$effect(() => {
		const doc = pdfDoc;
		const page = currentPage;
		if (doc) {
			untrack(() => renderPdf(page));
		}
	});

	// Draw overlays when detections, selection, or page changes
	$effect(() => {
		const _deps = [detections, selectedDetectionId, currentPage];
		if (pdfDoc) {
			untrack(() => drawOverlays(currentPage));
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

	<!-- PDF canvas + overlay -->
	<div class="relative flex justify-center p-4">
		{#if !pdfDoc}
			<div class="flex h-96 items-center justify-center text-neutral">
				PDF laden...
			</div>
		{:else}
			<div class="relative">
				<canvas bind:this={canvasEl}></canvas>
				<div bind:this={overlayEl} class="absolute top-0 left-0 pointer-events-none"></div>
			</div>
		{/if}
	</div>
</div>
