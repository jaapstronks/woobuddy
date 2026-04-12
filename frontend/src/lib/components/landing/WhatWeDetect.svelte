<script lang="ts">
	import { User, Hash, Mail, Phone, MapPin, CreditCard } from 'lucide-svelte';

	const entities = [
		{ icon: User, label: 'Namen', description: 'Persoonsnamen van burgers en ambtenaren' },
		{ icon: Hash, label: 'BSN-nummers', description: 'Met 11-proef validatie' },
		{ icon: Mail, label: 'E-mailadressen', description: 'Privé en zakelijke adressen' },
		{ icon: Phone, label: 'Telefoonnummers', description: 'Vast en mobiel' },
		{ icon: MapPin, label: 'Adressen', description: 'Straatnamen, postcodes, huisnummers' },
		{ icon: CreditCard, label: 'IBAN-nummers', description: 'Nederlandse en internationale IBAN\'s' }
	];
</script>

<section class="bg-bg px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<h2 class="text-center text-3xl font-bold text-gray-900">Wat herkent WOO Buddy?</h2>
		<p class="mx-auto mt-4 max-w-2xl text-center text-neutral">
			Van BSN-nummers tot beleidsopvattingen — WOO Buddy herkent het.
		</p>

		<div class="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
			{#each entities as entity}
				<div class="rounded-xl bg-white p-6 shadow-sm transition-shadow hover:shadow-md">
					<div
						class="flex h-12 w-12 items-center justify-center rounded-lg bg-landing-accent text-primary"
					>
						<entity.icon size={24} />
					</div>
					<h3 class="mt-4 text-lg font-semibold text-gray-900">{entity.label}</h3>
					<p class="mt-1 text-sm text-neutral">{entity.description}</p>
				</div>
			{/each}
		</div>

		<p class="mt-8 text-center text-sm text-neutral">
			En meer: kentekens, creditcardnummers, paspoortnummers, medische gegevens, beleidsopvattingen...
		</p>
	</div>
</section>
