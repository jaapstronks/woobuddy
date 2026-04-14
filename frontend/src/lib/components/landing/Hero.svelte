<script lang="ts">
	import { ArrowRight, Lock, EyeOff, CircleSlash } from 'lucide-svelte';
</script>

<section class="relative px-6 pt-32 pb-20 sm:pt-40 sm:pb-28">
	<div class="mx-auto max-w-4xl">
		<!-- Eyebrow -->
		<div
			class="fade-in-up mb-8 inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-1.5 text-xs font-medium tracking-wide text-ink-soft uppercase"
		>
			<span class="h-1.5 w-1.5 rounded-full bg-success"></span>
			Werkt 100% in je browser
		</div>

		<!-- Headline: serif for character, not Rijksoverheid sans -->
		<h1
			class="fade-in-up font-serif text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl md:text-7xl"
			style="animation-delay: 80ms;"
		>
			Lak Woo-documenten
			<span class="block italic text-primary">zonder dat er iets je laptop verlaat.</span>
		</h1>

		<p
			class="fade-in-up mt-8 max-w-2xl text-lg leading-relaxed text-ink-soft sm:text-xl"
			style="animation-delay: 200ms;"
		>
			WOO Buddy herkent BSN's, namen, adressen en andere persoonsgegevens in je
			Woo-documenten — en helpt je ze in een paar klikken weg te lakken. Het hele proces
			draait in je browser. Geen upload, geen AI, geen trackers.
		</p>

		<!-- Privacy callouts as bullet chips -->
		<ul class="fade-in-up mt-10 flex flex-wrap gap-3" style="animation-delay: 320ms;">
			<li
				class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3.5 py-2 text-sm text-ink"
			>
				<Lock size={15} class="text-primary" />
				<span>Geen byte verlaat je computer</span>
			</li>
			<li
				class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3.5 py-2 text-sm text-ink"
			>
				<CircleSlash size={15} class="text-primary" />
				<span>Geen AI of LLM in de pijplijn</span>
			</li>
			<li
				class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3.5 py-2 text-sm text-ink"
			>
				<EyeOff size={15} class="text-primary" />
				<span>Geen trackers, geen cookies</span>
			</li>
		</ul>

		<div
			class="fade-in-up mt-12 flex flex-col items-start gap-4 sm:flex-row sm:items-center"
			style="animation-delay: 440ms;"
		>
			<a
				href="/try"
				class="group inline-flex items-center gap-3 rounded-md bg-ink px-7 py-4 text-base font-medium text-bg transition-colors hover:bg-primary"
			>
				Probeer met je eigen PDF
				<ArrowRight size={18} class="transition-transform group-hover:translate-x-0.5" />
			</a>
			<span class="text-sm text-ink-mute">
				Geen account · geen registratie · niets te installeren
			</span>
		</div>
	</div>
</section>
