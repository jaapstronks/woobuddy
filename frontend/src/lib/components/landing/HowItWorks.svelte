<script lang="ts">
	import { ScanSearch, CheckSquare, Download } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';

	const steps = [
		{
			icon: ScanSearch,
			title: 'Detectie op je apparaat',
			description:
				'Je browser leest de PDF en stuurt alleen losse woorden naar een server zonder opslag. Regels en patronen vinden BSN, IBAN, telefoon, e-mail, namen en adressen. Geen AI, geen black box.'
		},
		{
			icon: CheckSquare,
			title: 'Jij beoordeelt, met snelheidswinst',
			description:
				'Harde identifiers (Trap 1) staan direct dicht. Namen en adressen (Trap 2) krijgen een voorstel dat je met één toets bevestigt of afwijst. Dezelfde beslissing geldt voor alle voorkomens.'
		},
		{
			icon: Download,
			title: 'Download de gelakte PDF',
			description:
				'Het lakken is onomkeerbaar: de gemarkeerde tekst wordt uit de PDF verwijderd, niet alleen afgedekt. Je document wordt tijdens het lakken in het geheugen verwerkt en direct teruggestuurd — niets blijft achter.'
		}
	];
</script>

<section class="border-y border-border bg-surface px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<div class="max-w-2xl" use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Hoe het werkt</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				Drie stappen. Je document blijft van jou.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				WOO Buddy haalt de mechanische arbeid weg, niet het oordeel. Jij ziet alles, jij
				bevestigt alles, jij zet je handtekening onder het besluit.
			</p>
		</div>

		<ol
			class="mt-16 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-3"
		>
			{#each steps as step, i}
				<li class="flex flex-col bg-surface p-8" use:reveal={{ delay: i * 90 }}>
					<div class="flex items-center gap-3">
						<span class="font-serif text-3xl text-primary">0{i + 1}</span>
						<step.icon size={20} class="text-ink-mute" />
					</div>
					<h3 class="mt-6 text-lg font-semibold text-ink">{step.title}</h3>
					<p class="mt-2 text-sm leading-relaxed text-ink-soft">{step.description}</p>
				</li>
			{/each}
		</ol>
	</div>
</section>
