<script lang="ts">
	import { Lock, EyeOff, CircleSlash } from 'lucide-svelte';
	import HeroUploadPanel from './HeroUploadPanel.svelte';
</script>

<section class="relative px-6 pt-28 pb-16 sm:pt-32 sm:pb-20">
	<div class="mx-auto max-w-6xl">
		<div class="grid grid-cols-1 items-start gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
			<!-- Left column: headline + description + privacy chips -->
			<div>
				<h1
					class="fade-in-up font-serif text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl md:text-7xl"
				>
					Lak WOO-documenten
					<span class="block italic text-primary">snel, gratis en veilig.</span>
				</h1>

				<p
					class="fade-in-up mt-8 max-w-xl text-lg leading-relaxed text-ink-soft sm:text-xl"
					style="animation-delay: 120ms;"
				>
					WOO Buddy herkent BSN's, namen, adressen en andere persoonsgegevens in je
					Woo-documenten — en helpt je ze in een paar klikken weg te lakken. Het hele
					proces draait in je browser.
				</p>

				<!-- Privacy callouts -->
				<ul class="fade-in-up mt-8 flex flex-wrap gap-2.5" style="animation-delay: 240ms;">
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
					>
						<Lock size={13} class="text-primary" />
						<span>Geen byte verlaat je computer</span>
					</li>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
					>
						<CircleSlash size={13} class="text-primary" />
						<span>Geen AI of LLM in de pijplijn</span>
					</li>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-ink"
					>
						<EyeOff size={13} class="text-primary" />
						<span>Geen trackers, geen cookies</span>
					</li>
				</ul>

				<p class="mt-8 text-sm text-ink-mute">
					Geen account nodig · niets te installeren · MIT open source
				</p>
			</div>

			<!-- Right column: the hero IS the CTA. -->
			<HeroUploadPanel />
		</div>
	</div>
</section>
