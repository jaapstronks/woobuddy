<svelte:head>
	<title>Verwerkersovereenkomst — WOO Buddy</title>
	<meta
		name="description"
		content="Modeltekst verwerkersovereenkomst (DPA) voor WOO Buddy. De scope is beperkt tot accountdata en detectie-metadata — niet de documentinhoud, want die verlaat je browser nooit."
	/>
	<link rel="canonical" href="https://woobuddy.nl/verwerkersovereenkomst" />
	<meta property="og:url" content="https://woobuddy.nl/verwerkersovereenkomst" />
	<meta property="og:title" content="Verwerkersovereenkomst — WOO Buddy" />
	<meta property="og:type" content="article" />
</svelte:head>

<h1>Verwerkersovereenkomst</h1>
<p class="lead">
	Modeltekst voor een verwerkersovereenkomst (DPA) tussen jouw organisatie (verwerkingsverantwoordelijke)
	en WOO Buddy (verwerker), in lijn met artikel 28 AVG.
</p>
<p class="meta">Laatst bijgewerkt: 28 april 2026 · Versie 1.1 (model)</p>

<div class="callout">
	<p>
		<strong>Simpeler dan gebruikelijk.</strong> Omdat documentinhoud de browser nooit verlaat, gaat
		deze overeenkomst niet over PDF's. De verwerking beperkt zich tot accountgegevens en
		detectie-metadata (positie, type, artikel). Dat maakt de procurement-vragen bij een
		gemeente of ministerie aanzienlijk korter.
	</p>
</div>

<h2>1. Partijen</h2>
<ul>
	<li><strong>Verwerkingsverantwoordelijke:</strong> [naam organisatie], hierna "Klant".</li>
	<li>
		<strong>Verwerker:</strong> Bureau Bolster B.V. (KvK 61487953, h.o.d.n. WOO Buddy),
		gevestigd in Nederland, hierna "WOO Buddy".
	</li>
</ul>

<h2>2. Onderwerp en duur</h2>
<p>
	Deze overeenkomst regelt de verwerking van persoonsgegevens door WOO Buddy in het kader van de
	hoofdovereenkomst (het abonnement op WOO Buddy). Zij is van kracht zolang WOO Buddy
	persoonsgegevens van Klant verwerkt.
</p>

<h2>3. Aard en doel van de verwerking</h2>
<p>
	WOO Buddy verwerkt persoonsgegevens uitsluitend om de dienst te leveren: detectie van
	persoonsgegevens in Woo-documenten, opslag van beslissingen, en accountbeheer.
</p>

<h2>4. Soorten persoonsgegevens en betrokkenen</h2>

<h3>4.1 Wel verwerkt</h3>
<ul>
	<li>
		<strong>Gebruikers van Klant:</strong> naam, e-mailadres, organisatie, rol. Betrokkenen:
		ambtenaren en juristen van Klant.
	</li>
	<li>
		<strong>Detectie-metadata:</strong> positie (bbox-coördinaten), type (BSN, naam, adres, enz.),
		tier, Woo-artikel, reviewstatus. Betrokkenen: personen die voorkomen in de door Klant
		verwerkte documenten.
	</li>
</ul>

<h3>4.2 Uitdrukkelijk niet verwerkt</h3>
<ul>
	<li>
		<strong>Documentinhoud</strong> (de PDF zelf) — deze wordt uitsluitend in de browser van de
		gebruiker verwerkt en bereikt de servers van WOO Buddy niet.
	</li>
	<li>
		<strong>De gedetecteerde tekstwaarden zelf</strong> ("entity_text") — alleen de positie en het
		type worden opgeslagen.
	</li>
</ul>
<p>
	Zie de <a href="/privacy">privacyverklaring</a> en de technische specificatie (client-first
	architectuur) voor onderbouwing.
</p>

<h2>5. Verplichtingen WOO Buddy</h2>
<p>WOO Buddy:</p>
<ol>
	<li>verwerkt persoonsgegevens uitsluitend op basis van schriftelijke instructies van Klant;</li>
	<li>zorgt ervoor dat medewerkers zich verbinden tot geheimhouding;</li>
	<li>treft passende technische en organisatorische maatregelen (zie bijlage);</li>
	<li>verleent assistentie bij verzoeken van betrokkenen en bij DPIA-trajecten;</li>
	<li>
		verwijdert of retourneert alle persoonsgegevens na einde van de dienstverlening, binnen 30
		dagen, tenzij Unie- of lidstaatrechtelijke bepalingen opslag voorschrijven;
	</li>
	<li>stelt alle informatie beschikbaar die nodig is om naleving aan te tonen.</li>
</ol>

<h2>6. Sub-verwerkers</h2>
<p>Klant verleent algemene toestemming voor de volgende sub-verwerkers:</p>
<ul>
	<li><strong>Hetzner Online GmbH</strong> — hosting (Duitsland / Finland, binnen de EER).</li>
	<li><strong>Postmark (of gelijkwaardig)</strong> — transactionele e-mail (VS, onder SCC's).</li>
</ul>
<p>
	WOO Buddy informeert Klant schriftelijk bij voorgenomen wijzigingen; Klant heeft 30 dagen de tijd
	om gemotiveerd bezwaar te maken. Er wordt <strong>geen</strong> LLM- of AI-leverancier ingezet.
</p>

<h2>7. Doorgifte buiten de EER</h2>
<p>
	Documentinhoud wordt nooit doorgegeven. Voor accountgegevens en e-mailverkeer gebruikt WOO Buddy
	de EU-modelcontracten (Standard Contractual Clauses) waar dat nodig is (bijvoorbeeld voor
	Postmark).
</p>

<h2>8. Beveiliging</h2>
<p>WOO Buddy past ten minste de volgende maatregelen toe:</p>
<ul>
	<li>TLS 1.2 of hoger voor alle netwerkverkeer;</li>
	<li>Gehashte en gesalte wachtwoorden (bcrypt/argon2);</li>
	<li>Least-privilege toegang tot productie-infrastructuur;</li>
	<li>Logging van toegangs- en beveiligingsevents, exclusief verzoekinhoud;</li>
	<li>Periodieke security-reviews en dependency-scans;</li>
	<li>
		Architecturaal: documenten worden structureel niet naar de server verzonden — dataverlies van
		documenten is daardoor niet mogelijk.
	</li>
</ul>

<h2>9. Meldplicht datalekken</h2>
<p>
	WOO Buddy meldt een datalek zonder onredelijke vertraging en uiterlijk binnen 48 uur aan Klant,
	met voldoende informatie om Klant in staat te stellen zelf te voldoen aan artikel 33 AVG.
</p>

<h2>10. Audit</h2>
<p>
	Klant heeft het recht om jaarlijks, of bij gegronde verdenking van een inbreuk, een audit te
	(laten) uitvoeren. WOO Buddy werkt daaraan mee tegen redelijke kostenvergoeding. Voor
	Team-klanten leveren we een beknopt beveiligingsrapport op aanvraag.
</p>

<h2>11. Aansprakelijkheid</h2>
<p>
	Aansprakelijkheid volgt de hoofdovereenkomst / algemene voorwaarden. Voor schade als gevolg van
	schending van deze DPA geldt de limiet uit de hoofdovereenkomst, behoudens dwingend recht.
</p>

<h2>12. Beëindiging</h2>
<p>
	Bij beëindiging verwijdert WOO Buddy alle accountgegevens en detectie-metadata binnen 30 dagen.
	Op verzoek levert WOO Buddy een export van detectie-metadata aan in een gangbaar formaat
	(CSV/JSON).
</p>

<h2>13. Slot</h2>
<p>
	Bij tegenstrijdigheid tussen deze DPA en de hoofdovereenkomst prevaleert de DPA voor wat betreft
	privacybepalingen. Op deze DPA is Nederlands recht van toepassing.
</p>

<h2>Ondertekening</h2>
<p>
	Dit is een modeltekst. Voor daadwerkelijke ondertekening op organisatieniveau: stuur een mail
	naar
	<a href="mailto:dpa@woobuddy.nl">dpa@woobuddy.nl</a>
	— we leveren een ondertekenbare PDF op basis van dit model, aangepast aan jouw context.
</p>
