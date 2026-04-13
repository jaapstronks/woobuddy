# Woo-redactietool: waarom een slimme interface zonder AI-taalmodel de betere keuze is

## Achtergrond

Bij het afhandelen van Woo-verzoeken (Wet open overheid) moeten gemeenten documenten doorlopen en privacy- en beleidsgevoelige passages zwartlakken. Denk aan BSN-nummers, namen, e-mailadressen, maar ook aan persoonlijke beleidsopvattingen en strategische overwegingen.

Dit is tijdrovend, foutgevoelig en saai werk. Een softwaretool die dit versnelt heeft duidelijke waarde. De vraag is: hoe bouw je die tool?

De voor de hand liggende gedachte is om er een AI-taalmodel (LLM) in te stoppen — een systeem zoals ChatGPT of Google's Gemma — dat documenten "begrijpt" en automatisch gevoelige passages herkent. Maar na analyse denken we dat een tool **zonder** taalmodel niet alleen goed genoeg is, maar zelfs beter verkoopbaar en bruikbaarder.

Dit document legt uit waarom.

---

## Wat moet er zwartgelakt worden?

De Woo (artikelen 5.1 en 5.2) kent diverse uitzonderingsgronden. Ruwweg zijn er twee categorieën:

### Categorie 1: Herkenbare patronen

Dit zijn gegevens met een vast formaat:

- **BSN-nummers** — altijd 9 cijfers, met een wiskundige controle (elfproef)
- **Telefoonnummers** — 06-12345678, +31 6 1234 5678, etc.
- **E-mailadressen** — jan.jansen@gemeente.nl
- **IBAN-nummers** — NL91 ABNA 0417 1643 00
- **Postcodes** — 3511 AB
- **Kentekens** — AB-123-CD
- **KvK-nummers**, **BTW-nummers**

Daarnaast zijn er gegevens die je kunt herkennen aan de context waarin ze staan:

- **Namen** — vaak voorafgegaan door "de heer", "mevrouw", of te vinden in aanhef/ondertekening van e-mails
- **Functietitels** — "beleidsmedewerker", "juridisch adviseur", "teamleider handhaving"
- **E-mailheaders** — alles in Van/Aan/CC-velden
- **Handtekeningblokken** — het blok na "Met vriendelijke groet" onderaan e-mails

### Categorie 2: Inhoudelijke beoordeling

Dit zijn passages die je alleen kunt herkennen als je de *betekenis* begrijpt:

- **Persoonlijke beleidsopvattingen** (art. 5.2) — een ambtenaar die in een interne mail schrijft "ik vind dat we dit niet moeten doen"
- **Onevenredige benadeling** (art. 5.1 lid 5) — onderhandelingsposities, strategische overwegingen
- **Belang van de staat** (art. 5.1 lid 1) — internationale betrekkingen, veiligheid
- **Opsporing en vervolging** — lopende onderzoeken

Voor categorie 2 is altijd een menselijke reviewer nodig. Geen enkele software — ook geen AI — kan deze beoordeling betrouwbaar overnemen.

---

## Wat is regex en hoe werkt automatische detectie?

"Regex" staat voor *regular expressions*: een manier om tekstpatronen te beschrijven zodat software ze automatisch kan herkennen. Een paar voorbeelden:

| Wat je zoekt | Patroon (versimpeld) | Voorbeeld |
|---|---|---|
| BSN-nummer | 9 cijfers op een rij | 123456789 |
| E-mailadres | tekst @ tekst . tekst | j.jansen@gemeente.nl |
| Postcode | 4 cijfers + 2 letters | 3511 AB |
| Telefoonnummer | 06 + 8 cijfers | 06-12345678 |
| IBAN | NL + 2 cijfers + 4 letters + 10 cijfers | NL91ABNA0417164300 |

Dit klinkt simpel, en dat is het in de basis ook. Het mooie is: deze patronen zijn *betrouwbaar*. Een BSN-nummer ziet er altijd hetzelfde uit. Een e-mailadres heeft altijd een @-teken. Er is geen interpretatie nodig.

Naast regex kun je werken met **woordenlijsten**: een lijst van alle Nederlandse voornamen (beschikbaar via het Meertens Instituut en CBS), een lijst van veelvoorkomende achternamen, een lijst van functietitels. Software doorzoekt het document en markeert elk woord dat op zo'n lijst staat.

Met de combinatie van regex-patronen, woordenlijsten en structuurherkenning (zoals e-mailheaders en handtekeningblokken) kun je naar schatting **70-80% van alle te lakken passages** automatisch detecteren. En die 70-80% is precies het saaiste, meest repetitieve deel van het werk.

---

## Wat zou een AI-taalmodel toevoegen?

Een taalmodel zoals Google's Gemma (dat je zelf kunt hosten) zou de detectie kunnen verbeteren. Het begrijpt context: het herkent "Van der Berg" als naam ook zonder dat er "mevrouw" voor staat. Het kan het verschil zien tussen "De Bilt" als plaatsnaam en "de Bilt" als mogelijke persoonsnaam.

Realistisch brengt een taalmodel de detectie van ~75% naar ~85-90%. Dat klinkt als een flinke verbetering, maar er zijn kanttekeningen:

1. **Die extra 10-15% zit in een grijs gebied.** De passages die regex mist maar een LLM wel vindt, zijn juist de gevallen waar de reviewer het resultaat toch moet controleren. De tijdswinst is beperkt.

2. **De echt moeilijke 10-15% blijft mensenwerk.** Persoonlijke beleidsopvattingen, strategische afwegingen — daar is zelfs het beste taalmodel onbetrouwbaar op. De reviewer moet die passages hoe dan ook zelf beoordelen.

3. **De grootste tijdswinst zit in de stap van 0% naar 75%.** Het verschil tussen handmatig alle BSN's zoeken en ze automatisch gemarkeerd krijgen is enorm. Het verschil tussen 75% en 90% automatische detectie is relatief klein, omdat handmatige controle sowieso nodig blijft.

---

## Waarom een slimme interface méér waarde heeft dan een slimmer model

De echte versnelling voor Woo-medewerkers zit niet in perfecte detectie, maar in een **workflow die het reviewproces structureert**. Denk aan:

### Gestructureerd reviewen
- Per pagina afvinken: "deze pagina is gecontroleerd"
- Per document aangeven welke categorieën gevoelige informatie erin voorkomen
- Voortgangsindicator: 47 van 200 documenten beoordeeld

### Slim lakken
- Alle gevonden BSN's in het hele document met één klik lakken
- Per markering bevestigen of afwijzen
- Eigen zoektermen toevoegen die specifiek zijn voor dit Woo-verzoek (bijvoorbeeld een bedrijfsnaam of projectnaam die in alle documenten terugkomt)

### Audit trail
Dit is misschien wel de belangrijkste feature. Gemeenten moeten bij elk Woo-besluit per gelakte passage motiveren welke uitzonderingsgrond ze gebruiken. Als de tool dit faciliteert — "deze passage is gelakt op grond van art. 5.1 lid 2 sub e (persoonlijke levenssfeer)" — en dat exporteert naar het besluit, bespaar je uren aan administratief werk dat nu handmatig gebeurt.

### Bulkverwerking
Een Woo-verzoek kan honderden documenten omvatten. De mogelijkheid om patronen in bulk toe te passen en per document de status bij te houden is op zichzelf al een enorme versnelling.

---

## Het verkoopargument: privacy en eenvoud

Hier wordt het verschil tussen de twee varianten het scherpst.

### Zonder taalmodel: volledig in de browser

Een tool die alleen regex en woordenlijsten gebruikt, kan volledig in de webbrowser draaien. Dat betekent:

- **Er verlaat geen enkel document de werkplek.** Alles wordt lokaal verwerkt in de browser van de medewerker.
- **Geen verwerkersovereenkomst nodig.** Er worden geen persoonsgegevens gedeeld met een externe partij.
- **Geen IT-afdeling nodig voor installatie.** Open de browser, ga naar de URL, klaar.
- **Werkt offline.** Handig voor medewerkers die in beveiligde omgevingen werken.

Dit is een verhaal dat een CISO (beveiligingsverantwoordelijke), een FG (functionaris gegevensbescherming) en een inkoper allemaal in één zin begrijpen: *"Uw documenten verlaten nooit uw computer."*

### Met taalmodel: direct complexiteit

Zodra je een taalmodel toevoegt, krijg je te maken met:

- **Hosting**: het model moet ergens draaien — op een server (van wie?) of lokaal bij de gemeente (wie beheert dat?)
- **Privacy**: documenten moeten naar het model gestuurd worden, al is het maar tijdelijk in het geheugen. Dat vereist een verwerkersovereenkomst en een DPIA.
- **Hardware**: een taalmodel als Gemma 27B vereist een GPU-server. Dat is kosten, beheer en afhankelijkheid.
- **Uitleg**: bij elke demo en elk inkoopgesprek moet je uitleggen hoe het model werkt, waar data naartoe gaat, wie er toegang heeft. Dat kost tijd en vertrouwen.

De meerwaarde van het taalmodel (10-15% betere detectie) weegt niet op tegen de drempels die het opwerpt in verkoop, inkoop en implementatie.

---

## Voorstel: twee fasen

### Fase 1 — Browser-only tool (nu bouwen)

Een webapplicatie die volledig client-side draait:

- Regex-detectie voor BSN, IBAN, e-mail, telefoon, postcode, kenteken, KvK, BTW
- Naamherkenning via voornamen- en achternamenlijsten
- Structuurherkenning voor e-mailheaders en handtekeningblokken
- Reviewinterface met per-pagina controle, audit trail en bulkacties
- Export naar gelakt PDF met onderbouwing per passage

Dit is verkoopbaar, deploybaar en bruikbaar vanaf dag één.

### Fase 2 — Optionele AI-laag (later, als de markt erom vraagt)

Als browser-gebaseerde AI (WebGPU) volwassen genoeg wordt om kleinere taalmodellen lokaal te draaien zonder server, kan dit als optionele laag worden toegevoegd — zonder het privacyverhaal te doorbreken. Tot die tijd is de regex+UX-variant de sterkere propositie.

---

## Samenvatting

| | Zonder taalmodel | Met taalmodel |
|---|---|---|
| Detectie | ~75-80% | ~85-90% |
| Privacy | Volledig lokaal in browser | Vereist server of lokale GPU |
| Installatie | URL openen | IT-afdeling betrekken |
| Verwerkersovereenkomst | Niet nodig | Wel nodig |
| Verkoopgesprek | "Data verlaat nooit uw computer" | "Laat me uitleggen hoe we uw data beschermen..." |
| Kosten voor gemeente | Licentie/abonnement | Licentie + hardware/hosting |
| Onderhoud | Minimaal | Model-updates, GPU-beheer |

De tool zonder taalmodel is niet een afgezwakte versie van de tool mét taalmodel. Het is een **bewuste keuze** voor een product dat makkelijker te bouwen, verkopen en gebruiken is — en dat het overgrote deel van de tijdswinst levert die er te halen valt.
