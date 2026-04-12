<script lang="ts">
	import { Upload, ScanSearch, CheckCircle, Download } from 'lucide-svelte';

	const steps = [
		{
			icon: Upload,
			title: 'Upload',
			description: 'Sleep je PDF-documenten in WOO Buddy. Eén document of een heel dossier tegelijk.'
		},
		{
			icon: ScanSearch,
			title: 'Detectie',
			description:
				'WOO Buddy analyseert elk document op persoonsgegevens, identifiers en gevoelige passages.'
		},
		{
			icon: CheckCircle,
			title: 'Review',
			description:
				'Controleer de voorstellen, bevestig of wijzig lakbeslissingen, en voeg motivering toe.'
		},
		{
			icon: Download,
			title: 'Export',
			description:
				'Download gelakte documenten en een motiveringsrapport, klaar voor je Woo-besluit.'
		}
	];
</script>

<section class="bg-white px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<h2 class="text-center text-3xl font-bold text-gray-900">Hoe werkt het?</h2>
		<p class="mx-auto mt-4 max-w-2xl text-center text-neutral">
			Van upload tot Woo-besluit in vier stappen.
		</p>

		<div class="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
			{#each steps as step, i}
				<div class="flex flex-col items-center text-center">
					<div
						class="flex h-16 w-16 items-center justify-center rounded-2xl bg-landing-accent text-primary"
					>
						<step.icon size={32} />
					</div>
					<div class="mt-2 flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
						{i + 1}
					</div>
					<h3 class="mt-4 text-xl font-semibold text-gray-900">{step.title}</h3>
					<p class="mt-2 text-sm leading-relaxed text-neutral">{step.description}</p>
				</div>
			{/each}
		</div>
	</div>
</section>
