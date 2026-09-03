<script lang="ts">
	import { CheckCircle2, Clock, AlertCircle } from 'lucide-svelte';
	import Header from '$lib/components/landing/Header.svelte';
	import Footer from '$lib/components/landing/Footer.svelte';
	import type { PageData } from './$types';

	const { data }: { data: PageData } = $props();

	// Plain HTML and lucide icons only — no Shoelace. This page is SSR'd
	// so the outcome is in the first byte of HTML: someone who clicked a
	// link in their mail should read the verdict, not watch a spinner.

	// One entry per outcome. `expired` and `invalid` share a shape but not
	// a sentence: "this link is old" and "this link is not ours" ask the
	// reader to do the same thing for different reasons, and blurring them
	// into one message makes both sound like an accusation.
	const COPY = {
		confirmed: {
			icon: CheckCircle2,
			tone: 'success',
			heading: 'Je e-mailadres is bevestigd',
			body: 'Je krijgt voortaan een bericht als er iets te melden is over WOO Buddy — teamfuncties, de NL-gehoste versie, of een grote nieuwe functie. Geen vast ritme, hooguit een paar keer per jaar. Uitschrijven kan met één klik, onderaan elk bericht.'
		},
		expired: {
			icon: Clock,
			tone: 'warning',
			heading: 'Deze link is verlopen',
			body: 'Een bevestigingslink is 48 uur geldig. Vul je e-mailadres opnieuw in en vink het vakje aan, dan sturen we een nieuwe.'
		},
		invalid: {
			icon: AlertCircle,
			tone: 'warning',
			heading: 'Deze link werkt niet',
			body: 'Waarschijnlijk is de link onderweg afgekapt door je e-mailprogramma. Vul je e-mailadres opnieuw in en vink het vakje aan, dan sturen we een nieuwe.'
		},
		missing: {
			icon: AlertCircle,
			tone: 'warning',
			heading: 'Er ontbreekt iets aan deze link',
			body: 'Deze pagina bevestigt een e-mailadres, maar de link bevat geen bevestigingscode. Kopieer de volledige link uit de e-mail, of vraag hieronder een nieuwe aan.'
		},
		unavailable: {
			icon: AlertCircle,
			tone: 'danger',
			heading: 'Het bevestigen lukte even niet',
			body: 'Dit ligt aan ons, niet aan jou. Probeer het over een paar minuten opnieuw met dezelfde link — die blijft 48 uur geldig.'
		}
	} as const;

	const view = $derived(COPY[data.status]);
	const retryable = $derived(data.status !== 'confirmed' && data.status !== 'unavailable');

	const TONE_CLASSES = {
		success: 'border-success/30 bg-success/5 text-success',
		warning: 'border-warning/30 bg-warning/5 text-warning',
		danger: 'border-danger/30 bg-danger/5 text-danger'
	} as const;
</script>

<svelte:head>
	<title>{view.heading} — WOO Buddy</title>
	<meta name="description" content="Bevestiging van je aanmelding voor updates over WOO Buddy." />
	<!-- A one-shot token page has nothing to offer a search index, and the
	     URL carries a signed address. Keep it out of results entirely. -->
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="min-h-screen bg-bg text-ink">
	<Header />
	<main class="px-6 pt-28 pb-16 sm:pt-32 sm:pb-24">
		<div class="mx-auto max-w-2xl">
			<div
				class="flex h-12 w-12 items-center justify-center rounded-full border {TONE_CLASSES[
					view.tone
				]}"
				aria-hidden="true"
			>
				<view.icon size={24} />
			</div>

			<h1 class="mt-6 font-serif text-4xl tracking-tight text-ink sm:text-5xl">
				{view.heading}
			</h1>
			<p class="mt-6 text-lg leading-relaxed text-ink-soft">
				{view.body}
			</p>

			<div class="mt-10 flex flex-wrap items-center gap-4">
				<a
					href="/"
					class="inline-flex items-center rounded-md border border-ink bg-ink px-5 py-3 text-sm font-medium text-bg transition-colors hover:border-primary hover:bg-primary"
				>
					{data.status === 'confirmed' ? 'Naar WOO Buddy' : 'Terug naar WOO Buddy'}
				</a>
				{#if retryable}
					<a
						href="/#updates"
						class="text-sm font-medium text-ink-soft underline underline-offset-4 transition-colors hover:text-ink"
					>
						Nieuwe bevestiging aanvragen
					</a>
				{/if}
			</div>

			<p class="mt-12 border-t border-border pt-6 text-sm leading-relaxed text-ink-mute">
				WOO Buddy wordt aangeboden door Bureau Bolster B.V. We gebruiken je adres alleen
				voor deze updates.
				<a href="/privacy" class="underline hover:text-ink">Hoe we met je gegevens omgaan</a>.
			</p>
		</div>
	</main>
	<Footer />
</div>
