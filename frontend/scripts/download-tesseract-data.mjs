#!/usr/bin/env node
/**
 * One-shot dev setup for in-browser OCR (#49).
 *
 * Copies tesseract.js's worker + wasm core out of node_modules into
 * `static/tesseract/` and fetches the Dutch traineddata so the running
 * app can serve everything from the WOO Buddy origin — no third-party
 * CDN at runtime. The trust story ("uw documenten verlaten nooit uw
 * browser") depends on there being zero outbound requests from the
 * OCR path; a CDN download for the model would break that.
 *
 * Run once after `npm install`:
 *
 *     npm run setup:tesseract
 *
 * The downloaded files are gitignored. The script is idempotent; it
 * skips files that already exist unless `--force` is passed.
 */
import { mkdir, copyFile, stat, writeFile } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC_DIR = resolve(__dirname, '..', 'static', 'tesseract');

const force = process.argv.includes('--force');

async function exists(path) {
	try {
		await stat(path);
		return true;
	} catch {
		return false;
	}
}

async function copyFromNodeModules(pkgFile, destName) {
	const src = require.resolve(pkgFile);
	const dest = join(STATIC_DIR, destName);
	if (!force && (await exists(dest))) {
		console.log(`  skip ${destName} (exists)`);
		return;
	}
	await copyFile(src, dest);
	console.log(`  copied ${destName}`);
}

async function downloadTraineddata(lang) {
	const dest = join(STATIC_DIR, `${lang}.traineddata.gz`);
	if (!force && (await exists(dest))) {
		console.log(`  skip ${lang}.traineddata.gz (exists)`);
		return;
	}
	// tessdata_fast is the tesseract-ocr project's own GitHub repo of
	// LSTM-only models. Significantly smaller (~4 MB for Dutch) than
	// tessdata_best, with quality adequate for printed Dutch. Hosted on
	// raw.githubusercontent.com, which is GitHub's own infra — not a
	// third-party CDN — and we're downloading at dev-setup time, not at
	// runtime, so the trust story stays intact.
	const url = `https://github.com/tesseract-ocr/tessdata_fast/raw/main/${lang}.traineddata`;
	console.log(`  fetching ${lang}.traineddata from ${url}`);
	const res = await fetch(url);
	if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
	// tesseract.js serves .traineddata.gz by convention; we gzip the
	// raw file ourselves so lang loading picks it up with the default
	// file extension.
	const raw = Buffer.from(await res.arrayBuffer());
	const { gzipSync } = await import('node:zlib');
	const gz = gzipSync(raw);
	await writeFile(dest, gz);
	console.log(`  wrote ${lang}.traineddata.gz (${(gz.byteLength / 1e6).toFixed(1)} MB)`);
}

async function main() {
	await mkdir(STATIC_DIR, { recursive: true });
	console.log(`Self-hosting tesseract.js assets in ${STATIC_DIR}`);

	// The tesseract.js v5 worker script + wasm core. Path names are
	// stable across v5 patch releases; if they move, update here.
	//
	// tesseract.js picks one of four wasm variants at runtime based on
	// (a) whether the browser supports wasm-simd and (b) whether the
	// loaded traineddata is LSTM-only (tessdata_fast) or full legacy.
	// We use tessdata_fast for Dutch → tesseract requests the -lstm
	// variants. Copy all four so any browser + any future traineddata
	// swap keeps working without a re-run.
	await copyFromNodeModules('tesseract.js/dist/worker.min.js', 'worker.min.js');
	const coreVariants = [
		'tesseract-core.wasm.js',
		'tesseract-core.wasm',
		'tesseract-core-simd.wasm.js',
		'tesseract-core-simd.wasm',
		'tesseract-core-lstm.wasm.js',
		'tesseract-core-lstm.wasm',
		'tesseract-core-simd-lstm.wasm.js',
		'tesseract-core-simd-lstm.wasm'
	];
	for (const name of coreVariants) {
		await copyFromNodeModules(`tesseract.js-core/${name}`, name);
	}

	// Dutch is the only V1 language. Adding more is a one-line change
	// here (plus UI copy adjustments in OcrOptInDialog).
	await downloadTraineddata('nld');

	console.log('Done. These files are gitignored and should be re-run on fresh clones.');
}

main().catch((err) => {
	console.error(err);
	process.exit(1);
});
