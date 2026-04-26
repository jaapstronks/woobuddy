<script lang="ts">
	import { Lock, EyeOff, CircleSlash, Cloud, Accessibility, Package } from 'lucide-svelte';
	import { anyPickerEnabled } from '$lib/config/file-picker';

	const cloudPickEnabled = anyPickerEnabled();

	const chips = [
		{ icon: Lock, label: 'Geen byte verlaat je computer' },
		{ icon: CircleSlash, label: 'Geen AI of LLM in de pijplijn' },
		{ icon: EyeOff, label: 'Geen cookies, geen fingerprinting' },
		{ icon: Accessibility, label: 'Geëxporteerde PDF’s zijn voorgelezen-toegankelijk' },
		{ icon: Package, label: 'Publicatieklaar volgens de DiWoo-standaard' },
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
