<script lang="ts">
	import { Upload } from 'lucide-svelte';
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
			class="group mt-10 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-gray-300 bg-landing-accent/50 px-8 py-12 transition-all hover:border-primary hover:bg-landing-accent"
		>
			<Upload size={48} class="text-gray-400 transition-colors group-hover:text-primary" />
			<span class="mt-4 text-lg font-medium text-gray-700 group-hover:text-primary">
				Sleep een PDF hierheen of klik om te uploaden
			</span>
			<span class="mt-1 text-sm text-gray-500">PDF, max. 50 MB</span>
		</a>
	</div>
</section>
