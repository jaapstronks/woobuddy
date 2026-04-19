<script lang="ts">
	import { Lock, CircleSlash, Github } from 'lucide-svelte';

	const chips = [
		{ icon: Lock, label: 'PDF blijft op je apparaat' },
		{ icon: CircleSlash, label: 'Geen LLM in de pijplijn' },
		{ icon: Github, label: 'MIT open source' }
	];
</script>

<div class="hero-text mx-auto max-w-3xl text-center">
	<h1
		class="fade-in-up font-serif text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl"
	>
		WOO Buddy
	</h1>

	<p
		class="fade-in-up mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-ink-soft"
		style="animation-delay: 120ms;"
	>
		Open source redactietool voor Woo-documenten. Sleep een PDF om te
		beginnen — tekstextractie en detectie draaien volledig in je browser.
	</p>

	<ul
		class="fade-in-up mt-8 flex flex-wrap justify-center gap-2.5"
		style="animation-delay: 240ms;"
	>
		{#each chips as chip}
			<li
				class="inline-flex items-center gap-2 rounded-md border border-border bg-surface/80 px-3 py-1.5 text-xs text-ink backdrop-blur-sm"
			>
				<chip.icon size={13} class="text-primary" />
				<span>{chip.label}</span>
			</li>
		{/each}
	</ul>
</div>
