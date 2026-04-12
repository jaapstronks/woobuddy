<script lang="ts">
	import Header from '$lib/components/landing/Header.svelte';
	import Hero from '$lib/components/landing/Hero.svelte';
	import HowItWorks from '$lib/components/landing/HowItWorks.svelte';
	import WhatWeDetect from '$lib/components/landing/WhatWeDetect.svelte';
	import YouDecide from '$lib/components/landing/YouDecide.svelte';
	import OpenSource from '$lib/components/landing/OpenSource.svelte';
	import Footer from '$lib/components/landing/Footer.svelte';
</script>

<svelte:head>
	<title>WOO Buddy — Jouw slimme assistent voor het lakken van Woo-documenten</title>
</svelte:head>

<div class="min-h-screen bg-bg" style="font-family: 'Plus Jakarta Sans', system-ui, sans-serif;">
	<Header />
	<main>
		<Hero />
		<HowItWorks />
		<WhatWeDetect />
		<YouDecide />
		<OpenSource />
	</main>
	<Footer />
</div>
