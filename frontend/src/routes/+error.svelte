<script lang="ts">
	import { page } from '$app/state';

	// Plain HTML on purpose: this page also renders for `/`, which is SSR
	// and must stay Shoelace-free (#68). Do not echo `page.error.message`
	// — it can carry an internal path or an upstream body; the status
	// code plus a Dutch line is all a visitor needs.
	const copy = $derived.by(() => {
		switch (page.status) {
			case 404:
				return {
					title: 'Pagina niet gevonden',
					body: 'Het adres klopt niet meer of heeft nooit bestaan.'
				};
			case 429:
			case 503:
				return {
					title: 'Even geduld',
					body: 'De server is tijdelijk druk. Probeer het over een minuut opnieuw.'
				};
			default:
				return {
					title: 'Er ging iets mis',
					body: 'Probeer het later opnieuw. Uw document blijft in uw browser en gaat niet verloren.'
				};
		}
	});
</script>

<svelte:head>
	<title>{page.status} · {copy.title} — WOO Buddy</title>
</svelte:head>

<main class="mx-auto max-w-xl px-6 py-24 text-ink">
	<p class="text-sm font-medium tracking-wide text-ink-mute uppercase">Fout {page.status}</p>
	<h1 class="mt-2 text-2xl font-semibold">{copy.title}</h1>
	<p class="mt-3 text-ink-soft">{copy.body}</p>
	<a
		href="/"
		class="mt-8 inline-block rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-hover"
	>
		Terug naar WOO Buddy
	</a>
</main>
