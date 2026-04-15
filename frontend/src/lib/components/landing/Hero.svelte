<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Lock, EyeOff, CircleSlash, RotateCw, Mail, Users, FileText as FileTextIcon } from 'lucide-svelte';
	import FileUpload from '$lib/components/shared/FileUpload.svelte';
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
	import { SAMPLES, type SampleDoc } from '$lib/samples';

	// Warn about long extraction time for large PDFs.
	const LARGE_PDF_BYTES = 20 * 1024 * 1024;
	const LARGE_PDF_PAGES = 100;

	// Multi-step progress for the upload → extract → register → analyze flow.
	type StepId = 'load' | 'extract' | 'register' | 'analyze';
	const INITIAL_STEPS: Step[] = [
		{ id: 'load', label: 'PDF laden', status: 'pending' },
		{ id: 'extract', label: 'Tekst extraheren (in je browser)', status: 'pending' },
		{ id: 'register', label: 'Document registreren', status: 'pending' },
		{ id: 'analyze', label: 'Persoonsgegevens detecteren', status: 'pending' }
	];

	// Hydrate the interactive upload UI on the client only. The landing page is
	// SSR-rendered for SEO, so until onMount fires we show a static placeholder
	// that visually mirrors the drop zone.
	let hydrated = $state(false);

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let steps = $state<Step[]>(INITIAL_STEPS.map((s) => ({ ...s })));
	let uploadError = $state<string | null>(null);
	let canRetryAnalyze = $state(false);
	let loadingSampleId = $state<string | null>(null);

	const SAMPLE_ICONS = {
		'email-thread': Mail,
		raadsverslag: Users,
		klachtbrief: FileTextIcon
	} as const;

	let pendingDocId: string | null = null;
	let pendingPages: PageExtraction[] | null = null;

	onMount(() => {
		hydrated = true;
	});

	function resetSteps() {
		steps = INITIAL_STEPS.map((s) => ({ ...s }));
	}

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
		uploadError = null;
		canRetryAnalyze = false;
		pendingDocId = null;
		pendingPages = null;
		resetSteps();
	}

	async function loadSample(sample: SampleDoc) {
		if (uploading || loadingSampleId) return;
		loadingSampleId = sample.id;
		uploadError = null;
		try {
			const res = await fetch(`/samples/${sample.id}.pdf`);
			if (!res.ok) {
				throw new Error(`Voorbeeld kon niet worden geladen (${res.status})`);
			}
			const blob = await res.blob();
			const file = new File([blob], sample.filename, { type: 'application/pdf' });
			handleFiles([file]);
			await handleUpload();
		} catch (e) {
			uploadError = describeError(e);
		} finally {
			loadingSampleId = null;
		}
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
		uploadError = null;
		canRetryAnalyze = false;
		resetSteps();

		const file = files[0];
		const isLarge = file.size >= LARGE_PDF_BYTES;

		try {
			setStep(
				'load',
				isLarge ? 'Dit is een groot bestand, dit kan even duren.' : null
			);
			const bytes = await file.arrayBuffer();
			await verifyPdfMagicBytes(bytes);
			const pdfDoc = await loadPdfDocument(bytes);

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

			setStep('register');
			const doc = await registerDocument(file.name, extraction.pageCount);

			await storePdf(doc.id, file.name, bytes);

			pendingDocId = doc.id;
			pendingPages = extraction.pages;

			await runAnalyze();
		} catch (e) {
			uploadError = describeError(e);
			uploading = false;
			resetSteps();
		}
	}

	async function runAnalyze() {
		if (!pendingDocId || !pendingPages) return;
		uploading = true;
		uploadError = null;
		canRetryAnalyze = false;

		setStep('analyze');

		try {
			await analyzeDocument(pendingDocId, pendingPages);
			markAllDone();
			await goto(`/review/${pendingDocId}`);
		} catch (e) {
			uploadError = describeError(e);
			canRetryAnalyze = e instanceof ApiError || e instanceof Error;
			uploading = false;
			resetSteps();
		}
	}
</script>

<section class="relative px-6 pt-28 pb-16 sm:pt-32 sm:pb-20">
	<div class="mx-auto max-w-6xl">
		<div class="grid grid-cols-1 items-start gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
			<!-- Left column: headline + description + privacy chips -->
			<div>
				<h1
					class="fade-in-up font-serif text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl md:text-7xl"
				>
					Lak WOO-documenten
					<span class="block italic text-primary">snel, gratis en veilig.</span>
				</h1>

				<p
					class="fade-in-up mt-8 max-w-xl text-lg leading-relaxed text-ink-soft sm:text-xl"
					style="animation-delay: 120ms;"
				>
					WOO Buddy herkent BSN's, namen, adressen en andere persoonsgegevens in je
					Woo-documenten — en helpt je ze in een paar klikken weg te lakken. Het hele
					proces draait in je browser.
				</p>

				<!-- Privacy callouts -->
				<ul class="fade-in-up mt-8 flex flex-wrap gap-2.5" style="animation-delay: 240ms;">
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
					>
						<Lock size={13} class="text-primary" />
						<span>Geen byte verlaat je computer</span>
					</li>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
					>
						<CircleSlash size={13} class="text-primary" />
						<span>Geen AI of LLM in de pijplijn</span>
					</li>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
					>
						<EyeOff size={13} class="text-primary" />
						<span>Geen trackers, geen cookies</span>
					</li>
				</ul>

				<p class="mt-8 text-sm text-ink-mute">
					Geen account nodig · niets te installeren · MIT open source
				</p>
			</div>

			<!-- Right column: the hero IS the CTA. -->
			<div id="try" class="fade-in-up lg:pt-2" style="animation-delay: 320ms;">
				{#if uploadError}
					<div class="mb-4 rounded-md border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
						<p>{uploadError}</p>
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

				{#if !hydrated}
					<!-- SSR placeholder that mirrors the drop zone shape so the page
					     doesn't jump on hydration. -->
					<div
						class="flex flex-col items-center justify-center rounded-md border border-dashed border-border-strong bg-surface px-8 py-14"
					>
						<span class="font-serif text-xl text-ink">Sleep een PDF hierheen</span>
						<span class="mt-1 text-sm text-ink-soft">of klik om te bladeren · max. 50 MB</span>
					</div>
				{:else if !uploading}
					<FileUpload onfiles={handleFiles} />

					{#if files.length > 0 && !canRetryAnalyze}
						<button
							onclick={handleUpload}
							class="detect-cta group relative mt-4 w-full overflow-hidden rounded-md bg-ink px-6 py-4 text-base font-medium text-bg shadow-sm transition-all duration-300 ease-out hover:-translate-y-0.5 hover:bg-primary hover:shadow-lg hover:shadow-primary/30 active:translate-y-0 active:scale-[0.985] active:duration-75"
						>
							<!-- Shine sweep on hover -->
							<span
								class="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 ease-out group-hover:translate-x-full"
								aria-hidden="true"
							></span>
							<span class="relative z-10 inline-flex items-center justify-center gap-2">
								Detecteer persoonsgegevens
								<svg
									xmlns="http://www.w3.org/2000/svg"
									width="18"
									height="18"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
									class="transition-transform duration-300 group-hover:translate-x-0.5"
									aria-hidden="true"
								>
									<path d="M5 12h14" />
									<path d="m12 5 7 7-7 7" />
								</svg>
							</span>
						</button>
					{/if}

					<!-- Zero-friction path: click a fictional sample instead of
					     having to find a real document first. -->
					<div class="mt-6">
						<div class="mb-3 flex items-baseline justify-between gap-4">
							<h2 class="text-xs font-medium tracking-wide text-ink-soft uppercase">
								Geen document bij de hand?
							</h2>
							<span class="text-xs text-ink-mute">100% fictieve data</span>
						</div>
						<ul class="grid gap-2 sm:grid-cols-3">
							{#each SAMPLES as sample (sample.id)}
								{@const Icon = SAMPLE_ICONS[sample.id]}
								{@const isLoading = loadingSampleId === sample.id}
								<li>
									<button
										type="button"
										onclick={() => loadSample(sample)}
										disabled={loadingSampleId !== null}
										class="group flex h-full w-full flex-col items-start gap-1.5 rounded-md border border-border bg-surface p-3 text-left transition-colors hover:border-primary/60 hover:bg-bg disabled:cursor-not-allowed disabled:opacity-60"
									>
										<span
											class="inline-flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary"
										>
											<Icon size={14} />
										</span>
										<span class="text-sm font-medium text-ink">{sample.title}</span>
										<span class="text-[11px] leading-snug text-ink-soft">
											{sample.description}
										</span>
										<span
											class="mt-auto pt-1 text-[11px] font-medium text-primary group-hover:underline"
										>
											{isLoading ? 'Voorbeeld laden…' : 'Open voorbeeld →'}
										</span>
									</button>
								</li>
							{/each}
						</ul>
					</div>
				{:else}
					<div class="rounded-md border border-border bg-surface px-8 py-8">
						<p class="mb-5 font-serif text-lg text-ink">WOO Buddy is aan het werk…</p>
						<ProgressSteps {steps} />
					</div>
				{/if}
			</div>
		</div>
	</div>
</section>
