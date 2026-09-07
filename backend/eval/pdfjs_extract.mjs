#!/usr/bin/env node
/**
 * Extract text the way the browser does, for the evaluation harness.
 *
 * KEEP IN SYNC WITH `frontend/src/lib/services/pdf-text-extractor.ts`.
 * ------------------------------------------------------------------
 * The harness only measures something real if the text it feeds the pipeline
 * is byte-for-byte what the frontend would have sent. That text is not
 * `page.get_text()` from PyMuPDF: it is pdf.js `getTextContent()` items in
 * content-stream order, joined with '' when they touch on the same line and
 * with ' ' otherwise, with no newlines anywhere. Reimplementing that join in
 * Python was how the first version of this harness ended up measuring its own
 * tokenizer instead of the detector, so this script runs the real pdf.js and
 * mirrors `extractText()` line by line: same transform maths, same viewport
 * pair, same tolerances, same `normalizeRotation`.
 *
 * Any change to `extractText()` has to be repeated here (and vice versa).
 * `test_pdfjs_extract.py` pins the join rule so the two cannot drift silently.
 *
 * Usage:  node pdfjs_extract.mjs <file.pdf>
 * Writes to stdout:
 *   { "page_count": N,
 *     "pages": [{ "page_number": 1,            // 1-based
 *                 "full_text": "...",
 *                 "text_items": [{text,x0,y0,x1,y1}],   // viewer space
 *                 "rotation": 0 }] }
 */

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

/**
 * Find `pdfjs-dist` without an install of our own.
 *
 * The harness runs from `backend/`, sometimes inside a git worktree whose
 * `frontend/node_modules` was never populated. Walking up the directory tree
 * finds the real checkout in both cases (a worktree under `.claude/worktrees/`
 * still has the main checkout as an ancestor). `WOOBUDDY_PDFJS_DIST` overrides
 * everything for exotic layouts.
 */
function findPdfjs() {
	const suffixes = [
		join('frontend', 'node_modules', 'pdfjs-dist'),
		join('node_modules', 'pdfjs-dist')
	];
	const override = process.env.WOOBUDDY_PDFJS_DIST;
	const roots = [];
	if (override) roots.push(override);
	let dir = HERE;
	for (;;) {
		for (const suffix of suffixes) roots.push(join(dir, suffix));
		const up = dirname(dir);
		if (up === dir) break;
		dir = up;
	}
	for (const root of roots) {
		const entry = join(root, 'legacy', 'build', 'pdf.mjs');
		if (existsSync(entry)) return root;
	}
	throw new Error(
		'pdfjs-dist not found. Run `npm install` in frontend/, or set ' +
			'WOOBUDDY_PDFJS_DIST to a pdfjs-dist directory.'
	);
}

const PDFJS_ROOT = findPdfjs();
const pdfjsLib = await import(
	pathToFileURL(join(PDFJS_ROOT, 'legacy', 'build', 'pdf.mjs')).href
);

// No DOM, no real worker thread: point `workerSrc` at the legacy worker so
// pdf.js can load it as a module in-process (its fake-worker path) instead of
// trying to construct a browser `Worker`.
pdfjsLib.GlobalWorkerOptions.workerSrc = pathToFileURL(
	join(PDFJS_ROOT, 'legacy', 'build', 'pdf.worker.mjs')
).href;

/** Mirror of `normalizeRotation` in `frontend/src/lib/services/reading-axis.ts`. */
function normalizeRotation(rotation) {
	if (typeof rotation !== 'number' || !Number.isFinite(rotation)) return 0;
	const normalized = ((Math.round(rotation) % 360) + 360) % 360;
	return normalized === 90 || normalized === 180 || normalized === 270 ? normalized : 0;
}

/** Mirror of `toViewportBox` in `pdf-text-extractor.ts`. */
function toViewportBox(viewport, x0, yBottom, x1, yTop) {
	const [ax, ay] = viewport.convertToViewportPoint(x0, yBottom);
	const [bx, by] = viewport.convertToViewportPoint(x1, yTop);
	return {
		x0: Math.min(ax, bx),
		y0: Math.min(ay, by),
		x1: Math.max(ax, bx),
		y1: Math.max(ay, by)
	};
}

// Mirror of the constants in `extractText()`.
const SAME_LINE_TOLERANCE = 2; // points
const ADJACENT_X_TOLERANCE = 1.5; // points

/**
 * Join text items into one line of page text, exactly as `extractText()` does.
 *
 * `boxes` are the *unrotated* (layout viewport) boxes. `pdfio.join_items()`
 * is the Python twin, used to rebuild `full_text` after a planted item has
 * been moved back into reading order; `test_pdfjs_extract.py` asserts the two
 * agree on a generated PDF.
 */
function joinItems(texts, boxes) {
	return texts.reduce((acc, text, idx) => {
		if (idx === 0) return text;
		const box = boxes[idx];
		const prev = boxes[idx - 1];
		const sameLine = Math.abs(box.y0 - prev.y0) < SAME_LINE_TOLERANCE;
		const touching = sameLine && box.x0 - prev.x1 < ADJACENT_X_TOLERANCE;
		return acc + (touching ? '' : ' ') + text;
	}, '');
}

async function extract(path) {
	const bytes = await readFile(path);
	const pdfDoc = await pdfjsLib.getDocument({
		data: new Uint8Array(bytes),
		// Node has no font machinery and we never rasterise: skip both, and
		// keep pdf.js off `eval` so it behaves like the CSP'd browser build.
		disableFontFace: true,
		isEvalSupported: false,
		useWorkerFetch: false,
		standardFontDataUrl: join(PDFJS_ROOT, 'standard_fonts') + '/'
	}).promise;

	const pageCount = pdfDoc.numPages;
	const pages = [];
	for (let pageIdx = 0; pageIdx < pageCount; pageIdx++) {
		const page = await pdfDoc.getPage(pageIdx + 1);
		const viewport = page.getViewport({ scale: 1.0 });
		const layoutViewport = page.getViewport({ scale: 1.0, rotation: 0 });
		const textContent = await page.getTextContent();

		const textItems = [];
		const layoutBoxes = [];
		for (const item of textContent.items) {
			if (!('str' in item) || !item.str.trim()) continue;
			const text = item.str.trim();
			const tx = item.transform;
			const x0 = tx[4];
			const yBottom = tx[5];
			const fontHeight = Math.hypot(tx[2], tx[3]);
			const x1 = x0 + item.width;
			const yTop = yBottom + fontHeight;
			textItems.push({ text, ...toViewportBox(viewport, x0, yBottom, x1, yTop) });
			layoutBoxes.push(toViewportBox(layoutViewport, x0, yBottom, x1, yTop));
		}

		pages.push({
			page_number: pageIdx + 1, // 1-based; the harness keys everything on it
			full_text: joinItems(
				textItems.map((i) => i.text),
				layoutBoxes
			),
			text_items: textItems,
			// The unrotated boxes travel with the page so `pdfio.py` can redo the
			// join after relocating a planted item without re-deriving them.
			layout_boxes: layoutBoxes,
			rotation: normalizeRotation(viewport.rotation)
		});
		page.cleanup();
	}
	// `destroy()` moved onto the loading task between pdf.js majors; the
	// process exits right after either way, so this is only good manners.
	await pdfDoc.cleanup?.();
	return { page_count: pageCount, pages };
}

const arg = process.argv[2];
if (!arg) {
	process.stderr.write('usage: node pdfjs_extract.mjs <file.pdf>\n');
	process.exit(2);
}
const result = await extract(resolve(arg));
process.stdout.write(JSON.stringify(result));
