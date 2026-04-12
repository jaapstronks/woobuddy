# WOO Buddy — De Drietrapsraket

Het drie-lagen detectiemodel van WOO Buddy. Elke laag heeft een eigen detectiemethode, betrouwbaarheidsniveau en UX-patroon.

---

## Waarom drie lagen?

Niet alle lakbeslissingen zijn gelijk. Een BSN-nummer is altijd privacygevoelig — dat kan de computer zelf. Een persoonsnaam hangt af van de context — is het een burger of een wethouder? En de vraag of een passage een persoonlijke beleidsopvatting bevat, is een juridisch oordeel dat alleen een mens kan maken.

De drietrapsraket erkent dit verschil en past de automatisering aan per type:

| | Trap 1 | Trap 2 | Trap 3 |
|---|---|---|---|
| **Wat** | Harde identificatoren | Contextafhankelijke persoonsgegevens | Inhoudelijke beoordelingen |
| **Detectie** | Regex + validatie | NER + rolclassificatie | LLM-analyse |
| **Zekerheid** | >95% | 60-90% | 40-70% (niet als %) |
| **Standaard** | Auto-gelakt | Suggestie (gemarkeerd) | Annotatie (gesignaleerd) |
| **Actie reviewer** | Opt-out (ontlakken) | Eenkliks bevestigen/afwijzen | Volledige beoordeling met ondersteuning |
| **Motivering** | Automatisch | Semi-automatisch met sjabloon | Door reviewer geschreven met concept |

---

## Trap 1: Harde Identificatoren

**Principe:** Auto-lakken met opt-out.

### Wat wordt gedetecteerd

Data die met patroonherkenning en hoge zekerheid (>95%) te vinden is:

| Entiteit | Patroon | Validatie | Woo-artikel |
|----------|---------|-----------|-------------|
| BSN-nummers | 9 cijfers | 11-proef | 5.1.1e |
| IBAN-nummers | NL + 2 cijfers + 4 letters + 10 cijfers | Formaat | 5.1.2e |
| Telefoonnummers | Nederlandse mobiel/vast patronen | — | 5.1.2e |
| E-mailadressen | Standaard e-mailpatroon | — | 5.1.2e |
| Postcodes | 4 cijfers + 2 letters | — | 5.1.2e |
| Kentekens | Nederlandse kentekenpatronen | — | 5.1.2e |
| Creditcardnummers | Nummerpatroon | Luhn-check | 5.1.2e |
| Paspoort-/rijbewijsnummers | Patroonherkenning | — | 5.1.1e |

### Hoe het werkt

Regex-patronen met validatielogica. Geen LLM nodig. Detectie is snel en deterministisch.

### UX

- Bij het openen van het document zijn deze al **zwart gelakt**
- Elke zwarte balk toont een klein icoon voor het type identifier
- Het Woo-artikelnummer staat in de balk
- Eén klik om te **ontlakken** — voor uitzonderingssituaties (bijv. een IBAN van een publiek betaalaccount van een overheidsorgaan)
- Geen uitlegpaneel nodig — de motivering is triviaal en automatisch gegenereerd

### Gegenereerde motivering

Standaardtekst, direct bruikbaar in het Woo-besluit:

> "Het identificatienummer is gelakt op grond van art. 5.1 lid 1 sub e Woo."

---

## Trap 2: Contextafhankelijke Persoonsgegevens

**Principe:** Suggestie met eenkliks bevestiging.

### Wat wordt gedetecteerd

Data die via NER te vinden is, maar waar de lakbeslissing afhangt van context. Voornamelijk art. 5.1.2e en deels 5.1.1d.

**Namen — de grootste categorie:**

| Situatie | Actie |
|----------|-------|
| Namen van burgers | Bijna altijd lakken |
| Namen van ambtenaren die NIET in publieke hoedanigheid optreden | Lakken |
| Namen van bestuurders in publieke hoedanigheid (wethouders, directeuren, woordvoerders) | Vaak NIET lakken |
| Namen in mandaatbesluiten | NIET lakken |

**Overige entiteiten:**
- Straatadressen + huisnummers
- Bijzondere persoonsgegevens (medische informatie, diagnoses, medicijnnamen, etniciteit, religie, seksuele geaardheid, strafrechtelijke gegevens)
- Functietitels die herleidbaar zijn tot individuen bij kleine organisaties

### Hoe het werkt

1. **Deduce NER** als primaire detectie — gespecialiseerd in Nederlandse de-identificatie
2. **Rolclassificatie** — voor elke gedetecteerde naam:
   - Controleer de referentielijst van publieke functionarissen
   - Indien niet gevonden: optionele LLM-aanroep voor classificatie op basis van context
3. **Medische NER** — UMLS-terminologie en medicijnnamen voor bijzondere persoonsgegevens
4. **Herleibaarheidstoets** — beoordeelt of een functietitel + organisatienaam uniek naar een persoon leidt

### UX

- Gemarkeerde passages met een **gekleurde overlay** (NIET zwart — dat impliceert een definitieve beslissing)
- Inline label met de voorgestelde grond (bijv. chip: "5.1.2e — persoonsnaam burger")
- Betrouwbaarheidsindicator (hoog/gemiddeld/laag)
- **Eenkliks accepteren** (✓) of **afwijzen** (✗)
- Contextpaneel (bij hover of klik) met de redenering:
  > "Gedetecteerd als persoonsnaam. Niet gevonden in de lijst publieke functionarissen voor [organisatie]. Voorgestelde grond: art. 5.1.2e."

### Slimme functies

**Naampropagatie:** Wanneer de reviewer "J. de Vries" bij het eerste voorkomen als burger bevestigt, worden alle volgende vermeldingen van dezelfde naam automatisch geaccepteerd (met melding en undo-mogelijkheid).

**Rolgeheugen:** Geclassificeerde namen worden onthouden voor het hele dossier, niet alleen het huidige document.

**Referentielijst publieke functionarissen:** Een importeerbare CSV-lijst van namen die NIET gelakt moeten worden (college B&W, raadsleden, directeuren, woordvoerders). Per organisatie/dossier te uploaden.

### Gegenereerde motivering

Semi-automatisch met sjabloon:

> "De naam van betrokkene is gelakt ter bescherming van de persoonlijke levenssfeer (art. 5.1 lid 2 sub e Woo). Het belang van eerbiediging van de persoonlijke levenssfeer weegt in dit geval zwaarder dan het belang van openbaarmaking."

---

## Trap 3: Inhoudelijke Beoordelingen

**Principe:** Annotatie met beslisondersteuning. Het systeem verschuift van *detectie* naar *signalering*.

### Wat wordt geanalyseerd

Passages die een inhoudelijk oordeel vereisen dat niet volledig geautomatiseerd kan worden:

| Categorie | Woo-artikel | Signalen |
|-----------|-------------|----------|
| Persoonlijke beleidsopvattingen | 5.2 | "Ik adviseer...", "mijn inschatting is...", "het lijkt mij verstandig..." |
| Bedrijfsgegevens (concurrentiegevoelig) | 5.1.2f | Financiele data, omzetcijfers, klantenlijsten, strategiedocumenten |
| Inspectie en toezicht | 5.1.2d | Lopende inspecties, handhavingsstrategieen, controleplannen |
| Goed functioneren overheid | 5.1.2i | Interviewverslagen, integriteitsonderzoeken |
| Internationale betrekkingen | 5.1.2a | Diplomatieke communicatie, grensoverschrijdende samenwerking |
| Opsporing strafbare feiten | 5.1.2c | Verwijzingen naar lopende onderzoeken |
| Beveiliging | 5.1.2h | Beveiligingsdetails, toegangscodes |

### Hoe het werkt

Relevante passages (geselecteerd via documenttype-heuristieken en signaaltrefwoorden) worden naar de LLM gestuurd voor analyse. De LLM levert:

- Mogelijke toepasselijke gronden, gerangschikt op waarschijnlijkheid
- Een korte analyse waarom de passage is gesignaleerd
- Voor art. 5.2: een **feit-vs-mening classificatie per zin**
- Kwalitatieve labels — GEEN percentages

### UX

Het systeem presenteert een **analyse**, geen lakvoorstel.

**Geen betrouwbaarheidspercentages** — die zijn misleidend bij dit type beoordeling. In plaats daarvan kwalitatieve labels:
- "Mogelijk persoonlijke beleidsopvatting"
- "Bevat mogelijk concurrentiegevoelige informatie"

**Het beslispaneel toont:**

1. Mogelijke gronden, gerangschikt op waarschijnlijkheid
2. Analysetekst met uitleg waarom de passage is gesignaleerd
3. Voor art. 5.2: **feit-vs-mening indicator** per zin
   - "Deze zin bevat een feitelijke constatering over het budget"
   - "Deze zin bevat een waardeoordeel over de wenselijkheid van het plan"
   - "Deze passage bevat zowel feiten als meningen — overweeg alleen de subjectieve delen te lakken"
4. De relevante wettekst (inklapbaar)
5. Voor relatieve gronden: een **checklist voor de belangenafweging**
6. Drie beslisknoppen:
   - **Lakken** — reviewer kiest de grond
   - **Niet lakken** — reviewer noteert waarom
   - **Uitstellen** — voor beoordeling door collega of jurist

### Art. 5.2 — Het feit-vs-mening probleem

Dit is de moeilijkste beoordeling in het hele Woo-proces. De wet is helder:

- **Feiten**, **prognoses**, **beleidsalternatieven** en **objectief te duiden uitspraken** zijn expliciet GEEN persoonlijke beleidsopvattingen en mogen NIET worden gelakt onder art. 5.2
- Bij formele bestuurlijke besluitvorming moeten persoonlijke beleidsopvattingen in **geanonimiseerde vorm** worden verstrekt

De LLM classificeert per zin:

| Classificatie | Voorbeeld | Lakbaar onder 5.2? |
|---------------|-----------|---------------------|
| Feit | "Het budget bedraagt EUR 2M" | Nee |
| Prognose | "De verwachte kosten zijn EUR 3M" | Nee |
| Beleidsalternatief | "Optie A kost EUR 2M, optie B kost EUR 3M" | Nee |
| Persoonlijke beleidsopvatting | "Ik adviseer om optie B te kiezen vanwege de betere kwaliteit" | Ja (met anonimisering) |
| Gemengd | "Het budget is EUR 2M en ik vind dat onvoldoende" | Gedeeltelijk — alleen het subjectieve deel |

### Gegenereerde motivering

Door de reviewer geschreven, met een concept van het systeem dat bewerkbaar is. Voor relatieve gronden bevat de motivering ook de uitkomst van de belangenafweging als gestructureerde tekst.

---

## Confidence Boosting

Wanneer meerdere detectiemethoden dezelfde entiteit vinden, wordt de betrouwbaarheid verhoogd:

| Situatie | Effect |
|----------|--------|
| Deduce EN regex vinden dezelfde entiteit | Betrouwbaarheid omhoog |
| Alleen een van beide vindt de entiteit | Betrouwbaarheid omlaag |
| LLM is het oneens met regelgebaseerde detectie | Prominent tonen aan reviewer |

---

## Vijfjaarregel (Art. 5.3)

Relatieve gronden gelden niet automatisch voor informatie ouder dan vijf jaar. Het systeem:

- Detecteert documentdatums uit metadata en inhoud
- Waarschuwt wanneer een relatieve grond wordt toegepast op een document ouder dan 5 jaar
- Vereist extra motivering van de reviewer

Dit geldt voor alle Trap 2 en Trap 3 detecties die vallen onder art. 5.1 lid 2.

---

## Exportresultaat

Na afronding van de review genereert het systeem:

- **Gelakte PDF's** — met zwarte balken en artikelnummers, irreversibel
- **Motiveringsrapport** — gestructureerd document als bijlage bij het Woo-besluit:
  - Per document: welke passages zijn gelakt en op welke grond
  - Per Woo-artikel: gebundelde motiveringstekst
  - Voor relatieve gronden: de uitkomsten van de belangenafweging
  - Statistieken: totaal passages, per grond, per trap
