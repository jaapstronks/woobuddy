<svelte:head>
	<title>Privacyverklaring — WOO Buddy</title>
	<meta
		name="description"
		content="Privacyverklaring van WOO Buddy. PDF's verlaten nooit je browser. Bij anoniem gebruik slaan we letterlijk niets op — geen documentinhoud en geen detectie-metadata."
	/>
	<link rel="canonical" href="https://woobuddy.nl/privacy" />
	<meta property="og:url" content="https://woobuddy.nl/privacy" />
	<meta property="og:title" content="Privacyverklaring — WOO Buddy" />
	<meta property="og:type" content="article" />
</svelte:head>

<h1>Privacyverklaring</h1>
<p class="lead">
	WOO Buddy is een hulpmiddel voor het lakken van Woo-documenten. Deze verklaring legt uit welke
	gegevens we verwerken en — vooral — welke niet.
</p>
<p class="meta">Laatst bijgewerkt: 29 april 2026</p>

<div class="callout">
	<p>
		<strong>Samengevat:</strong> je PDF verlaat nooit je browser. Bij gebruik zonder account slaan
		we letterlijk niets op — geen documentinhoud, geen detectie-metadata, geen logregel met
		documenttekst. De server berekent detecties in het werkgeheugen en gooit alles direct daarna
		weg.
	</p>
</div>

<h2>1. Wie is verantwoordelijk?</h2>
<p>
	WOO Buddy wordt aangeboden door Bureau Bolster B.V. (KvK 61487953), gevestigd in Nederland. Voor
	vragen over privacy kun je mailen naar
	<a href="mailto:privacy@woobuddy.nl">privacy@woobuddy.nl</a>.
</p>

<h2>2. Welke gegevens verwerken we?</h2>

<h3>2.1 Documentinhoud — niet verwerkt, niet opgeslagen</h3>
<p>
	De PDF zelf wordt in je browser geopend en verlaat je apparaat niet. Tekstextractie (pdf.js) en
	optionele OCR gebeuren lokaal. Alleen de geëxtraheerde tekst wordt — tijdens analyse — naar de
	server gestuurd om detecties te berekenen. De server verwerkt die tekst in het geheugen en gooit
	hem daarna direct weg. Er wordt niets gelogd, niets gearchiveerd, niets opgeslagen.
</p>

<h3>2.2 Detectie-metadata</h3>
<p>
	<strong>Zonder account (de standaard-flow):</strong> de server slaat
	<strong>geen</strong> detectie-metadata op. Geen positie, geen type, geen artikel-referentie,
	geen reviewstatus. Je beslissingen leven uitsluitend in het geheugen van je browser (en in
	IndexedDB op je eigen apparaat, zodat een herlaadactie ze niet wegvaagt). Open je netwerk-tabblad
	tijdens het reviewen en je ziet alleen <code>POST /api/analyze</code> en
	<code>POST /api/export/redact-stream</code> — geen <code>POST /api/documents</code>, geen
	<code>PATCH /api/detections</code>.
</p>
<p>
	<strong>Met account (toekomstig, alleen als je expliciet voor opslaan kiest):</strong> wanneer je
	besluit een sessie te bewaren, slaan we per detectie: positie (bbox-coördinaten), type (bijv.
	BSN, naam, adres), tier, artikel-referentie en reviewstatus. We bewaren <strong>niet</strong> de
	tekst zelf (geen <code>entity_text</code>) — ook niet in deze opslag-modus.
</p>

<h3>2.3 Accountgegevens (alleen bij inloggen)</h3>
<p>
	Als je een account aanmaakt: e-mailadres, naam en (voor teamaccounts) organisatie. Zonder account
	gebruiken is volledig mogelijk — de landing page en de review-omgeving werken zonder registratie.
</p>

<h3>2.4 Kiezen uit SharePoint, OneDrive of Google Drive</h3>
<p>
	Als je een bestand kiest uit Microsoft 365 (SharePoint/OneDrive) of Google Drive, meld je je
	aan bij die provider in je eigen browser. WOO Buddy ontvangt <strong>geen</strong> inloggegevens
	en krijgt <strong>geen</strong> toegang tot je hele drive — we vragen alleen toestemming om
	precies het ene bestand dat je kiest te openen (scope <code>Files.Read</code> bij Microsoft,
	<code>drive.file</code> bij Google). Het bestand wordt vervolgens rechtstreeks vanuit
	Microsoft of Google in je browser geladen via een tijdelijke, door de provider ondertekende
	link. De inhoud passeert onze servers niet. Het OAuth-token staat alleen in het geheugen van
	je browsertab en verdwijnt zodra je het tabblad sluit.
</p>

<h3>2.5 Technische logs</h3>
<p>
	De server houdt minimale toegangslogs bij (tijdstip, endpoint, statuscode) voor stabiliteit en
	beveiliging. Verzoekinhoud op <code>/api/analyze</code> en <code>/api/export/redact</code> wordt
	<strong>nooit</strong> gelogd.
</p>

<h2>3. Waarom verwerken we dit?</h2>
<ul>
	<li>
		<strong>Tekst analyseren</strong> — om BSN's, namen, adressen en andere persoonsgegevens te
		herkennen. Grondslag: uitvoering van de overeenkomst (gebruik van de dienst).
	</li>
	<li>
		<strong>Detectie-metadata opslaan</strong> — zodat je later kunt teruggrijpen op eerdere
		beslissingen. Grondslag: uitvoering van de overeenkomst.
	</li>
	<li>
		<strong>Accountgegevens</strong> — om toegang tot betaalde teamfeatures te verlenen.
		Grondslag: uitvoering van de overeenkomst.
	</li>
</ul>

<h2>4. Hoe lang bewaren we het?</h2>
<ul>
	<li><strong>Documentinhoud:</strong> niet bewaard.</li>
	<li>
		<strong>Detectie-metadata bij anoniem gebruik:</strong> niet bewaard. Alleen in je eigen
		browser (IndexedDB), tot jij die wist.
	</li>
	<li>
		<strong>Detectie-metadata bij ingelogd gebruik met expliciete opslag:</strong> zolang je
		account actief is, of tot je een document verwijdert.
	</li>
	<li><strong>Accountgegevens:</strong> tot 30 dagen na opzegging.</li>
	<li><strong>Toegangslogs:</strong> maximaal 30 dagen.</li>
</ul>

<h2>5. Met wie delen we het?</h2>
<p>
	We delen gegevens alleen met verwerkers die strikt nodig zijn om de dienst te leveren:
</p>
<ul>
	<li><strong>Hosting:</strong> Hetzner (Duitsland/Finland, binnen de EER).</li>
	<li><strong>E-mail (transactioneel):</strong> Postmark of gelijkwaardig — alleen adressen, nooit documentinhoud.</li>
	<li>
		<strong>Analytics:</strong> Plausible (zonder cookies, zonder persoonsgegevens). We tellen
		pageviews, een handvol benoemde gebeurtenissen (zoals 'document geconverteerd' of 'export
		voltooid') en uitgaande linkklikken — bijvoorbeeld naar onze GitHub-repo. Geen documentinhoud
		en geen persoonlijke gegevens.
	</li>
	<li>
		<strong>Microsoft / Google (optioneel):</strong> alleen als je zelf voor "Uit SharePoint of
		OneDrive" of "Uit Google Drive" kiest. Je authenticeert rechtstreeks bij die provider in je
		eigen browser; wij krijgen nooit je wachtwoord of iets anders dan toestemming om één bestand
		op te halen.
	</li>
</ul>
<p>
	<strong>Geen taalmodel-leverancier.</strong> WOO Buddy gebruikt geen LLM in de detectiepijplijn —
	er is dus geen OpenAI, Anthropic of Google die iets van je document te zien krijgt.
</p>

<h2>6. Jouw rechten</h2>
<p>Onder de AVG heb je recht op:</p>
<ul>
	<li>inzage in de gegevens die we van je verwerken;</li>
	<li>rectificatie of aanvulling;</li>
	<li>verwijdering ("recht op vergetelheid");</li>
	<li>beperking van de verwerking;</li>
	<li>bezwaar tegen verwerking;</li>
	<li>gegevensoverdraagbaarheid;</li>
	<li>intrekken van toestemming.</li>
</ul>
<p>
	Vraag een van deze rechten uit te oefenen via
	<a href="mailto:privacy@woobuddy.nl">privacy@woobuddy.nl</a>. We reageren binnen vier weken.
	Ontevreden? Dan kun je klagen bij de
	<a href="https://autoriteitpersoonsgegevens.nl/" target="_blank" rel="noopener noreferrer"
		>Autoriteit Persoonsgegevens</a
	>.
</p>

<h2>7. Beveiliging</h2>
<p>
	Alle verkeer gaat via TLS. Wachtwoorden worden gehasht opgeslagen. De server heeft geen toegang tot
	documentinhoud — de architectuur maakt dataverlies van documenten letterlijk onmogelijk, want er
	is geen document om kwijt te raken.
</p>

<h2>8. Wijzigingen</h2>
<p>
	We kunnen deze verklaring aanpassen. Substantiële wijzigingen kondigen we aan per e-mail
	(ingelogde gebruikers) of via een melding op deze pagina.
</p>
