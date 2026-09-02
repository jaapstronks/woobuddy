# TODO — woobuddy

Het nu-document. Regels (volledig: skill `werkwijze`): _In progress_ is een claimbord,
max 3 claims, leeg is de goede staat. _Open werk_ staat **top-down op prioriteit**;
nummers zijn vaste adressen, geen volgorde-sporen. Eén item is kort (2-4 zinnen, ≤ 12
regels) en draagt een toetsbaar **klaar als**; bewijs, vindplaatsen en deelpunten staan
in `briefs/<slug>.md`. Budget: **< 1.200 regels** (signaal bij 1.500). Geshipt verdwijnt
hier: één regel in _Recently done_ + de write-up in [`done/`](done/) (gesloten nummers:
[`done/register.md`](done/register.md)). Hoe het werkt staat in [`../reference/`](../reference/).

## In progress

<!-- formaat: item — @machine — `branch` — klaar als: één toetsbare zin -->

- #72 — @mbp — `feat/brevo-to-listmonk` — klaar als: een echte inzending op woobuddy.nl geeft 200, de notificatiemail komt aan op jaap@jaapstronks.nl, en een deploy zonder mailsecrets faalt zichtbaar.

## Open werk

_Ingericht bij workflow-init 2026-09-02 vanuit `docs/todo/` (fases A–G van het oude
README, bewaard als [`done/backlog-README-2026-04.md`](done/backlog-README-2026-04.md)). Blokken
top-down; binnen een blok top-down op prioriteit. #66–#71 komen uit de tighten-scan van
2026-09-02. #62 (Notion-kruisverwijzingen) is vervallen: Notion wordt niet meer gebruikt
voor de todo's van deze repo. Vervolgnummers: 73._

> **A · Kapot of doctrine-schending - eerst** - verkeerde of ontbrekende zwarte balken,
> een rode testsuite, of een trust-claim die de code niet waarmaakt.

### 72. Leadformulier op woobuddy.nl geeft 500: mailconfig bereikt de api-container niet

Gemeten op 2026-09-02: een geldige inzending op `POST /api/leads` eindigt in
`leads.brevo_api_key_missing` en een 500; in de draaiende container zijn alle `BREVO_*`-
variabelen leeg, want `docker-compose.prod.yml` geeft alleen `DATABASE_URL` door en
`deploy.sh` schrijft alleen het DB-wachtwoord naar `.env`. Het formulier heeft op productie
dus nooit gewerkt. Fix: `feat/brevo-to-listmonk` landen (lokaal, c1ee83d), mailconfig via
`env_file` in de prod-compose, en een deploy-check die een lege sleutel hard laat falen.
P0, size S + secrets. Brief: [`briefs/72-lead-form-broken-in-production.md`](briefs/72-lead-form-broken-in-production.md)

**Jaap levert:** Scaleway TEM-sleutel + project-id, Listmonk-lijst-UUID, `NOTIFICATION_EMAIL`.

**Klaar als:** een echte inzending op woobuddy.nl geeft 200 en de notificatiemail komt aan,
en een deploy zonder mailsecrets faalt zichtbaar.

### 66. Redactie-correctheid: custom termen, undo van split/merge, verdwenen motivatie

Tien bevindingen die veranderen wát er onder een zwarte balk terechtkomt, of die
reviewerwerk stilletjes weggooien. De zwaarste: een door de reviewer getypte term krijgt
op elke pagina de bbox van pagina 1, dus vanaf pagina 2 exporteert die term **ongelakt**.
Verder zijn split en merge niet ongedaan te maken, verdwijnt `motivation_text` tussen
frontend en store, en vallen out-of-range boxen zonder spoor weg. P0, size M.
Brief: [`briefs/66-redaction-correctness-bugs.md`](briefs/66-redaction-correctness-bugs.md)

**Jaap beslist eerst:** motivatietekst bewaren en tonen, of het veld uit de UI halen.

**Klaar als:** een custom term op pagina 3 exporteert gelakt met een test die dat bewijst,
Ctrl+Z draait een split én een merge terug, en export rapporteert het aantal overgeslagen
boxen.

### 67. Exportketen: Ghostscript wist `/Lang`, blokkerende I/O, schrijven naar schijf

`test_empty_redactions_returns_unmodified` faalt op elke machine mét Ghostscript en slaagt
in CI en productie alleen omdat die het niet hebben. Gevolg: productie levert nooit PDF/A,
en waar Ghostscript wél staat wist de laatste stap de `/Lang`-tag die #48 als "grootste
toegankelijkheidswinst" beloofde. Daarnaast draait de hele keten (PyMuPDF, drie
pikepdf-rondes, `subprocess.run(gs)`) synchroon in een `async def`. P1, size S–M.
Brief: [`briefs/67-export-chain-accessibility-and-async.md`](briefs/67-export-chain-accessibility-and-async.md)

**Jaap beslist eerst:** willen we PDF/A-2b überhaupt? Ja betekent Ghostscript in de
Dockerfile en in CI; nee betekent `convert_to_pdfa` en het tempfile-pad weg.

**Klaar als:** `pytest` is groen mét en zonder Ghostscript op PATH, en `/Lang` staat in de
uiteindelijke bytes van elke export.

### 68. Landingspagina laadt Shoelace, CSP-gaten, ruwe fouten in het leadformulier

De SSR-landingspagina importeert via `ProgressSteps` en `ProviderPickerButtons` alsnog een
Shoelace-component, dus Lit draait in Node bij elke render van `/` - precies wat de
CLAUDE.md-doctrine verbiedt, en drie comments beweren het tegendeel. **[delegeerbaar]**
Daarnaast toont het leadformulier de ruwe FastAPI-JSON als Nederlandse kopij, en blokkeert
de CSP downloads van consumenten-OneDrive (`*.files.1drv.com`). P1, size S–M.
Brief: [`briefs/68-landing-ssr-csp-and-error-surfaces.md`](briefs/68-landing-ssr-csp-and-error-surfaces.md)

**Klaar als:** `/` rendert met nul Shoelace-modules in de SSR-bundle, en leadform-fouten
tonen Nederlandse tekst bij 500/502/503.

### 71. Docs, CI en backlog-hygiëne

Drie dingen misleiden een nieuwe bijdrager vandaag: `CONTRIBUTING.md` linkt naar een
bestand dat niet in de repo zit, CI draait niet wat CONTRIBUTING voorschrijft (`mypy` geeft
3 fouten, `ruff format --check` 13 bestanden, frontend heeft geen lintstap), en de gearchiveerde
backlog-index (`done/backlog-README-2026-04.md`) beweert dat de Ollama-provider in-tree blijft
terwijl die weg is. **[delegeerbaar]**
Verder: `ARCHITECTURE.md` is grotendeels fictie, en `scripts/woo_contacts_named.csv` bevat
echte namen van ambtenaren in een publieke MIT-repo. P2, size S–M, vooral schrappen.
Brief: [`briefs/71-docs-ci-and-backlog-hygiene.md`](briefs/71-docs-ci-and-backlog-hygiene.md)

**Klaar als:** CI en CONTRIBUTING noemen exact dezelfde commandolijst en die is groen op
`main`, en `scripts/woo_contacts_named.csv` plus `tests/test-jsons/` zijn weg of aangesloten.

### 60. Client-side PDF-redactie: de laatste server-aanraking weg

Export is de enige plek waar documentbytes de browser verlaten. Dat is efemeer en goed
geaudit, maar het maakt de kernzin *"uw PDF verlaat nooit uw browser"* letterlijk onwaar.
Met mupdf.js (dezelfde engine als PyMuPDF, via dynamische import op het exportscherm) wordt
de claim wél letterlijk, inclusief echte tekstlaag-verwijdering plus een verplichte
post-redactie-extractietest voordat het bestand wordt afgegeven. P2, size M–L. De brief
adviseert dit ná de publieke launch te doen, als eerste post-launch winst.
Brief: [`briefs/60-client-side-export.md`](briefs/60-client-side-export.md)

**Klaar als:** een volledige review → export loopt zonder dat er PDF-bytes de browser
verlaten, en de extractietest slaagt op alle golden fixtures in CI.

### 63. `PUBLIC_API_URL` op runtime in plaats van build-time

De GHCR-images van v0.1.0 bakken `PUBLIC_API_URL` in de bundle, met `http://localhost:8000`
als default, dus een self-hoster op een eigen hostname moet alsnog zelf bouwen - wat de
belofte van versie-pinnen ondergraaft. **[delegeerbaar]** De fix is klein: van
`$env/static/public` naar `$env/dynamic/public` in `client.ts` en `export-service.ts`, en de
build-arg uit de Dockerfile. Status: uitvoeringsklaar. P2, size S.
Brief: [`briefs/63-frontend-runtime-api-url.md`](briefs/63-frontend-runtime-api-url.md)

**Klaar als:** `docker run -e PUBLIC_API_URL=https://example.org/api …` praat zonder rebuild
met dat adres, en een lege waarde valt terug op same-origin.

> **B · Launch-ready polish en self-host** - het restant van fase C: wat nog moet voordat
> woobuddy.nl publiek de deur uit kan.

### 39. Deployment: off-VPS backups, smoke test, auto-deploy

De hosted instance draait live op een Hetzner cx23 in Falkenstein via Caddy + docker-compose,
met TLS, EU-only hosting en een gescript handmatig deploy-pad. **[delegeerbaar]** Wat nog
ontbreekt is het vangnet: er is alleen `pgdata` op het VPS-volume, geen geplande `pg_dump`
naar elders, geen post-deploy smoke test, en dus ook geen veilige auto-deploy op push naar
`main`. Staging pas zinvol zodra auto-deploy landt. P2, size S.
Brief: [`briefs/39-deployment.md`](briefs/39-deployment.md)

**Klaar als:** er draait een geplande off-VPS backup van Postgres met een beschreven en
geteste restore-procedure.

### 46. Client-side conversie: afbeeldingen, .txt, .docx, .zip

Vandaag accepteert de uploadzone alleen PDF, terwijl echte Woo-verzoeken binnenkomen als
mengsels van Word-concepten, gescande brieven en zip-bundels. **[delegeerbaar]** Alles blijft
in de browser (pdf-lib, mammoth, pdfmake, jszip): geen serverroute, geen LibreOffice. De
prijs is fideliteit, en die wordt afgedekt met een verplicht verificatiescherm ("dit is wat
WOO Buddy gaat redigeren - klopt dit met het origineel?"). Harde eis: elke geproduceerde PDF
heeft een selecteerbare tekstlaag, anders breekt detectie stil. P1, size L.
Brief: [`briefs/46-convert-to-pdf-ingestion.md`](briefs/46-convert-to-pdf-ingestion.md)

**Klaar als:** een `.docx`, `.txt`, afbeelding of `.zip` leidt via het verificatiescherm naar
een werkende reviewsessie, met een netwerk-isolatietest die nul uitgaande requests aantoont.

### 47. Client-side e-mail- en .msg-ingestie met thread-stitching

E-mail is het grootste bulkformaat in Woo-verzoeken, en de reviewer wil een thread als één
doorlopend document lezen en lakken, niet 87 losse sessies. **[delegeerbaar na #46]**
`postal-mime` en `msgreader` parsen in de browser; berichten worden op `Date:` gesorteerd en
met `pdf-lib` aan elkaar geplakt. Bijzonder: HTML-weergave is standaard uit, en ook áán
worden externe URL's herschreven vóór enige parser ze ziet, zodat tracking pixels nooit
afgaan. Deelt de conversie-infrastructuur en het verificatiescherm van #46. P1, size M.
Brief: [`briefs/47-email-msg-ingestion.md`](briefs/47-email-msg-ingestion.md)

**Klaar als:** tien `.eml`-bestanden in thread-modus leveren één chronologische PDF met
selecteerbare tekst op, en de netwerk-isolatietest blijft nul, ook met HTML-weergave aan.

### 69. Reviewscherm: O(N²)-paden, bulk-IDB-writes, toetsenbord- en a11y-gaten

Op documenten met 200+ detecties is het scherm merkbaar traag: `DetectionList` roept per rij
`sameNameCount()` aan (die de hele lijst scant), en bulk-accept doet per rij een volledige
IndexedDB read-modify-write. **[delegeerbaar]** Daarnaast staan er interactieve
`<sl-button>`s in `<button>`-kaarten (ongeldige HTML, kapotte taborde), zijn de
PDF-overlays `div`s zonder rol of tabindex, en blijft de re-attach-filepicker hangen bij
annuleren. P2, size M.
Brief: [`briefs/69-review-perf-and-a11y.md`](briefs/69-review-perf-and-a11y.md)

**Klaar als:** bulk-accept van 200 Tier-1-rijen doet één IDB-write en elk overlay-vlak is met
het toetsenbord bereikbaar en activeerbaar.

### 70. Structuurconsolidatie: reviewpagina, stores, dubbele helpers, dode DB-laag

`routes/review/[docId]/+page.svelte` is 1305 regels en bevat toolbar, banners, sidebar,
statusbalk, sessie-bootstrap en toetsenbordlijm door elkaar; de brief snijdt dat in 4–5 PR's
van elk onder ~400 regels. **[delegeerbaar behalve E]** Daarnaast staan er negen
hand-gerolde kopieën van bestaande helpers (waaronder de accept-predicaat uit #66) en drie
naamvarianten voor dezelfde actie. Sectie E is een productbeslissing: geen enkele route
raakt de database, maar `main.py` draait wel 7 `ALTER TABLE` bij elke boot en CI start een
Postgres voor tests die er niets mee doen. P2, size L.
Brief: [`briefs/70-structure-consolidation.md`](briefs/70-structure-consolidation.md)

**Klaar als:** `+page.svelte` is onder de 400 regels, elke rij in de duplicatentabel leest
N/0, en het besluit over de DB-laag staat vastgelegd in de brief én in `docker-compose.yml`.

> **C · Poort: publieke launch en meten** - geen werkitem, een besluitmoment. Deploy naar
> productie, zachte launch via het eigen netwerk, en meten in Plausible: gestarte uploads,
> geopende voorbeelddocumenten, voltooide exports, aanmeldingen. Daarna de vraag: is er
> genoeg signaal (terugkerende gebruikers, teamleiders die bellen, "mijn collega's hebben
> dit ook nodig") om multi-user te bouwen? Zo nee: doorwerken aan detectiekwaliteit, UX,
> voorbeelden en marketing - of stoppen.
> **Begin niet aan blok D vóór deze poort.** Speculatief auth + organisaties bouwen is de
> grootste manier om weken aan dit project te verspillen.

> **D · Teamfeatures, pas na signaal** - volgorde volgt de echte afhankelijkheidsketen:
> auth → organisaties → rollen → leden.

### 32. Authenticatie (Better Auth)

De app heeft geen gebruikersmodel: `reviewed_by` is vrije tekst, er zijn geen sessies. Better
Auth is de keuze omdat het zijn eigen database gebruikt (geen externe authdienst, belangrijk
voor overheidsvertrouwen), Svelte 5 first-class ondersteunt en de organisatie-plugin voor #33
meelevert. De harde randvoorwaarde: `/` en `/review/[docId]` blijven volledig werken zónder
account. De inlogpoort staat op `/app/*`, dus op persistentie en teamfeatures, nooit op de
reviewloop zelf. P0 zodra de poort open is, size L.
Brief: [`briefs/32-authentication.md`](briefs/32-authentication.md)

**Klaar als:** een nieuwe gebruiker kan zich registreren, verifiëren en inloggen, `/app/*`
redirect zonder sessie, en de anonieme uploadflow werkt onveranderd en zonder persistentie.

### 33. Organisaties en data-scoping

Zonder organisatie is er geen eigendomsgrens en zweeft alles in een gedeelde ruimte. Elke
query die gebruikersdata raakt moet op `organization_id` filteren; dat is de belangrijkste
beveiligingsinvariant van een multi-tenant SaaS. Onder de client-first-architectuur geldt de
scoping alleen voor metadata (bbox, artikel, status), nooit voor documentinhoud. Deze brief
is geschreven tegen de oude multi-document-vorm en wordt volgens #53 vervangen door het
dossier-ontwerpdoc. P0 zodra getriggerd, size L.
Brief: [`briefs/33-organizations.md`](briefs/33-organizations.md)

**Klaar als:** een gebruiker in organisatie A kan niets van organisatie B zien, en
`detections` bevat geen `entity_text` en `documents` geen MinIO-verwijzing meer.

### 34. Rollen en rechten

Vier rollen via de organisatie-plugin van Better Auth: `owner` (inclusief facturatie),
`admin`, `reviewer` (dossiers en detecties, geen goedkeuring of ledenbeheer) en `viewer`
(alleen lezen). Geen eigen RBAC-systeem bouwen. De frontend verbergt wat een rol niet mag,
maar de handhaving hoort in de backend. P1, size M, hangt aan #33.
Brief: [`briefs/34-roles-permissions.md`](briefs/34-roles-permissions.md)

**Klaar als:** de backend weigert een niet-toegestane actie met een 403, niet alleen met
verborgen UI.

### 36. Ledenbeheer en uitnodigingen

Echte Woo-processen lopen via meerdere mensen: de reviewer, een jurist die meekijkt, een
leidinggevende die tekent. Dit is de uitnodigingsflow op `/app/org/members`: e-mailadres plus
rol, Better Auth doet de levenscyclus (pending → accepted), en de ontvanger landt na
accountaanmaak in de juiste organisatie. Nederlandse mailtemplate. P2, size M, hangt aan #33
en #34.
Brief: [`briefs/36-member-management.md`](briefs/36-member-management.md)

**Klaar als:** een uitgenodigde collega krijgt een mail, maakt een account en landt in de
juiste organisatie met de juiste rol, en de laatste owner kan niet verwijderd worden.

### 53. Dossier- en multi-document-modus (spike + eerste slice)

Een echt Woo-besluit beslaat tientallen tot honderden documenten die als één dossier horen:
zelfde verzoek, zelfde grondenstelsel, dezelfde namen. Alles waar teams voor betalen (dedup,
naampropagatie, batch-goedkeuring, dossier-audit) hangt aan die eenheid. Dit item dwingt de
herschrijving af als bewuste architectuurbeslissing: eerst een ontwerpdoc
(`docs/design/dossier-mode.md`) over datamodel, IndexedDB-vorm, routes en server-API, dan
drie slices achter een feature flag. P1 zodra getriggerd, size XL.
Brief: [`briefs/53-dossier-multi-document-mode.md`](briefs/53-dossier-multi-document-mode.md)

**Klaar als:** het ontwerpdoc ligt er en slices A–C zijn gemerged achter een feature flag,
terwijl het anonieme single-document-pad ongewijzigd blijft werken.

> **E · Draft-workflow en exportverrijking, pas voor betalende pilots** - alles hier
> veronderstelt een multi-user model: goedkeuringspoorten, juristopmerkingen,
> her-export-audits. Een solo-gebruiker exporteert gewoon als hij klaar is. Bouw niets
> hiervan voordat blok D staat én een teampilot erom vraagt.

### 25. Documentlevenscyclus (concept / goedkeuren / heropenen)

Vandaag gaat een document van "review" rechtstreeks naar "geëxporteerd", zonder formele
goedkeuring. De brief voegt `draft` toe tussen review en approved, met een
volledigheidscheck bij goedkeuren en een heropen-pad met auditregel. **Herschrijven vóór
uitvoering:** de brief leunt op een server-side `status` op een rij die niets meer schrijft
(zie #71) - eerst client-side herformuleren of laten vallen. P2, size M.
Brief: [`briefs/25-document-lifecycle.md`](briefs/25-document-lifecycle.md)

**Klaar als:** een document doorloopt de volledige levenscyclus en kan niet goedgekeurd
worden zolang er detecties openstaan, met een dialoog die precies benoemt wat nog open is.

### 26. Conceptvoorbeeld en naast-elkaar-weergave

Voor goedkeuring wil de reviewer (of zijn leidinggevende) zien hoe het gelakte document er
straks uitziet: zwarte vlakken met de artikelcode erin, live meebewegend met elke beslissing.
Volledig client-side, want de server heeft de PDF niet. **Herschrijven vóór uitvoering:** de
routes `/app/dossier/[id]/…` in de brief bestaan niet (zie #71). P2, size M, hangt aan #25.
Brief: [`briefs/26-draft-preview.md`](briefs/26-draft-preview.md)

**Klaar als:** het conceptvoorbeeld toont zwarte balken op alle geaccepteerde detecties en
werkt direct bij als een beslissing verandert; naast-elkaar scrollt gesynchroniseerd.

### 27. Opmerkingen op het concept

Ondersteunt de gangbare werkwijze waarin een jurist het concept nakijkt en notities
achterlaat zonder zelf beslissingen te wijzigen. Opmerkingen verwijzen naar een detectie-id,
niet naar geciteerde tekst, dus server-side opslag is verdedigbaar. **Herschrijven of laten
vallen:** `draft_comments` hangt aan server-side detectie-id's die er na #50 niet meer zijn
(zie #71). P3, size M, hangt aan #26 en #32.
Brief: [`briefs/27-draft-comments.md`](briefs/27-draft-comments.md)

**Klaar als:** een jurist plaatst een opmerking op een specifieke redactie, de reviewer lost
'm op, en een openstaande opmerking blokkeert goedkeuring.

### 28. Exportversies en her-export

Woo-behandeling is iteratief: na export kan een besluit worden aangevochten. Zonder versies
is er geen spoor van wat wanneer is gepubliceerd. Onder client-first bewaren we alleen
export-metadata (versienummer, tijdstip, wie, detectie-snapshot), nooit het bestand.
**Herschrijven vóór uitvoering:** de brief gaat uit van een `exports`-tabel en een verwijderde
`/api/documents/{id}/export`-route (zie #71). P2, size M.
Brief: [`briefs/28-export-versioning.md`](briefs/28-export-versioning.md)

**Klaar als:** her-exporteren maakt versie 2 aan, markeert versie 1 als verouderd, en de
wijzigingssamenvatting benoemt toevoegingen, verwijderingen en aanpassingen correct.

### 29. Conceptexport met watermerk

Een conceptexport moet visueel niet te verwarren zijn met de definitieve versie, anders wordt
er ooit een half afgerond document gepubliceerd. Diagonaal "CONCEPT - Niet definitief" in
lichtgrijs, in dezelfde in-memory pass als de redactie, dus zonder extra schijf-I/O.
Definitief is alleen beschikbaar voor goedgekeurde documenten. P2, size S. Dit is het enige
item in dit blok dat naar blok B mag verhuizen als een pilotreviewer erom vraagt.
Brief: [`briefs/29-concept-export.md`](briefs/29-concept-export.md)

**Klaar als:** de conceptexport draagt op elke pagina een zichtbaar watermerk en de
definitieve export heeft er geen, en is alleen te kiezen bij goedgekeurde documenten.

### 30. Lakkaart genereren

Een lakkaart is het interne spiegelbeeld van de export: het originele document met gekleurde
overlays in plaats van zwarte balken, geannoteerd met detectie-id en artikelcode. Handig voor
auditverificatie en om zelf te controleren of de lakking klopt. Kleur per Woo-artikel. Kan als
extra bestand uit de efemere exportstap komen, of volledig client-side op het pdf.js-canvas.
P3, size M.
Brief: [`briefs/30-redaction-map.md`](briefs/30-redaction-map.md)

**Klaar als:** de lakkaart toont de originele inhoud met gekleurde annotaties, elk met
artikelcode en detectie-id, en de kleuren zijn per artikel consistent binnen het document.

### 31. Lakregistratie als CSV/XLSX

Een machineleesbaar overzicht van alle lakbesluiten, bruikbaar voor audit, rapportage en
andere systemen: het lakregister in draagbare vorm. Client-side genereren heeft de voorkeur,
want alleen daar kan eventueel de entiteittekst uit de lokale PDF worden meegenomen.
**Inkorten vóór uitvoering:** ongeveer 70% is al gebouwd (`diwoo/csv.ts`, gebundeld in
`onderbouwing/bundle.ts`) - wat rest is XLSX plus een knop op de logpagina (zie #71). P3,
size S.
Brief: [`briefs/31-redaction-inventory.md`](briefs/31-redaction-inventory.md)

**Klaar als:** vanaf de lakregistratiepagina is een CSV en een XLSX te downloaden met alle
kolommen correct gevuld.

### 54. Dubbele documenten binnen een dossier herkennen

Een Woo-besluit bevat vaak dezelfde e-mailthread als bijlage bij twintig documenten. Alles
opnieuw beoordelen is verspilling, en elke serieuze concurrent opent juist met "we vonden 40%
duplicaten". Client-first: hashen gebeurt in de browser (SHA-256 per document, tekst-hash per
pagina, MinHash voor bijna-identiek), opslag in IndexedDB, niets naar de server. De reviewer
kan een cluster verbergen of de redacties van één document over het cluster uitrollen. P2,
size M, hangt aan #53.
Brief: [`briefs/54-cross-document-deduplication.md`](briefs/54-cross-document-deduplication.md)

**Klaar als:** een dossier met exacte én bijna-identieke documenten levert de verwachte
clusters op, volledig in de browser berekend (netwerk-isolatietest).

### 55. Naambesluiten door het hele dossier laten gelden

Het meest voorkomende Woo-verzoek is "alle correspondentie van persoon X", en dus staat
dezelfde naam in elk document. Nu bevestigt de reviewer Jan Jansen veertig keer. Dit item
tilt het per-document-woordenlijstidee van #21 naar dossierniveau: een besluit met
`scope: 'all'` wordt op alle al geanalyseerde documenten herhaald en automatisch toegepast op
documenten die later worden geanalyseerd, met een per-document-override voor het zeldzame
geval van naamgenoten. P2, size M, hangt aan #53.
Brief: [`briefs/55-cross-document-name-propagation.md`](briefs/55-cross-document-name-propagation.md)

**Klaar als:** de reviewer bevestigt een naam één keer in een dossier van 40 documenten en
ziet die naam in alle 40 voorbevestigd staan.

### 56. Belanghebbenden raadplegen (Woo art. 4.4)

Artikel 4.4 verplicht het bestuursorgaan om derden een zienswijze te laten geven voordat
informatie over hen wordt gepubliceerd. Zonder gereedschap is dat knip- en plakwerk in de
mail. Dit item geeft het dossier een belanghebbenden-lijst, koppelt passages aan een partij,
genereert een raadpleegpakket (passage-extract plus Nederlandse begeleidende brief met
reactietermijn), en legt de reactie vast. Publicatie is geblokkeerd zolang iemand nog moet
reageren, tenzij onderbouwd overruled. P2, size M.
Brief: [`briefs/56-belanghebbenden-consultation.md`](briefs/56-belanghebbenden-consultation.md)

**Klaar als:** een dossier kan niet naar `ready_for_publication` zolang een belanghebbende op
antwoord wacht, behalve met een vastgelegde onderbouwing.

### 57. Gedeelde lijst publieke functionarissen per organisatie

#13 levert de generieke functietitels en #17 de lijst per document, maar elke gemeente heeft
eigen namen: het college van Utrecht is Sharon Dijksma plus zeven wethouders, en die wil de
reviewer niet elke keer opnieuw invoeren. OpenRaadsinformatie dekt de meeste gemeenten als
open dataset; een dagelijkse achtergrondjob houdt de lijst vers, met handmatige CSV-import als
terugvaloptie. Geen scraping in het hete pad. Dit is een Team-tier-onderscheider. P2, size M.
Brief: [`briefs/57-public-official-registry-sync.md`](briefs/57-public-official-registry-sync.md)

**Klaar als:** een organisatie ziet, bewerkt en ververst haar eigen lijst, en die lijst werkt
automatisch door in de review van elke reviewer in die organisatie.

### 58. Woo-jaarverslag en rapportagedashboard

Gemeenten moeten jaarlijks een Woo-jaarverslag publiceren met cijfers, en die komen nu uit het
zaaksysteem zonder enig zicht op wat er in de lakstap gebeurde. Een dashboard met aantallen
per tier, meest aangehaalde weigeringsgronden en de verhouding voorgesteld/bevestigd/afgewezen
maakt van de tool een jaarlijks ritueel. **Let op:** de databaseparagraaf in de brief leunt op
`RedactionLogEntry`- en `Dossier`-tabellen die niet bestaan (zie #71). P3, size M.
Brief: [`briefs/58-woo-jaarverslag-dashboard.md`](briefs/58-woo-jaarverslag-dashboard.md)

**Klaar als:** een admin ziet een jaaroverzicht van de lakactiviteit van zijn organisatie en
kan dat exporteren als CSV en als PDF, zonder dat er ooit entiteittekst in een grafiek belandt.

> **F · Monetisatie, pas na handmatige facturen** - integreer geen betaalprovider voordat
> iemand zegt "stuur maar een factuur". Eén tot drie handmatige facturen leren meer over de
> dealvorm dan Mollie.

### 37. Mollie-facturatie

Mollie is de juiste provider voor een Nederlandse overheidstool: Europees, AVG-native, iDEAL.
De tierladder staat vast: self-host gratis (MIT), hosted Gratis zonder aanmeldmuur en zonder
documentlimiet, Team rond €79–€99 per organisatie per maand (multi-user, gedeelde
woordenlijsten, auditlog, SSO, DPA), Enterprise op maat. Het harde principe: facturatie hekt
teamfeatures af, nooit de reviewloop, en prijzen blijven configureerbaar. P2, size XL, hangt
aan #32 en #33.
Brief: [`briefs/37-mollie-billing.md`](briefs/37-mollie-billing.md)

**Klaar als:** een organisatie upgradet van Gratis naar Team via Mollie-checkout, terwijl
anonieme en Gratis-gebruikers onbeperkt kunnen analyseren en exporteren.

### 38. Transactionele e-mail

Better Auth heeft mail nodig voor verificatie, wachtwoordherstel en uitnodigingen; facturatie
voor bonnen en mislukte betalingen. Zeven Nederlandse templates, HTML met platte-tekst-variant,
functioneel en zonder marketing. **Inkorten vóór uitvoering:** de brief stelt Resend of
Nodemailer voor, terwijl Scaleway TEM en Listmonk al gebouwd zijn op de nog ongemergde branch
`feat/brevo-to-listmonk` - wat rest is de templateset (zie #71). P2, size M.
Brief: [`briefs/38-email-service.md`](briefs/38-email-service.md)

**Klaar als:** alle auth- en facturatiemails komen betrouwbaar aan en renderen correct in
Outlook en Gmail.

### 42. Microsoft-SSO en 2FA

Veel Nederlandse ambtenaren hebben een Microsoft 365-account, dus "Inloggen met Microsoft"
haalt merkbare drempel weg; 2FA voegt een vertrouwenslaag toe die bij overheidsgereedschap
telt. Beide zijn onderscheiders, geen launch-blokkers. Azure AD multi-tenant via het
`common`-endpoint, TOTP via de 2FA-plugin van Better Auth. De volwaardige SSO-plugin voor
enterprise blijft "alleen evalueren" tot een klant erom vraagt. P3, size M, hangt aan #32.
Brief: [`briefs/42-sso-2fa.md`](briefs/42-sso-2fa.md)

**Klaar als:** inloggen met een Microsoft-account werkt inclusief koppeling aan een bestaand
account op hetzelfde e-mailadres, en 2FA is instelbaar en wordt bij inloggen afgedwongen.

### 59. Zaaksysteem-koppelingen (architectuurspike)

Woo-verzoeken ontstaan niet in WOO Buddy maar in Djuma, Decos JOIN, Corsa, Centric of
OpenZaak, en het heen-en-weer downloaden en uploaden is precies de wrijving waarop grote
gemeenten voor een gevestigde partij kiezen. Koppelingen zijn een groeihefboom, geen product:
eerst een plugin-architectuur met OpenZaak als referentie (CORS-vriendelijk, dus client-first),
daarna één koppeling per betalende pilot. De server-proxy voor legacy-systemen is een
geauditeerde uitzondering, geïsoleerd in een eigen module. P3, size L + M per koppeling.
Brief: [`briefs/59-zaaksysteem-connectors.md`](briefs/59-zaaksysteem-connectors.md)

**Klaar als:** de plugin-architectuur staat gedocumenteerd met een werkende
OpenZaak-referentie die documenten ophaalt en het gelakte resultaat terugzet, achter een
per-organisatie feature flag.

### 61. Publiceren naar open.overheid.nl (GPP-publicatiebank)

#52 levert al een DiWoo/TOOI-bundel; dit is de laatste stap: met één klik publiceren naar de
publicatiebank van de organisatie. Dat draait de framing van "wij helpen reviewers sneller
lakken" naar "wij zorgen dat burgers eerder inzicht krijgen". De ontwerpbeperking is hard: de
browser praat rechtstreeks met de publicatiebank van de klant, nooit via een WOO
Buddy-server, want dat zou ons een doorgeefluik voor documentinhoud maken. P3, size L, hangt
aan #52.
Brief: [`briefs/61-open-overheid-direct-publish.md`](briefs/61-open-overheid-direct-publish.md)

**Klaar als:** een reviewer publiceert document plus metadata in één klik, en netwerkinspectie
bevestigt dat de gelakte PDF geen enkele WOO Buddy-server passeert.

## Recently done

- **2026-04-28 · #65** Tagged PDF + bookmarks voor het onderbouwingsrapport (PDF/UA-1).
- **2026-04-28 · #64** Onderbouwingsrapport-export als bijlage bij het Woo-besluit.
- **2026-04-28 · #50** Anonieme analyse zonder serverpersistentie (administratief gesloten 2026-09-02).
- **2026-04-26 · #48** Toegankelijke PDF-export (lang-tag, XMP, alt-tekst, PDF/A-2b).
- **2026-04-26 · #52** DiWoo/TOOI-publicatiemetadata-export.
