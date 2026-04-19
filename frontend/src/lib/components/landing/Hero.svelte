<script lang="ts">
	import HeroUploadPanel from './HeroUploadPanel.svelte';
	import MarketingIntro from './MarketingIntro.svelte';
	import SelfHostIntro from './SelfHostIntro.svelte';
	import { isHosted } from '$lib/config/site';

	const hosted = isHosted();
</script>

<section class="hero-section relative overflow-hidden px-6 pt-28 pb-20 sm:pt-32">
	<div
		aria-hidden="true"
		class="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[860px] bg-[radial-gradient(ellipse_60%_55%_at_50%_45%,_var(--color-primary-soft),_transparent_70%)]"
	></div>

	<div class="mx-auto max-w-6xl">
		{#if hosted}
			<MarketingIntro />
		{:else}
			<SelfHostIntro />
		{/if}

		<div class="hero-upload mx-auto mt-14 max-w-4xl sm:mt-16">
			<HeroUploadPanel />
		</div>

		<p class="mt-8 text-center text-sm text-ink-mute">
			Geen account nodig · niets te installeren · MIT open source
		</p>
	</div>
</section>
