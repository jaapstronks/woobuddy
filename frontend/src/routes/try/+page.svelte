<script lang="ts">
	import { goto } from '$app/navigation';
	import { ShieldCheck, ArrowLeft, RotateCw } from 'lucide-svelte';
	import FileUpload from '$lib/components/shared/FileUpload.svelte';
	import Spinner from '$lib/components/shared/Spinner.svelte';
	import { registerDocument, analyzeDocument, ApiError } from '$lib/api/client';
	import { storePdf, PdfStoreError } from '$lib/services/pdf-store';
	import {
		extractText,
		loadPdfDocument,
		verifyPdfMagicBytes,
		PdfError
	} from '$lib/services/pdf-text-extractor';
	import type { PageExtraction } from '$lib/types';

	// Warn about long extraction time for large PDFs.
	const LARGE_PDF_BYTES = 20 * 1024 * 1024;
	const LARGE_PDF_PAGES = 100;

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let progress = $state<string | null>(null);
	let progressDetail = $state<string | null>(null);
	let error = $state<string | null>(null);
	let canRetryAnalyze = $state(false);

	// When analyze fails we keep the extracted pages + registered doc id in
	// memory so the retry button can re-run only the analyze step — the PDF
	// never gets re-read from disk and is not re-uploaded.
	let pendingDocId: string | null = null;
	let pendingPages: PageExtraction[] | null = null;

	function handleFiles(selected: File[]) {
		files = selected;
		error = null;
		canRetryAnalyze = false;
		pendingDocId = null;
		pendingPages = null;
	}

	function describeError(e: unknown): string {
		if (e instanceof PdfError) return e.message;
		if (e instanceof PdfStoreError) return e.message;
		if (e instanceof ApiError) return e.message;
		if (e instanceof Error) return e.message;
		return 'Er ging iets mis';
	}

	async function handleUpload() {
		if (files.length === 0) return;
		uploading = true;
		error = null;
		canRetryAnalyze = false;
		progressDetail = null;

		const file = files[0];
		const isLarge = file.size >= LARGE_PDF_BYTES;

		try {
			progress = 'Tekst extraheren...';
			progressDetail = isLarge
				? 'Dit is een groot bestand, de eerste stap kan even duren.'
				: null;

			const bytes = await file.arrayBuffer();
			// Magic-byte check before pdf.js so non-PDFs (JPEG renamed .pdf,
			// HTML, etc.) get rejected with a clean Dutch error instead of a
			// raw pdf.js parser exception.
			await verifyPdfMagicBytes(bytes);
			const pdfDoc = await loadPdfDocument(bytes);

			if (pdfDoc.numPages >= LARGE_PDF_PAGES && !progressDetail) {
				progressDetail = `Dit document heeft ${pdfDoc.numPages} pagina\u2019s, tekstextractie duurt iets langer.`;
			}

			const extraction = await extractText(pdfDoc);

			progress = 'Document registreren...';
			progressDetail = null;
			const doc = await registerDocument(file.name, extraction.pageCount);

			// Store PDF locally in IndexedDB (client-first: PDF never leaves browser)
			await storePdf(doc.id, file.name, bytes);

			// Stash the extraction so a failing analyze step can be retried
			// without rerunning pdf.js or re-registering the document.
			pendingDocId = doc.id;
			pendingPages = extraction.pages;

			await runAnalyze();
		} catch (e) {
			error = describeError(e);
			uploading = false;
			progress = null;
			progressDetail = null;
		}
	}

	async function runAnalyze() {
		if (!pendingDocId || !pendingPages) return;
		uploading = true;
		error = null;
		canRetryAnalyze = false;
		progress = 'Persoonsgegevens detecteren...';
		progressDetail = null;

		try {
			await analyzeDocument(pendingDocId, pendingPages);
			progress = 'Klaar! Doorsturen naar review...';
			await goto(`/review/${pendingDocId}`);
		} catch (e) {
			error = describeError(e);
			// Offer a retry that skips extraction, registration, and IndexedDB
			// storage. The user pays only for the analyze round-trip again.
			canRetryAnalyze = e instanceof ApiError || e instanceof Error;
			uploading = false;
			progress = null;
			progressDetail = null;
		}
	}
</script>

<svelte:head>
	<title>Probeer WOO Buddy</title>
</svelte:head>

<div class="flex min-h-screen flex-col items-center bg-bg px-6 py-12">
	<a href="/" class="mb-8 inline-flex items-center gap-1 text-sm text-neutral hover:text-primary">
		<ArrowLeft size={16} />
		Terug naar home
	</a>

	<div class="flex items-center gap-2">
		<ShieldCheck size={32} class="text-primary" />
		<span class="text-2xl tracking-tight">
			<span class="font-bold text-primary">WOO</span><span class="font-normal text-neutral">Buddy</span>
		</span>
	</div>

	<h1 class="mt-6 text-3xl font-bold text-gray-900">Probeer het zelf</h1>
	<p class="mt-2 max-w-md text-center text-neutral">
		Upload een PDF en bekijk welke persoonsgegevens WOO Buddy herkent.
		Geen account nodig.
	</p>

	<div class="mt-8 w-full max-w-lg">
		{#if error}
			<div class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
				<p>{error}</p>
				{#if canRetryAnalyze}
					<button
						onclick={runAnalyze}
						class="mt-3 inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
					>
						<RotateCw size={14} />
						Analyse opnieuw proberen
					</button>
				{/if}
			</div>
		{/if}

		{#if !uploading}
			<FileUpload onfiles={handleFiles} />

			{#if files.length > 0 && !canRetryAnalyze}
				<button
					onclick={handleUpload}
					class="mt-4 w-full rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-primary-light"
				>
					Analyseer document
				</button>
			{/if}
		{:else}
			<div class="flex flex-col items-center rounded-2xl border border-gray-200 bg-white px-8 py-12">
				<Spinner size="lg" />
				<p class="mt-4 text-lg font-medium text-gray-900">{progress}</p>
				<p class="mt-1 text-sm text-neutral">
					{progressDetail ?? 'Even geduld, dit kan een paar seconden duren.'}
				</p>
			</div>
		{/if}
	</div>
</div>
