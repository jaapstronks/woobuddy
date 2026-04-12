<script lang="ts">
	import { ArrowRight } from 'lucide-svelte';
</script>

<section class="relative flex min-h-[85vh] items-center justify-center px-6 pt-20">
	<div class="mx-auto max-w-3xl text-center">
		<h1 class="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl md:text-6xl">
			Woo-documenten lakken?
			<span class="mt-2 block text-primary">Laat je buddy het zware werk doen.</span>
		</h1>

		<p class="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-neutral">
			WOO Buddy herkent automatisch persoonsgegevens, BSN-nummers en andere gevoelige informatie
			in je documenten. Jij behoudt de controle over elke lakbeslissing.
		</p>

		<a
			href="/try"
			class="group mt-10 inline-flex items-center gap-3 rounded-xl bg-primary px-8 py-4 text-lg font-semibold text-white shadow-lg transition-all hover:bg-primary-light hover:shadow-xl"
		>
			Probeer het zelf
			<ArrowRight size={20} class="transition-transform group-hover:translate-x-1" />
		</a>
	</div>
</section>
