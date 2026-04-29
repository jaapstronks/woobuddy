<script lang="ts">
	import { ScanSearch, CheckSquare, Download } from 'lucide-svelte';
	import { reveal } from '$lib/actions/reveal';

	const steps = [
		{
			icon: ScanSearch,
			title: 'Herkennen in je browser',
			description:
				'Je browser leest de tekst zelf uit de PDF. Alleen die tekst gaat even naar de server: binnen enkele seconden wijst die BSN\u2019s, IBAN\u2019s, namen en adressen aan, en meteen daarna wordt de tekst weer weggegooid. Geen AI, geen black box.'
		},
		{
			icon: CheckSquare,
			title: 'Beoordelen met één toets',
			description:
				'Harde persoonsgegevens zoals BSN en IBAN worden meteen gelakt; daar valt niets over te oordelen. Voor namen, adressen en andere gevoelige context krijg je een voorstel dat je met één toetsaanslag bevestigt of afwijst. Eén beslissing geldt meteen voor elke plek waar dezelfde naam of hetzelfde adres in het document terugkomt.'
		},
		{
			icon: Download,
			title: 'Exporteren zonder opslag',
			description:
				'Bij het exporteren gaat de PDF nog één keer naar de server, wordt daar in het werkgeheugen onomkeerbaar gelakt en direct weer naar jou teruggestuurd. We bewaren niets — geen origineel, geen gelakte versie, geen logregel met inhoud. Daarnaast krijg je optioneel een onderbouwingsrapport als bijlage bij je Woo-besluit (per gelakte passage de juridische grond, motivering en SHA-256-hashes ter verificatie), of een publicatieklare DiWoo-bundel die direct ingelezen kan worden door GPP-Woo of een ander Woo-platform.'
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
				WOO Buddy neemt je het monnikenwerk uit handen, niet de beoordeling. Je ziet
				elk voorstel, je bevestigt elke beslissing, en de verantwoordelijkheid voor
				het besluit blijft bij jou.
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
