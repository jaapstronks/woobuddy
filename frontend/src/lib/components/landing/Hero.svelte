<script lang="ts">
	import { Lock, EyeOff, CircleSlash } from 'lucide-svelte';
	import HeroUploadPanel from './HeroUploadPanel.svelte';
</script>

<section class="hero-section relative overflow-hidden px-6 pt-28 pb-20 sm:pt-32">
	<!-- Soft radial wash behind the mockup. Uses the warm cream bg blending
	     into a faint teal glow so the laptop reads as "stage lit" without
	     any hard borders. -->
	<div
		aria-hidden="true"
		class="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[720px] bg-[radial-gradient(ellipse_70%_60%_at_70%_30%,_var(--color-primary-soft),_transparent_70%)]"
	></div>

	<div class="mx-auto max-w-6xl">
		<div
			class="grid grid-cols-1 items-center gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-10"
		>
			<!-- Left: headline + subhead + privacy chips -->
			<div class="hero-text">
				<h1
					class="fade-in-up font-serif text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl xl:text-7xl"
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

				<ul
					class="fade-in-up mt-8 flex flex-wrap gap-2.5"
					style="animation-delay: 240ms;"
				>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface/80 px-3 py-1.5 text-xs text-ink backdrop-blur-sm"
					>
						<Lock size={13} class="text-primary" />
						<span>Geen byte verlaat je computer</span>
					</li>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface/80 px-3 py-1.5 text-xs text-ink backdrop-blur-sm"
					>
						<CircleSlash size={13} class="text-primary" />
						<span>Geen AI of LLM in de pijplijn</span>
					</li>
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface/80 px-3 py-1.5 text-xs text-ink backdrop-blur-sm"
					>
						<EyeOff size={13} class="text-primary" />
						<span>Geen trackers, geen cookies</span>
					</li>
				</ul>
			</div>

			<!-- Right: mockup, bleeding off the right edge on large screens so the
			     review sidebar gets visual weight without feeling contained. The
			     PNG already includes its own drop shadow; section has
			     overflow-hidden so the bleed never introduces horizontal scroll. -->
			<figure
				class="hero-mockup fade-in-up relative lg:-mr-16 xl:-mr-28"
				style="animation-delay: 360ms;"
			>
				<img
					src="/mockup.png"
					alt="Screenshot van de WOO Buddy review-interface met gelakte tekstpassages en een zijbalk met gedetecteerde persoonsgegevens."
					width="2151"
					height="1312"
					loading="eager"
					decoding="async"
					class="mx-auto h-auto w-full lg:max-w-none lg:w-[115%] xl:w-[125%]"
				/>
			</figure>
		</div>

		<!-- Dropzone + samples, below the hero split. Wider than the headline
		     column so the two-column dropzone/samples layout has room to
		     breathe, but still narrower than the mockup for visual funnel. -->
		<div class="hero-upload mx-auto mt-14 max-w-4xl sm:mt-16">
			<HeroUploadPanel />
		</div>

		<p class="mt-8 text-center text-sm text-ink-mute">
			Geen account nodig · niets te installeren · MIT open source
		</p>
	</div>
</section>
