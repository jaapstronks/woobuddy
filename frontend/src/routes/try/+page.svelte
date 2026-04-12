<script lang="ts">
	import { goto } from '$app/navigation';
	import { ShieldCheck, ArrowLeft } from 'lucide-svelte';
	import FileUpload from '$lib/components/shared/FileUpload.svelte';
	import Spinner from '$lib/components/shared/Spinner.svelte';
	import { createDossier, uploadDocuments, triggerDetection } from '$lib/api/client';

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let progress = $state<string | null>(null);
	let error = $state<string | null>(null);

	function handleFiles(selected: File[]) {
		files = selected;
		error = null;
	}

	async function handleUpload() {
		if (files.length === 0) return;
		uploading = true;
		error = null;

		try {
			progress = 'Tijdelijk dossier aanmaken...';
			const dossier = await createDossier({
				title: `Snel proberen — ${files[0].name}`,
				request_number: 'TRY-' + Date.now(),
				organization: 'Demo'
			});

			progress = 'Document uploaden...';
			const docs = await uploadDocuments(dossier.id, files);

			if (docs.length > 0) {
				progress = 'Persoonsgegevens detecteren...';
				await triggerDetection(docs[0].id);

				progress = 'Klaar! Doorsturen naar review...';
				await goto(`/app/dossier/${dossier.id}/review/${docs[0].id}`);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Er ging iets mis';
			uploading = false;
			progress = null;
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
				{error}
			</div>
		{/if}

		{#if !uploading}
			<FileUpload onfiles={handleFiles} />

			{#if files.length > 0}
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
				<p class="mt-1 text-sm text-neutral">Even geduld, dit kan een paar seconden duren.</p>
			</div>
		{/if}
	</div>
</div>
