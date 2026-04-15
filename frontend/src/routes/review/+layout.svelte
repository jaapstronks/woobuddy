<script lang="ts">
	// Shoelace: theme CSS + icon base path (components imported where used)
	import '@shoelace-style/shoelace/dist/themes/light.css';
	import { setBasePath } from '@shoelace-style/shoelace/dist/utilities/base-path.js';
	import { Monitor, ArrowLeft } from 'lucide-svelte';
	import Logo from '$lib/components/shared/Logo.svelte';

	setBasePath('https://cdn.jsdelivr.net/npm/@shoelace-style/shoelace@2.20.1/cdn/');

	let { children } = $props();
</script>

<svelte:head>
	<!--
		Review pages hold ephemeral user documents in memory — they should not
		appear in search results or social previews.
	-->
	<title>Beoordelen · WOO Buddy</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<!--
	The review interface is desktop-only by nature: it relies on a two-column
	PDF + sidebar layout, precise mouse interactions for boundary editing, and
	keyboard shortcuts. Below the lg breakpoint (1024px) we show a friendly
	Dutch fallback that points the user back to the landing page rather than
	letting them fight the layout on a phone.
-->
<div class="flex h-screen w-full flex-col overflow-hidden bg-bg lg:hidden">
	<header class="flex shrink-0 items-center justify-between border-b border-border bg-bg/85 px-6 py-4">
		<Logo />
	</header>
	<main class="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
		<div class="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary">
			<Monitor size={32} />
		</div>
		<h1 class="mb-3 text-2xl font-semibold text-ink">
			Beoordelen werkt het beste op desktop
		</h1>
		<p class="mb-2 max-w-md text-base text-ink-soft">
			De beoordelingsinterface is geoptimaliseerd voor desktop. Voor het
			nauwkeurig nakijken en aanpassen van detecties heb je een groter
			scherm en muisbediening nodig.
		</p>
		<p class="mb-8 max-w-md text-sm text-ink-soft">
			Open WOO Buddy opnieuw op een laptop of desktop met een schermbreedte
			van minimaal 1024 pixels.
		</p>
		<a
			href="/"
			class="inline-flex items-center gap-2 rounded-md border border-ink bg-ink px-4 py-2 text-sm font-medium text-bg transition-colors hover:border-primary hover:bg-primary"
		>
			<ArrowLeft size={16} />
			Terug naar start
		</a>
	</main>
</div>

<div class="hidden h-screen flex-col overflow-hidden bg-bg lg:flex">
	{@render children()}
</div>
