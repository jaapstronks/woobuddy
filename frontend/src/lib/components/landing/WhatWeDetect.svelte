<script lang="ts">
	import { User, Hash, Mail, Phone, MapPin, CreditCard } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';

	const entities = [
		{
			icon: Hash,
			label: 'BSN-nummers',
			description: 'Inclusief 11-proef validatie. Auto-gelakt, terug te draaien.'
		},
		{
			icon: CreditCard,
			label: 'IBAN',
			description: 'Nederlandse en internationale rekeningnummers, met of zonder spaties.'
		},
		{
			icon: Phone,
			label: 'Telefoonnummers',
			description: 'Vast en mobiel, ook als ze door een regelafbreking lopen.'
		},
		{
			icon: Mail,
			label: 'E-mailadressen',
			description: 'Privé en zakelijk. URL-detectie als bonus.'
		},
		{
			icon: User,
			label: 'Persoonsnamen',
			description: 'Dutch NER (Deduce) plus Meertens-voornamen en CBS-achternamen.'
		},
		{
			icon: MapPin,
			label: 'Adressen',
			description: 'Straat, postcode, huisnummer — herkend als geheel.'
		}
	];
</script>

<section class="px-6 py-24">
	<div class="mx-auto max-w-6xl">
		<div class="max-w-2xl" use:reveal>
			<p class="text-sm font-medium tracking-wide text-primary uppercase">Wat WOO Buddy ziet</p>
			<h2 class="mt-3 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				Regels en patronen, geen black box.
			</h2>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				Geen taalmodel dat raadt. WOO Buddy gebruikt reguliere expressies, validatieregels
				en open Nederlandse referentielijsten. Je kunt elke beslissing nazoeken in de code.
			</p>
		</div>

		<div class="mt-16 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
			{#each entities as entity, i}
				<div
					class="bg-surface p-7 transition-colors hover:bg-primary-soft/40"
					use:reveal={{ delay: i * 70 }}
				>
					<entity.icon size={22} class="text-primary" strokeWidth={1.5} />
					<h3 class="mt-5 text-base font-semibold text-ink">{entity.label}</h3>
					<p class="mt-1.5 text-sm leading-relaxed text-ink-soft">{entity.description}</p>
				</div>
			{/each}
		</div>

		<p class="mt-10 max-w-2xl text-sm text-ink-mute">
			En meer in ontwikkeling: kentekens, paspoortnummers, creditcardnummers, en herkenning
			van publieke functionarissen die juist <em>niet</em> gelakt mogen worden.
		</p>
	</div>
</section>
