<script lang="ts">
	import { goto } from '$app/navigation';
	import { ArrowLeft, RotateCw, Lock } from 'lucide-svelte';
	import FileUpload from '$lib/components/shared/FileUpload.svelte';
	import Logo from '$lib/components/shared/Logo.svelte';
	import ProgressSteps, { type Step } from '$lib/components/shared/ProgressSteps.svelte';
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

	// Multi-step progress for the upload → extract → register → analyze flow.
	// Each entry transitions pending → active → done as the pipeline runs.
	// The IDs map 1:1 to stages in `handleUpload`/`runAnalyze`; see `setStep`.
	type StepId = 'load' | 'extract' | 'register' | 'analyze';
	const INITIAL_STEPS: Step[] = [
		{ id: 'load', label: 'PDF laden', status: 'pending' },
		{ id: 'extract', label: 'Tekst extraheren (in je browser)', status: 'pending' },
		{ id: 'register', label: 'Document registreren', status: 'pending' },
		{ id: 'analyze', label: 'Persoonsgegevens detecteren', status: 'pending' }
	];

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let steps = $state<Step[]>(INITIAL_STEPS.map((s) => ({ ...s })));
	let error = $state<string | null>(null);
	let canRetryAnalyze = $state(false);

	// When analyze fails we keep the extracted pages + registered doc id in
	// memory so the retry button can re-run only the analyze step — the PDF
	// never gets re-read from disk and is not re-uploaded.
	let pendingDocId: string | null = null;
	let pendingPages: PageExtraction[] | null = null;

	function resetSteps() {
		steps = INITIAL_STEPS.map((s) => ({ ...s }));
	}

	/**
	 * Advance the stepper: mark every step before `id` as done, set `id`
	 * itself to active, and leave later steps pending. Optional `detail`
	 * and `percent` are applied to the active step — we pass `percent` for
	 * per-page extraction progress, and leave it `null` for server-bound
	 * steps that are truly indeterminate.
	 */
	function setStep(id: StepId, detail: string | null = null, percent: number | null = null) {
		const idx = INITIAL_STEPS.findIndex((s) => s.id === id);
		steps = INITIAL_STEPS.map((s, i) => {
			if (i < idx) return { ...s, status: 'done' };
			if (i === idx) return { ...s, status: 'active', detail, percent };
			return { ...s, status: 'pending' };
		});
	}

	function markAllDone() {
		steps = INITIAL_STEPS.map((s) => ({ ...s, status: 'done' }));
	}

	function handleFiles(selected: File[]) {
		files = selected;
		error = null;
		canRetryAnalyze = false;
		pendingDocId = null;
		pendingPages = null;
		resetSteps();
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
		resetSteps();

		const file = files[0];
		const isLarge = file.size >= LARGE_PDF_BYTES;

		try {
			// Step 1 — load the PDF bytes into memory. This is effectively
			// instant for small files but non-trivial for large ones.
			setStep(
				'load',
				isLarge ? 'Dit is een groot bestand, dit kan even duren.' : null
			);
			const bytes = await file.arrayBuffer();
			// Magic-byte check before pdf.js so non-PDFs (JPEG renamed .pdf,
			// HTML, etc.) get rejected with a clean Dutch error instead of a
			// raw pdf.js parser exception.
			await verifyPdfMagicBytes(bytes);
			const pdfDoc = await loadPdfDocument(bytes);

			// Step 2 — extract text per page. `extractText` reports
			// progress back so the active step can show a determinate bar.
			const totalPages = pdfDoc.numPages;
			const extractDetail =
				totalPages >= LARGE_PDF_PAGES
					? `Dit document heeft ${totalPages} pagina\u2019s.`
					: null;
			setStep('extract', extractDetail, 0);
			const extraction = await extractText(pdfDoc, (page, total) => {
				const percent = total === 0 ? 0 : Math.round((page / total) * 100);
				setStep(
					'extract',
					`Pagina ${page} van ${total}${extractDetail ? ' · ' + extractDetail : ''}`,
					percent
				);
			});

			// Step 3 — register the document server-side and persist the
			// bytes to IndexedDB. Quick, so we just flip to indeterminate.
			setStep('register');
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
			resetSteps();
		}
	}

	async function runAnalyze() {
		if (!pendingDocId || !pendingPages) return;
		uploading = true;
		error = null;
		canRetryAnalyze = false;

		// Step 4 — ship extracted text to the server and wait for the
		// detection result. Indeterminate: the server doesn't stream
		// progress, and the round-trip is the longest single step of the
		// flow, so a bar that just sits there is honest.
		setStep('analyze');

		try {
			await analyzeDocument(pendingDocId, pendingPages);
			markAllDone();
			await goto(`/review/${pendingDocId}`);
		} catch (e) {
			error = describeError(e);
			// Offer a retry that skips extraction, registration, and IndexedDB
			// storage. The user pays only for the analyze round-trip again.
			canRetryAnalyze = e instanceof ApiError || e instanceof Error;
			uploading = false;
			resetSteps();
		}
	}
</script>

<svelte:head>
	<title>Probeer WOO Buddy</title>
</svelte:head>

<div class="flex min-h-screen flex-col bg-bg text-ink">
	<header class="border-b border-border bg-bg/85 backdrop-blur-md">
		<div class="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
			<Logo size="small" />
			<a href="/" class="inline-flex items-center gap-1.5 text-sm text-ink-soft hover:text-ink">
				<ArrowLeft size={14} />
				Terug
			</a>
		</div>
	</header>

	<main class="mx-auto flex w-full max-w-2xl flex-1 flex-col px-6 py-16">
		<p class="text-sm font-medium tracking-wide text-primary uppercase">Probeer het</p>
		<h1 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
			Open een PDF en kijk wat WOO Buddy ervan maakt.
		</h1>
		<p class="mt-6 text-base leading-relaxed text-ink-soft">
			Geen account, geen registratie. Het bestand wordt gelezen door je browser. De server
			ziet alleen losse woorden en stuurt coördinaten terug.
		</p>

		<!-- Privacy reassurance band -->
		<div class="mt-8 flex items-start gap-3 rounded-md border border-border bg-surface p-4">
			<Lock size={18} class="mt-0.5 shrink-0 text-primary" />
			<p class="text-sm leading-relaxed text-ink-soft">
				<span class="font-medium text-ink">Je PDF blijft op deze computer.</span>
				WOO Buddy verstuurt geen bestanden, geen pagina-inhoud, en bewaart geen tekst. Lees
				de uitleg op de
				<a href="/#privacy" class="text-primary underline underline-offset-2 hover:text-primary-hover">privacypagina</a>.
			</p>
		</div>

		<div class="mt-10">
			{#if error}
				<div class="mb-4 rounded-md border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
					<p>{error}</p>
					{#if canRetryAnalyze}
						<button
							onclick={runAnalyze}
							class="mt-3 inline-flex items-center gap-1.5 rounded-md bg-danger px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
						>
							<RotateCw size={14} />
							Opnieuw proberen
						</button>
					{/if}
				</div>
			{/if}

			{#if !uploading}
				<FileUpload onfiles={handleFiles} />

				{#if files.length > 0 && !canRetryAnalyze}
					<button
						onclick={handleUpload}
						class="mt-4 w-full rounded-md bg-ink px-6 py-3.5 text-sm font-medium text-bg transition-colors hover:bg-primary"
					>
						Detecteer persoonsgegevens
					</button>
				{/if}
			{:else}
				<div class="rounded-md border border-border bg-surface px-8 py-8">
					<p class="mb-5 font-serif text-lg text-ink">
						WOO Buddy is aan het werk…
					</p>
					<ProgressSteps {steps} />
				</div>
			{/if}
		</div>
	</main>
</div>
