<script lang="ts">
	import { goto } from '$app/navigation';
	import { ArrowLeft } from 'lucide-svelte';
	import { createDossier } from '$lib/api/client';

	let title = $state('');
	let requestNumber = $state('');
	let organization = $state('');
	let submitting = $state(false);
	let error = $state<string | null>(null);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		submitting = true;
		error = null;

		try {
			const dossier = await createDossier({
				title,
				request_number: requestNumber,
				organization
			});
			await goto(`/app/dossier/${dossier.id}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Aanmaken mislukt';
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Nieuw dossier — WOO Buddy</title>
</svelte:head>

<div>
	<a href="/app" class="mb-6 inline-flex items-center gap-1 text-sm text-neutral hover:text-primary">
		<ArrowLeft size={16} />
		Terug naar dossiers
	</a>

	<h1 class="text-2xl font-bold text-gray-900">Nieuw dossier</h1>
	<p class="mt-1 text-sm text-neutral">Maak een dossier aan voor je Woo-verzoek</p>

	{#if error}
		<div class="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
			{error}
		</div>
	{/if}

	<form onsubmit={handleSubmit} class="mt-8 max-w-lg space-y-6">
		<div>
			<label for="title" class="block text-sm font-medium text-gray-700">Titel</label>
			<input
				id="title"
				type="text"
				bind:value={title}
				required
				placeholder="bijv. Woo-verzoek subsidieverlening 2024"
				class="mt-1 block w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none"
			/>
		</div>

		<div>
			<label for="request-number" class="block text-sm font-medium text-gray-700">Zaaknummer</label>
			<input
				id="request-number"
				type="text"
				bind:value={requestNumber}
				required
				placeholder="bijv. WOO-2024-0042"
				class="mt-1 block w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none"
			/>
		</div>

		<div>
			<label for="organization" class="block text-sm font-medium text-gray-700">Organisatie</label>
			<input
				id="organization"
				type="text"
				bind:value={organization}
				required
				placeholder="bijv. Gemeente Amsterdam"
				class="mt-1 block w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none"
			/>
		</div>

		<div class="flex gap-3 pt-2">
			<button
				type="submit"
				disabled={submitting}
				class="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-light disabled:opacity-50"
			>
				{submitting ? 'Aanmaken...' : 'Dossier aanmaken'}
			</button>
			<a
				href="/app"
				class="rounded-lg border border-gray-300 px-6 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
			>
				Annuleren
			</a>
		</div>
	</form>
</div>
