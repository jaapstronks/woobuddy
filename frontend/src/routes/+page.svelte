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
	<title>WOO Buddy — Woo-documenten lakken in je browser, zonder upload</title>
</svelte:head>

<div class="min-h-screen bg-bg text-ink">
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
