<script lang="ts">
	import { ShieldOff, MousePointerClick, Brain } from 'lucide-svelte';

	const tiers = [
		{
			icon: ShieldOff,
			tier: 'Trap 1',
			title: 'Automatisch gelakt',
			description:
				'BSN-nummers, IBAN\'s en andere harde identifiers worden direct gelakt. Je kunt ze altijd terugdraaien als dat nodig is.',
			color: 'bg-gray-100 text-gray-700',
			accent: 'border-gray-300'
		},
		{
			icon: MousePointerClick,
			tier: 'Trap 2',
			title: 'Voorgesteld — jij bevestigt',
			description:
				'Namen en adressen worden gemarkeerd met een voorstel. Eén klik om te bevestigen of af te wijzen. Hetzelfde besluit wordt automatisch toegepast op alle vermeldingen.',
			color: 'bg-amber-50 text-amber-700',
			accent: 'border-amber-300'
		},
		{
			icon: Brain,
			tier: 'Trap 3',
			title: 'Gesignaleerd — jij beslist',
			description:
				'Beleidsopvattingen en gevoelige passages worden geanalyseerd. Je krijgt een analyse, mogelijke gronden en hulp bij de belangenafweging. Het besluit is altijd van jou.',
			color: 'bg-blue-50 text-primary',
			accent: 'border-primary/30'
		}
	];
</script>

<section class="bg-white px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<h2 class="text-center text-3xl font-bold text-gray-900">Jij blijft in controle</h2>
		<p class="mx-auto mt-4 max-w-2xl text-center text-neutral">
			Onze drietrapsraket combineert snelheid met zorgvuldigheid.
			Niet alles hoeft handmatig — maar het kan wel.
		</p>

		<div class="mt-16 grid grid-cols-1 gap-8 lg:grid-cols-3">
			{#each tiers as t}
				<div class="rounded-xl border-2 {t.accent} p-8">
					<div class="flex h-12 w-12 items-center justify-center rounded-lg {t.color}">
						<t.icon size={24} />
					</div>
					<span class="mt-4 inline-block rounded-full px-3 py-1 text-xs font-semibold {t.color}">
						{t.tier}
					</span>
					<h3 class="mt-2 text-xl font-semibold text-gray-900">{t.title}</h3>
					<p class="mt-2 text-sm leading-relaxed text-neutral">{t.description}</p>
				</div>
			{/each}
		</div>
	</div>
</section>
