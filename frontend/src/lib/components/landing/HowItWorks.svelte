<script lang="ts">
	import { FileText, ScanSearch, CheckSquare, Download } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';

	const steps = [
		{
			icon: FileText,
			title: 'Open je PDF',
			description:
				'Sleep een document in WOO Buddy. Het bestand wordt direct ingelezen door je browser — er gaat niets de deur uit.'
		},
		{
			icon: ScanSearch,
			title: 'Detectie op je apparaat',
			description:
				'Een server zonder dataopslag krijgt alleen de losse woorden, draait er regels en patronen overheen, en stuurt coördinaten terug. Geen tekst wordt bewaard.'
		},
		{
			icon: CheckSquare,
			title: 'Jij beoordeelt',
			description:
				'Bevestig of wijzig elk voorstel. Voeg een Woo-grond en motivering toe. Sneltoetsen voor het werk dat anders uren kost.'
		},
		{
			icon: Download,
			title: 'Download de gelakte PDF',
			description:
				'PyMuPDF lakt onomkeerbaar in het geheugen en streamt de PDF terug. Je origineel raakt nooit een schijf.'
		}
	];
</script>

<section class="border-y border-border bg-surface px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<div class="max-w-2xl" use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Hoe het werkt</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				Vier stappen. Je document blijft van jou.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				WOO Buddy is gebouwd op één principe: het document is van jou en blijft van jou. De
				server ziet nooit een hele zin, laat staan een volledige pagina.
			</p>
		</div>

		<ol class="mt-16 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-2 lg:grid-cols-4">
			{#each steps as step, i}
				<li class="flex flex-col bg-surface p-8" use:reveal={{ delay: i * 90 }}>
					<div class="flex items-center gap-3">
						<span
							class="font-serif text-3xl text-primary"
						>0{i + 1}</span>
						<step.icon size={20} class="text-ink-mute" />
					</div>
					<h3 class="mt-6 text-lg font-semibold text-ink">{step.title}</h3>
					<p class="mt-2 text-sm leading-relaxed text-ink-soft">{step.description}</p>
				</li>
			{/each}
		</ol>
	</div>
</section>
