<script lang="ts">
	import { page } from '$app/state';
	import { ArrowLeft, Upload, FileText, Play, ExternalLink } from 'lucide-svelte';
	import Spinner from '$lib/components/shared/Spinner.svelte';
	import { getDossier, uploadDocuments, triggerDetection } from '$lib/api/client';
	import FileUpload from '$lib/components/shared/FileUpload.svelte';
	import DossierStats from '$lib/components/dossier/DossierStats.svelte';
	import OfficialsList from '$lib/components/dossier/OfficialsList.svelte';
	import { officialsStore } from '$lib/stores/officials';
	import type { DossierWithStats, Document } from '$lib/types';

	const dossierId = $derived(page.params.id!);

	let dossier = $state<DossierWithStats | null>(null);
	let documents = $state<Document[]>([]);
	let loading = $state(true);
	let uploading = $state(false);
	let error = $state<string | null>(null);

	async function loadDossier() {
		loading = true;
		try {
			dossier = await getDossier(dossierId);
			await officialsStore.load(dossierId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Laden mislukt';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		loadDossier();
	});

	async function handleUpload(files: File[]) {
		uploading = true;
		error = null;
		try {
			const newDocs = await uploadDocuments(dossierId, files);
			documents = [...documents, ...newDocs];
			await loadDossier();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Upload mislukt';
		} finally {
			uploading = false;
		}
	}

	async function handleDetect(docId: string) {
		try {
			await triggerDetection(docId);
			await loadDossier();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Detectie mislukt';
		}
	}

	async function handleOfficialUpload(file: File) {
		await officialsStore.upload(dossierId, file);
	}
</script>

<svelte:head>
	<title>{dossier?.title ?? 'Dossier'} — WOO Buddy</title>
</svelte:head>

<div>
	<a href="/app" class="mb-6 inline-flex items-center gap-1 text-sm text-neutral hover:text-primary">
		<ArrowLeft size={16} />
		Terug naar dossiers
	</a>

	{#if loading}
		<div class="flex justify-center py-12">
			<Spinner />
		</div>
	{:else if error}
		<div class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
	{:else if dossier}
		<div class="mb-6">
			<h1 class="text-2xl font-bold text-gray-900">{dossier.title}</h1>
			<p class="mt-1 text-sm text-neutral">
				{dossier.organization} &middot; {dossier.request_number}
			</p>
		</div>

		<div class="grid gap-6 lg:grid-cols-3">
			<!-- Documents -->
			<div class="rounded-xl border border-gray-200 bg-white p-6 lg:col-span-2">
				<h2 class="flex items-center gap-2 text-lg font-semibold text-gray-900">
					<FileText size={20} />
					Documenten ({dossier.document_count})
				</h2>

				<!-- Document list -->
				{#if dossier.document_count > 0}
					<div class="mt-4 space-y-2">
						<!-- We need to reload docs from the API — for now show count -->
						<p class="text-sm text-neutral">
							{dossier.document_count} document{dossier.document_count !== 1 ? 'en' : ''} geupload.
						</p>
					</div>
				{/if}

				<!-- Upload area -->
				<div class="mt-4">
					<FileUpload onfiles={handleUpload} />
					{#if uploading}
						<p class="mt-2 text-sm text-primary">Uploaden...</p>
					{/if}
				</div>
			</div>

			<!-- Sidebar: Stats + Officials -->
			<div class="space-y-6">
				<!-- Stats -->
				<div class="rounded-xl border border-gray-200 bg-white p-6">
					<h2 class="mb-4 text-lg font-semibold text-gray-900">Statistieken</h2>
					<DossierStats stats={dossier.detection_counts} documentCount={dossier.document_count} />
				</div>

				<!-- Public officials -->
				<div class="rounded-xl border border-gray-200 bg-white p-6">
					<OfficialsList
						officials={officialsStore.all}
						loading={officialsStore.loading}
						onUpload={handleOfficialUpload}
						onRemove={(id) => { /* TODO: wire delete */ }}
					/>
				</div>

				<!-- Export link -->
				<a
					href="/app/export/{dossierId}"
					class="flex items-center gap-2 rounded-xl border border-gray-200 bg-white p-4 text-sm font-medium text-primary transition-colors hover:border-primary hover:bg-primary/5"
				>
					<ExternalLink size={16} />
					Exporteren
				</a>
			</div>
		</div>
	{/if}
</div>
