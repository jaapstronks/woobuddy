<script lang="ts">
	import { Lock, EyeOff, CircleSlash, Cloud } from 'lucide-svelte';
	import HeroUploadPanel from './HeroUploadPanel.svelte';
	import { anyPickerEnabled } from '$lib/config/file-picker';

	const cloudPickEnabled = anyPickerEnabled();

	const chips = [
		{ icon: Lock, label: 'Geen byte verlaat je computer' },
		{ icon: CircleSlash, label: 'Geen AI of LLM in de pijplijn' },
		{ icon: EyeOff, label: 'Geen trackers, geen cookies' },
		...(cloudPickEnabled
			? [{ icon: Cloud, label: 'Direct uit SharePoint of Drive — zonder tussenstop' }]
			: [])
	];

	let videoEl: HTMLVideoElement | undefined = $state();

	$effect(() => {
		if (!videoEl) return;
		const prefersReducedMotion = window.matchMedia(
			'(prefers-reduced-motion: reduce)'
		).matches;
		if (!prefersReducedMotion) {
			videoEl.play().catch(() => {});
		}
	});
</script>

<section class="hero-section relative overflow-hidden px-6 pt-28 pb-20 sm:pt-32">
	<!-- Soft radial wash centered behind the mockup. -->
	<div
		aria-hidden="true"
		class="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[860px] bg-[radial-gradient(ellipse_60%_55%_at_50%_45%,_var(--color-primary-soft),_transparent_70%)]"
	></div>

	<div class="mx-auto max-w-6xl">
		<!-- Headline + subhead + privacy chips, centered above the mockup. -->
		<div class="hero-text mx-auto max-w-3xl text-center">
			<h1
				class="fade-in-up font-serif text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl xl:text-7xl"
			>
				Lak WOO-documenten
				<span class="block italic text-primary">snel, gratis en veilig.</span>
			</h1>

			<p
				class="fade-in-up mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-ink-soft sm:text-xl"
				style="animation-delay: 120ms;"
			>
				WOO Buddy herkent BSN's, namen, adressen en andere persoonsgegevens in je
				Woo-documenten — en helpt je ze in een paar klikken weg te lakken. Het hele
				proces draait in je browser.
			</p>

			<ul
				class="fade-in-up mt-8 flex flex-wrap justify-center gap-2.5"
				style="animation-delay: 240ms;"
			>
				{#each chips as chip}
					<li
						class="inline-flex items-center gap-2 rounded-md border border-border bg-surface/80 px-3 py-1.5 text-xs text-ink backdrop-blur-sm transition-colors duration-200 hover:border-primary/40 hover:bg-surface"
					>
						<chip.icon size={13} class="text-primary" />
						<span>{chip.label}</span>
					</li>
				{/each}
			</ul>
		</div>

		<!-- Mockup below the headline, full container width so the laptop is
		     always visible in its entirety. -->
		<figure
			class="hero-mockup fade-in-up relative mt-14 sm:mt-20"
			style="animation-delay: 360ms;"
		>
			<video
				bind:this={videoEl}
				poster="/mockup.png"
				muted
				loop
				playsinline
				preload="metadata"
				width="1800"
				height="1168"
				aria-label="Demonstratie van de WOO Buddy review-interface: persoonsgegevens worden met één klik zwart gelakt."
				class="mx-auto h-auto w-full"
			>
				<source src="/woobuddy-demo.mp4" type="video/mp4" />
			</video>
		</figure>

		<!-- Dropzone + samples. -->
		<div class="hero-upload mx-auto mt-14 max-w-4xl sm:mt-16">
			<HeroUploadPanel />
		</div>

		<p class="mt-8 text-center text-sm text-ink-mute">
			Geen account nodig · niets te installeren · MIT open source
		</p>
	</div>
</section>
