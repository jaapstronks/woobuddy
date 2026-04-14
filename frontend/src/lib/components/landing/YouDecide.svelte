<script lang="ts">
	import { Zap, Hand, Gavel } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';

	const tiers = [
		{
			icon: Zap,
			tier: 'Trap 1',
			title: 'Auto-gelakt',
			description:
				'Harde identifiers (BSN, IBAN, telefoon, e-mail) gaan direct dicht. Je ziet ze als zwart blok in de viewer en kunt ze met één klik weer openzetten als dat moet.'
		},
		{
			icon: Hand,
			tier: 'Trap 2',
			title: 'Voorgesteld — jij bevestigt',
			description:
				'Namen, adressen en andere contextuele gegevens krijgen een voorstel. Bevestig of wijs af met één toets. Hetzelfde besluit wordt automatisch toegepast op alle voorkomens in het document.'
		},
		{
			icon: Gavel,
			tier: 'Jij',
			title: 'De eindbeslissing',
			description:
				'WOO Buddy doet voorstellen, jij neemt de Woo-beslissing. Onderbouwen, motiveren, gronden kiezen — dat blijft mensenwerk. Geen taalmodel dat dat voor je doet.'
		}
	];
</script>

<section class="border-y border-border bg-surface px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<div class="max-w-2xl" use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Jij blijft in controle</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				Snelheid waar het kan, mensenwerk waar het moet.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				WOO Buddy haalt de mechanische arbeid weg, niet het oordeel. Jij ziet alles, jij
				bevestigt alles, jij zet je handtekening onder het besluit.
			</p>
		</div>

		<div class="mt-16 grid grid-cols-1 gap-6 lg:grid-cols-3">
			{#each tiers as t, i}
				<div
					class="relative flex flex-col rounded-lg border border-border bg-bg p-8 {i === 2
						? 'border-primary/40 bg-primary-soft/30'
						: ''}"
					use:reveal={{ delay: i * 110 }}
				>
					<div class="flex items-center justify-between">
						<span
							class="font-serif text-2xl text-primary"
						>{t.tier}</span>
						<t.icon size={22} class="text-ink-mute" strokeWidth={1.5} />
					</div>
					<h3 class="mt-6 text-xl font-semibold text-ink">{t.title}</h3>
					<p class="mt-3 text-sm leading-relaxed text-ink-soft">{t.description}</p>
				</div>
			{/each}
		</div>
	</div>
</section>
