<script lang="ts">
	import { Plus, FolderOpen } from 'lucide-svelte';
	import DossierCard from '$lib/components/dossier/DossierCard.svelte';
	import Spinner from '$lib/components/shared/Spinner.svelte';
	import { listDossiers } from '$lib/api/client';
	import type { Dossier } from '$lib/types';

	let dossiers = $state<Dossier[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		listDossiers()
			.then((data) => {
				dossiers = data;
			})
			.catch((e) => {
				error = e instanceof Error ? e.message : 'Laden mislukt';
			})
			.finally(() => {
				loading = false;
			});
	});
</script>

<svelte:head>
	<title>Dossiers — WOO Buddy</title>
</svelte:head>

<div class="flex items-center justify-between">
	<div>
		<h1 class="text-2xl font-bold text-gray-900">Dossiers</h1>
		<p class="mt-1 text-sm text-neutral">Beheer je Woo-verzoeken en documenten</p>
	</div>
	<a
		href="/app/dossier"
		class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-light"
	>
		<Plus size={18} />
		Nieuw dossier
	</a>
</div>

{#if loading}
	<div class="mt-12 flex justify-center">
		<Spinner />
	</div>
{:else if error}
	<div class="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
		{error}
	</div>
{:else if dossiers.length === 0}
	<div class="mt-16 flex flex-col items-center text-center">
		<div class="flex h-16 w-16 items-center justify-center rounded-2xl bg-gray-100 text-neutral">
			<FolderOpen size={32} />
		</div>
		<h2 class="mt-4 text-lg font-semibold text-gray-900">Nog geen dossiers</h2>
		<p class="mt-1 text-sm text-neutral">Maak een nieuw dossier aan om te beginnen.</p>
		<a
			href="/app/dossier"
			class="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-light"
		>
			<Plus size={18} />
			Nieuw dossier
		</a>
	</div>
{:else}
	<div class="mt-6 grid gap-4">
		{#each dossiers as dossier (dossier.id)}
			<DossierCard {dossier} />
		{/each}
	</div>
{/if}
