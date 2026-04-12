<script lang="ts">
	import { page } from '$app/state';
	import { ArrowLeft } from 'lucide-svelte';
	import MotivationReport from '$lib/components/export/MotivationReport.svelte';
	import { getDossier } from '$lib/api/client';
	import type { DossierWithStats } from '$lib/types';

	const dossierId = $derived(page.params.dossierId!);

	let dossier = $state<DossierWithStats | null>(null);
	let exporting = $state(false);
	let exportDone = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		getDossier(dossierId)
			.then((d) => (dossier = d))
			.catch((e) => (error = e instanceof Error ? e.message : 'Laden mislukt'));
	});

	async function handleExport() {
		exporting = true;
		error = null;
		try {
			const res = await fetch(`http://localhost:8000/api/dossiers/${dossierId}/export`, {
				method: 'POST'
			});
			if (!res.ok) throw new Error(await res.text());
			exportDone = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Export mislukt';
		} finally {
			exporting = false;
		}
	}
</script>

<svelte:head>
	<title>Export — WOO Buddy</title>
</svelte:head>

<div>
	<a
		href="/app/dossier/{dossierId}"
		class="mb-6 inline-flex items-center gap-1 text-sm text-neutral hover:text-primary"
	>
		<ArrowLeft size={16} />
		Terug naar dossier
	</a>

	<h1 class="text-2xl font-bold text-gray-900">
		Export{dossier ? `: ${dossier.title}` : ''}
	</h1>
	<p class="mt-1 text-sm text-neutral">
		Genereer gelakte PDF's en het motiveringsrapport voor het Woo-besluit.
	</p>

	{#if error}
		<div class="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
			{error}
		</div>
	{/if}

	{#if exportDone}
		<div class="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700">
			Export succesvol! Download de bestanden hieronder.
		</div>
	{/if}

	<div class="mt-8">
		<MotivationReport {dossierId} {exporting} onExport={handleExport} />
	</div>
</div>
