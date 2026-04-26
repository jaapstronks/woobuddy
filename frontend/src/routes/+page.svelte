<script lang="ts">
	import Header from '$lib/components/landing/Header.svelte';
	import Hero from '$lib/components/landing/Hero.svelte';
	import HowItWorks from '$lib/components/landing/HowItWorks.svelte';
	import Trust from '$lib/components/landing/Trust.svelte';
	import Footer from '$lib/components/landing/Footer.svelte';
	import { isHosted } from '$lib/config/site';

	const hosted = isHosted();
</script>

<svelte:head>
	{#if hosted}
		<title>WOO Buddy — Woo-documenten lakken in je browser, zonder upload</title>
		<meta
			name="description"
			content="WOO Buddy herkent BSN's, namen, adressen en andere persoonsgegevens in Woo-documenten en helpt je ze in een paar klikken weg te lakken. Draait volledig in je browser. Geen upload, geen AI, geen advertentietrackers."
		/>
		<link rel="canonical" href="https://woobuddy.nl/" />
		<meta property="og:url" content="https://woobuddy.nl/" />
		<meta property="og:type" content="website" />

		<!-- JSON-LD: WebApplication + Organization for rich results -->
		{@html `<script type="application/ld+json">${JSON.stringify({
			'@context': 'https://schema.org',
			'@graph': [
				{
					'@type': 'WebApplication',
					'@id': 'https://woobuddy.nl/#app',
					name: 'WOO Buddy',
					url: 'https://woobuddy.nl/',
					applicationCategory: 'BusinessApplication',
					operatingSystem: 'Any (web browser)',
					inLanguage: 'nl-NL',
					description:
						'WOO Buddy lakt Woo-documenten volledig in de browser. Herkent BSN\\u2019s, namen, adressen en andere persoonsgegevens. Geen upload, geen AI, geen advertentietrackers.',
					browserRequirements: 'Requires a modern browser with JavaScript enabled',
					offers: {
						'@type': 'Offer',
						price: '0',
						priceCurrency: 'EUR'
					},
					isAccessibleForFree: true,
					license: 'https://opensource.org/licenses/MIT',
					featureList: [
						'Client-first: PDFs blijven in de browser',
						'Regex + NER detectie van BSN, IBAN, telefoonnummers, namen en adressen',
						'Publiek-functionaris filter',
						'Export als gelakt PDF',
						'Publicatieklare DiWoo-bundel (metadata.xml + GPP-Woo metadata.json + lakkenoverzicht)',
						'Open source (MIT)'
					]
				},
				{
					'@type': 'Organization',
					'@id': 'https://woobuddy.nl/#org',
					name: 'WOO Buddy',
					url: 'https://woobuddy.nl/',
					logo: 'https://woobuddy.nl/favicon/android-icon-192x192.png',
					sameAs: ['https://github.com/jaapstronks/woobuddy']
				}
			]
		})}</` + `script>`}
	{:else}
		<title>WOO Buddy — open source Woo-redactietool</title>
		<meta
			name="description"
			content="Open source redactietool voor Woo-documenten. Herkent BSN's, namen, adressen en andere persoonsgegevens. PDF-tekstextractie en detectie draaien in de browser."
		/>
		<meta name="robots" content="noindex" />
	{/if}
</svelte:head>

<div class="min-h-screen bg-bg text-ink">
	<Header />
	<main>
		<Hero />
		{#if hosted}
			<HowItWorks />
			<Trust />
		{/if}
	</main>
	<Footer />
</div>
