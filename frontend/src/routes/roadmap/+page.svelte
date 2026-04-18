<script lang="ts">
	import Header from '$lib/components/landing/Header.svelte';
	import Footer from '$lib/components/landing/Footer.svelte';
</script>

<svelte:head>
	<title>Roadmap — WOO Buddy</title>
	<meta
		name="description"
		content="Wat we nu bouwen, wat hierna komt en wat verder op de planning staat voor WOO Buddy. Open en transparant — passend bij een tool voor de Wet open overheid."
	/>
	<link rel="canonical" href="https://woobuddy.nl/roadmap" />
	<meta property="og:url" content="https://woobuddy.nl/roadmap" />
	<meta property="og:title" content="Roadmap — WOO Buddy" />
	<meta property="og:type" content="article" />
</svelte:head>

<div class="min-h-screen bg-bg text-ink">
	<Header />
	<main class="px-6 pt-28 pb-16 sm:pt-32 sm:pb-20">
		<article class="mx-auto max-w-3xl roadmap-prose">
			<h1>Roadmap</h1>
			<p class="lead">
				Wat we nu bouwen, wat hierna komt en wat verder op de planning staat. Een tool voor de Wet
				open overheid hoort zélf ook open te zijn over wat er op de planning staat.
			</p>
			<p class="meta">Laatst bijgewerkt: 18 april 2026</p>

			<div class="callout">
				<p>
					<strong>Geen beloftes, wel een algemene richting</strong> Deze pagina beschrijft onze intenties, geen
					deadlines. Volgorde en scope kunnen wijzigen op basis van feedback van reviewers en
					pilot-organisaties. Op het moment van schrijven is de tool nog volledig nieuw en niet ingebruik, dus het kan nog alle kanten op – zolang de tool overheden maar helpt om WOO-verzoeken af te handelen. Mis je iets? Mail ons op
					<a href="mailto:hoi@woobuddy.nl">hoi@woobuddy.nl</a>.
				</p>
			</div>

			<h2>Nu — waar we aan werken</h2>
			<p>
				De huidige focus: de basisfunctionaliteit gereed maken voor gebrui. De review-workflow werkt, de
				detectie is goed genoeg voor proefprojecten; nu is het tijd om te testen, feedback te verzamelen, ondersteuning voor
				meer bestandsformaten ain te voeren en de infrastructuur om publiek te kunnen lanceren.
			</p>
			<ul>
				<li>
					<strong>Productie-deployment en analytics.</strong> WOO Buddy op een stabiel publiek adres,
					met privacy-vriendelijke statistieken (Plausible, geen cookies).
				</li>
				<li>
					<strong>Meer bestandsformaten in de browser.</strong> Losse afbeeldingen, <code>.docx</code>,
					<code>.txt</code>, <code>.zip</code>-bundels en <code>.msg</code>-/e-mailbestanden — allemaal
					client-side geconverteerd, zodat ze je browser niet verlaten.
				</li>
				<li>
					<strong>Toegankelijke PDF-export.</strong> Taal-tag, XMP-metadata, alt-teksten en
					PDF/A-2b — zodat het eindresultaat voldoet aan de digitale toegankelijkheidseisen van de
					overheid.
				</li>
				<li>
					<strong>Microsoft 365 &amp; Google Drive-bestandskiezer.</strong> Direct een document uit
					SharePoint of Drive openen — client-side, zonder tussenstop op onze server.
				</li>
				<li>
					<strong>Publicatie-klare export volgens DiWoo.</strong> Een <code>.zip</code> met gelakte
					PDF, <code>metadata.xml</code> (DiWoo/TOOI) en een grondenoverzicht — klaar om te
					publiceren via GPP-Woo of een ander Woo-platform.
				</li>
				<li>
					<strong>Open source release.</strong> Volledig zelf-hostbaar onder MIT, voor gemeenten en
					ministeries die data-soevereiniteit willen garanderen.
				</li>
			</ul>

			<h2>Hierna — de volgende stap</h2>
			<p>
				Na de publieke lancering bouwen we verder op basis van wat reviewers écht vragen. Deze
				onderwerpen staan bovenaan als het signaal er is.
			</p>
			<ul>
				<li>
					<strong>Accounts en teams.</strong> Optioneel inloggen voor organisaties die samen willen
					werken aan dezelfde besluiten. De anonieme route blijft bestaan — inloggen wordt nooit
					een verplichting voor de basis-workflow.
				</li>
				<li>
					<strong>Dossier-modus.</strong> Meerdere documenten in één Woo-verzoek, met gedeelde
					beslissingen en een gezamenlijke inventarislijst. Vandaag werkt WOO Buddy per document;
					dossiers zijn de logische volgende stap.
				</li>
				<li>
					<strong>Audit-log en onderbouwingsrapport.</strong> Per gelakte passage de juridische grond
					en motivering, exporteerbaar als bijlage bij het Woo-besluit.
				</li>
				<li>
					<strong>Gedeelde woordenlijsten per organisatie.</strong> Interne namen, projectcodes en
					functietitels die in meerdere documenten terugkomen, één keer instellen en overal
					toegepast.
				</li>
			</ul>

			<h2>Later — als er vraag naar is</h2>
			<p>
				Ideeën die we interessant vinden, maar die we pas bouwen als pilot-klanten erom vragen.
				Speculatief werk leidt tot verkeerde keuzes — liever wachten tot we weten wie het gebruikt
				en hoe.
			</p>
			<ul>
				<li>
					<strong>Direct publiceren op open.overheid.nl.</strong> Eén klik vanuit de reviewer naar
					een GPP-publicatiebank-endpoint van de gemeente. De PDF gaat daarbij direct van je
					browser naar het publicatieplatform — niet via onze servers.
				</li>
				<li>
					<strong>Naam-propagatie over documenten heen.</strong> Eén keer een naam beslissen en die
					beslissing in alle documenten van hetzelfde dossier toepassen.
				</li>
				<li>
					<strong>Deduplicatie over documenten heen.</strong> Bijlagen die in meerdere mails
					terugkomen, slim herkennen en samen afhandelen.
				</li>
				<li>
					<strong>Belanghebbenden-consultatie (art. 4.4).</strong> Werkstroom voor het horen van
					derden vóór publicatie.
				</li>
				<li>
					<strong>Connectoren voor zaaksystemen.</strong> Decos, Djuma, iBabs en andere — als
					organisaties vragen om een rechtstreekse koppeling.
				</li>
				<li>
					<strong>Woo-jaarverslag-dashboard.</strong> Aantallen, doorlooptijden en gronden per
					periode, voor verantwoording aan college of raad.
				</li>
				<li>
					<strong>Microsoft-SSO en tweefactor-authenticatie.</strong> Voor organisaties met
					federatieve identiteit.
				</li>
			</ul>

			<h2>Waar we <em>niet</em> naartoe gaan</h2>
			<p>
				Sommige paden sluiten we bewust af, omdat ze het kernverhaal van WOO Buddy zouden
				ondergraven:
			</p>
			<ul>
				<li>
					<strong>Geen taalmodel in de detectiepijplijn.</strong> Geen OpenAI, geen Anthropic, geen
					Google. De detectie blijft regel-gebaseerd (regex + Dutch Deduce + woordenlijsten) zodat
					jouw documenttekst nooit naar een externe AI-leverancier gaat.
				</li>
				<li>
					<strong>Geen server-side opslag van PDF's.</strong> Niet nu, niet later. Documenten
					verlaten je browser alleen tijdelijk en in-memory tijdens de export-stap.
				</li>
				<li>
					<strong>Geen limiet op de gratis versie.</strong> Geen document-cap, geen watermerk, geen
					inlogmuur. Het gratis aanbod is de marketing, niet de teaser.
				</li>
			</ul>

			<h2>Volledige backlog</h2>
			<p>
				De volledige technische backlog — inclusief prioriteiten, afhankelijkheden en open
				vragen — staat publiek op
				<a
					href="https://github.com/jaapstronks/woobuddy/tree/main/docs/todo"
					target="_blank"
					rel="noopener noreferrer">GitHub</a
				>. Issues en pull-requests zijn welkom.
			</p>
		</article>
	</main>
	<Footer />
</div>

<style>
	.roadmap-prose :global(h1) {
		font-family: var(--font-serif);
		font-size: 2.5rem;
		line-height: 1.1;
		letter-spacing: -0.01em;
		color: var(--color-ink);
		margin-bottom: 0.5rem;
	}

	.roadmap-prose :global(.lead) {
		color: var(--color-ink-soft);
		font-size: 1.05rem;
		line-height: 1.6;
		margin-bottom: 2.5rem;
	}

	.roadmap-prose :global(h2) {
		font-family: var(--font-serif);
		font-size: 1.5rem;
		line-height: 1.25;
		color: var(--color-ink);
		margin-top: 2.5rem;
		margin-bottom: 0.75rem;
	}

	.roadmap-prose :global(p),
	.roadmap-prose :global(li) {
		color: var(--color-ink-soft);
		line-height: 1.7;
	}

	.roadmap-prose :global(p) {
		margin-bottom: 1rem;
	}

	.roadmap-prose :global(ul) {
		margin-bottom: 1rem;
		padding-left: 1.25rem;
		list-style-type: disc;
	}

	.roadmap-prose :global(li) {
		margin-bottom: 0.5rem;
	}

	.roadmap-prose :global(a) {
		color: var(--color-primary);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.roadmap-prose :global(a:hover) {
		color: var(--color-primary-hover);
	}

	.roadmap-prose :global(strong) {
		color: var(--color-ink);
		font-weight: 600;
	}

	.roadmap-prose :global(code) {
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.9em;
		background: var(--color-surface, rgba(0, 0, 0, 0.04));
		padding: 0.1em 0.35em;
		border-radius: 3px;
	}

	.roadmap-prose :global(.meta) {
		font-size: 0.85rem;
		color: var(--color-ink-mute);
		margin-bottom: 2.5rem;
	}

	.roadmap-prose :global(.callout) {
		border-left: 3px solid var(--color-primary);
		background: var(--color-primary-soft);
		padding: 1rem 1.25rem;
		border-radius: 4px;
		margin: 1.5rem 0 2.5rem;
	}

	.roadmap-prose :global(.callout p:last-child) {
		margin-bottom: 0;
	}
</style>
