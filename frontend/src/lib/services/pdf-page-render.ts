/**
 * pdf.js page rendering helpers extracted from PdfViewer.svelte.
 *
 * Two responsibilities:
 *  1. Render a single page into a `<canvas>` at the requested scale.
 *  2. Render the page's selectable text layer into a `<div>`, returning a
 *     handle that can be cancelled if the reviewer pages forward before the
 *     previous render finishes.
 *
 * Kept Svelte-free so the viewer's `$effect`s stay tiny and so this can
 * eventually be unit tested with a fake pdf.js page.
 */

export interface RenderedPage {
	/** Viewport size in CSS pixels at the requested scale. */
	width: number;
	height: number;
	/** Unscaled (PDF-point) page size — useful for fit-to-width calculations. */
	naturalWidth: number;
	naturalHeight: number;
	/**
	 * Active text-layer render. Call `.cancel()` before kicking off another
	 * page render to abort the in-flight one cleanly. `null` when there is
	 * no text layer container.
	 */
	textLayer: { cancel: () => void } | null;
}

interface RenderOptions {
	pdfDoc: any;
	pageNum: number;
	scale: number;
	canvas: HTMLCanvasElement;
	textLayerEl: HTMLDivElement | null;
	/** Previous text layer render that should be cancelled before rendering. */
	previousTextLayer?: { cancel: () => void } | null;
}

/**
 * Render `pageNum` (zero-based) into `canvas` at `scale`, then render the
 * text layer into `textLayerEl`. Returns the rendered viewport size and the
 * new text-layer handle. The caller is responsible for storing the handle
 * and passing it back as `previousTextLayer` on the next render.
 */
export async function renderPdfPage({
	pdfDoc,
	pageNum,
	scale,
	canvas,
	textLayerEl,
	previousTextLayer
}: RenderOptions): Promise<RenderedPage> {
	const page = await pdfDoc.getPage(pageNum + 1);

	const baseViewport = page.getViewport({ scale: 1 });
	const viewport = page.getViewport({ scale });

	// Render off-screen first so the visible canvas keeps its previous
	// content (and its previous CSS size) until the new page is fully
	// painted. Resizing the visible canvas synchronously — as we used to —
	// cleared it the moment a zoom or fit-to-width recompute fired, which
	// left a window where overlays could be drawn at the new scale on top
	// of a blank/half-painted canvas. Blitting at the end keeps canvas
	// size, canvas content, and the `viewportSize` state update atomic
	// from the reviewer's point of view.
	const offscreen = document.createElement('canvas');
	offscreen.width = viewport.width;
	offscreen.height = viewport.height;
	// pdfjs v5 takes the canvas directly and manages its own 2d context.
	await page.render({ canvas: offscreen, viewport }).promise;

	canvas.width = viewport.width;
	canvas.height = viewport.height;
	canvas.getContext('2d')!.drawImage(offscreen, 0, 0);

	const textLayer = await renderTextLayer(page, viewport, textLayerEl, scale, previousTextLayer);

	return {
		width: viewport.width,
		height: viewport.height,
		naturalWidth: baseViewport.width,
		naturalHeight: baseViewport.height,
		textLayer
	};
}

async function renderTextLayer(
	page: any,
	viewport: any,
	container: HTMLDivElement | null,
	scale: number,
	previous: { cancel: () => void } | null | undefined
): Promise<{ cancel: () => void } | null> {
	if (!container) return null;
	// Cancel any previous render — switching pages quickly can leave a stale
	// text layer half-painted if we don't explicitly abort.
	previous?.cancel();
	container.innerHTML = '';
	container.style.width = `${viewport.width}px`;
	container.style.height = `${viewport.height}px`;
	// pdf.js expects this CSS var to equal the current scale so it can size glyphs.
	container.style.setProperty('--scale-factor', String(scale));

	const pdfjsLib = await import('pdfjs-dist');
	const textContent = await page.getTextContent();
	const textLayer = new (pdfjsLib as any).TextLayer({
		textContentSource: textContent,
		container,
		viewport
	});
	try {
		await textLayer.render();
	} catch {
		// pdf.js throws on cancel — nothing to do.
	}
	return textLayer;
}

/**
 * Lazily load pdf.js and configure the worker. Safe to call multiple times —
 * pdf.js itself memoises the worker source. Returns the loaded `pdfDoc` for
 * the supplied buffer. Caller passes a *copy* of the ArrayBuffer because
 * pdf.js worker transfer detaches the original.
 */
export async function loadPdfDocument(pdfData: ArrayBuffer): Promise<any> {
	const pdfjsLib = await import('pdfjs-dist');
	pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
		'pdfjs-dist/build/pdf.worker.mjs',
		import.meta.url
	).toString();
	// .slice(0) copies the buffer so pdf.js Worker transfer doesn't detach the original.
	const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(pdfData.slice(0)) });
	return loadingTask.promise;
}
