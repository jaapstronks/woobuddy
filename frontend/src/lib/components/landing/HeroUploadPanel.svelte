<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Mail, Users, FileText as FileTextIcon, RotateCw, ArrowRight } from 'lucide-svelte';
	import FileUpload from '$lib/components/shared/FileUpload.svelte';
	import ProgressSteps, { type Step } from '$lib/components/shared/ProgressSteps.svelte';
	import OcrOptInDialog from './OcrOptInDialog.svelte';
	import {
		cloneInitialSteps,
		advanceTo,
		allDone,
		describeError,
		ingestFile,
		runAnalyze,
		type StepId,
		type OcrDecision
	} from '$lib/services/upload-flow';
	import type { PageExtraction } from '$lib/types';
	import { SAMPLES, type SampleDoc } from '$lib/samples';

	// Hydrate the interactive upload UI on the client only. The landing page is
	// SSR-rendered for SEO, so until onMount fires we show a static placeholder
	// that visually mirrors the drop zone.
	let hydrated = $state(false);

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let steps = $state<Step[]>(cloneInitialSteps());
	let uploadError = $state<string | null>(null);
	let canRetryAnalyze = $state(false);
	let loadingSampleId = $state<string | null>(null);

	// OCR opt-in (#49) — the upload flow calls `requestOcrDecision()`
	// when it encounters a PDF with no text layer. We open the dialog
	// and return a promise that resolves once the reviewer clicks one
	// of the two buttons. Only one dialog can be open at a time, which
	// lines up with the single-file upload flow.
	let ocrDialogOpen = $state(false);
	let ocrDecisionResolver: ((d: OcrDecision) => void) | null = null;

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

	function setStep(
		id: StepId,
		detail: string | null = null,
		percent: number | null = null,
		labelOverride: string | null = null
	) {
		steps = advanceTo(id, detail, percent, labelOverride);
	}

	function requestOcrDecision(): Promise<OcrDecision> {
		return new Promise<OcrDecision>((resolve) => {
			ocrDecisionResolver = resolve;
			ocrDialogOpen = true;
		});
	}

	function resolveOcrDecision(decision: OcrDecision) {
		ocrDialogOpen = false;
		const resolver = ocrDecisionResolver;
		ocrDecisionResolver = null;
		resolver?.(decision);
	}

	function handleFiles(selected: File[]) {
		files = selected;
		uploadError = null;
		canRetryAnalyze = false;
		pendingDocId = null;
		pendingPages = null;
		steps = cloneInitialSteps();
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

	async function handleUpload() {
		if (files.length === 0) return;
		uploading = true;
		uploadError = null;
		canRetryAnalyze = false;
		steps = cloneInitialSteps();

		try {
			const result = await ingestFile(files[0], {
				onStep: setStep,
				onNeedOcrDecision: requestOcrDecision
			});
			if (result.kind === 'declined-ocr') {
				// Reviewer opted out of OCR — skip analyze entirely and
				// drop them into the review screen where manual area
				// selection is their redaction tool.
				steps = allDone();
				await goto(`/review/${result.documentId}`);
				return;
			}
			pendingDocId = result.documentId;
			pendingPages = result.pages;
			await tryAnalyze();
		} catch (e) {
			uploadError = describeError(e);
			uploading = false;
			steps = cloneInitialSteps();
		}
	}

	async function tryAnalyze() {
		if (!pendingDocId || !pendingPages) return;
		uploading = true;
		uploadError = null;
		canRetryAnalyze = false;

		try {
			await runAnalyze(pendingDocId, pendingPages, { onStep: setStep });
			steps = allDone();
			await goto(`/review/${pendingDocId}`);
		} catch (e) {
			uploadError = describeError(e);
			// Any error at the analyze step is retryable — the document is
			// registered, pages are cached; retry skips re-extract.
			canRetryAnalyze = true;
			uploading = false;
			steps = cloneInitialSteps();
		}
	}
</script>

<div id="try" class="fade-in-up" style="animation-delay: 480ms;">
	{#if uploadError}
		<div class="mb-4 rounded-md border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
			<p>{uploadError}</p>
			{#if canRetryAnalyze}
				<button
					onclick={tryAnalyze}
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
		     doesn't jump on hydration. Height matches the hydrated dropzone
		     so the SSR paint aligns with the samples list on its right. -->
		<div
			class="flex min-h-[14rem] flex-col items-center justify-center rounded-md border border-dashed border-border-strong bg-surface px-8 py-14"
		>
			<span class="font-serif text-xl text-ink">Sleep een PDF in je browser</span>
			<span class="mt-1 text-sm text-ink-soft">of klik om te bladeren · max. 50 MB</span>
			<span
				class="mt-5 inline-flex items-center gap-1.5 rounded-full border border-border bg-bg px-2.5 py-1 text-[11px] font-medium text-ink-soft"
			>
				Blijft op je apparaat — geen upload
			</span>
		</div>
	{:else if !uploading}
		<!-- Two-column split: dropzone on the left, sample documents stacked
		     vertically on the right. On mobile both collapse to a single
		     stack so the dropzone is the first thing a reviewer touches. -->
		<div class="grid gap-6 lg:grid-cols-[1.1fr_1fr] lg:gap-8">
			<!-- Left: dropzone + conditional Detecteer button. -->
			<div class="upload-panel-dropzone flex flex-col">
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
			</div>

			<!-- Right: sample document list. Zero-friction path — click a
			     fictional sample instead of having to find a real document. -->
			<div class="upload-panel-samples flex flex-col">
				<div class="mb-3 flex items-baseline justify-between gap-4">
					<h2 class="text-xs font-medium tracking-wide text-ink-soft uppercase">
						Geen document bij de hand?
					</h2>
					<span class="text-xs text-ink-mute">100% fictieve data</span>
				</div>
				<ul class="flex flex-col gap-2">
					{#each SAMPLES as sample (sample.id)}
						{@const Icon = SAMPLE_ICONS[sample.id]}
						{@const isLoading = loadingSampleId === sample.id}
						<li>
							<button
								type="button"
								onclick={() => loadSample(sample)}
								disabled={loadingSampleId !== null}
								class="group flex w-full items-start gap-3 rounded-md border border-border bg-surface p-3 text-left transition-colors hover:border-primary/60 hover:bg-bg disabled:cursor-not-allowed disabled:opacity-60"
							>
								<span
									class="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"
								>
									<Icon size={15} />
								</span>
								<span class="flex min-w-0 flex-1 flex-col gap-0.5">
									<span class="text-sm font-medium text-ink">{sample.title}</span>
									<span class="text-xs leading-snug text-ink-soft">
										{sample.description}
									</span>
								</span>
								<span
									class="mt-1 shrink-0 text-xs font-medium text-primary"
									aria-hidden={!isLoading}
								>
									{#if isLoading}
										Laden…
									{:else}
										<ArrowRight
											size={15}
											class="transition-transform duration-200 group-hover:translate-x-0.5"
										/>
									{/if}
								</span>
							</button>
						</li>
					{/each}
				</ul>
			</div>
		</div>
	{:else}
		<div class="rounded-md border border-border bg-surface px-8 py-8">
			<p class="mb-5 font-serif text-lg text-ink">WOO Buddy is aan het werk…</p>
			<ProgressSteps {steps} />
		</div>
	{/if}

	<OcrOptInDialog
		open={ocrDialogOpen}
		onAccept={() => resolveOcrDecision('ocr')}
		onDecline={() => resolveOcrDecision('skip')}
	/>
</div>
