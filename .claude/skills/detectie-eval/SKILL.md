---
name: detectie-eval
description: Het meet-en-verbeter-ritueel voor de WOO Buddy-detectiepijplijn - recall en vals-positieven meten tegen het ontlakte corpus, het rapport lezen, de triage gebruiken om één oorzaak te kiezen, en de baseline-delta in de PR zetten. Laden bij "draai de detectie-evaluatie", "meet recall", "evalueer de detector", "triage de false positives", "hoeveel mist de detector", "wat vindt hij te veel", of voordat je een detectieregel bouwt of aanpast.
---

# Detectie-evaluatie: meten, triëren, één oorzaak per PR

De harness in `backend/eval/` draait de echte pijplijn over 33 gepubliceerde
Woo-documenten waarin fictieve waarden zijn teruggezet. Hij levert twee
getallen die er toe doen: **recall** op wat we zelf geplant hebben, en
**vals-positief-kandidaten** op wat de lakker bewust liet staan. De triage
zegt er per fout bij wat de vermoedelijke oorzaak is en bij welke brief die
hoort.

Uitleg van het instrument staat in `backend/eval/README.md`. Deze skill gaat
over het *ritueel*: hoe je er verbetering uit haalt zonder dat elke sessie het
hele rapport moet lezen.

## 1. Voorwaarden

- Corpus op `$WOOBUDDY_EVAL_CORPUS`, standaard `~/Github NW/woobuddy-eval-corpus`.
  **Het corpus staat niet in git** - het zijn een paar honderd MB PDF's naast
  de repo. Ontbreekt het, dan stopt `evaluate.py` netjes; niet zelf opnieuw
  downloaden zonder het te vragen.
- Node 22+ op `PATH` en `frontend/node_modules` gevuld: de tekst komt uit de
  echte pdf.js, niet uit PyMuPDF. Kan dat niet, dan `--extractor pymupdf`,
  maar die cijfers zijn niet vergelijkbaar met een pdfjs-baseline.
- `backend/.venv` actief, draaien vanuit `backend/`, met `LOG_LEVEL=ERROR` -
  anders bedelft structlog het rapport.
- **Nooit met de hand een ground-truth-waarde in `ontlakt/*.json` aanpassen.**
  Dat is het enige in de hele opzet waar geen tweede bron voor is. Klopt er
  iets niet, dan is de generator fout, niet de JSON.
- `ontlak.py` alleen opnieuw draaien met hetzelfde seed (`20260907`), en alleen
  als de generator zelf veranderde. Elke hergeneratie maakt oude rapporten
  onvergelijkbaar, dus dan hoort er een nieuwe baseline bij.

## 2. Het ritueel

1. **Baseline bij?** Kijk in `<corpus>/reports/baseline.json` naar `backend.sha`.
   Is die ouder dan `origin/main`, draai de baseline dan éérst opnieuw **vanaf
   main**: `LOG_LEVEL=ERROR ./eval/evaluate.py --save-baseline`. `--save-baseline`
   hoort alleen vanaf main - een baseline van je eigen branch meet je werk
   tegen jezelf.
2. **Werk op je branch**, zoals altijd (`feat/`, `fix/`, ...).
3. **Meet**: `LOG_LEVEL=ERROR ./eval/evaluate.py --baseline "$WOOBUDDY_EVAL_CORPUS/reports/baseline.json"`.
   Een enkel document tussendoor: `--only '5_*'`.
4. **Lees het rapport in deze volgorde.** Niet van voren naar achteren:
   1. **Compared to baseline** - wat is er bewogen, in beide richtingen.
   2. **Recall per type** - waar zit de zwakte, en let op de kolom `(lenient)`:
      dat zijn treffers waarvan alleen een tussenvoegsel of een plaatsnaam
      onbedekt bleef.
   3. **Detections without a bounding box** - de rijen met region `original`
      zijn een echte bug: de reviewer krijgt een suggestie waar niets voor
      getekend wordt.
   4. **FP hard** - `auto_accepted`, dus zonder dat iemand kijkt weggelakt uit
      een gepubliceerd document. Duurder dan alles daaronder.
   5. **Triage** - de laatste sectie, of los: `./eval/triage.py <rapport>.json`.
5. **Kies één oorzaak, dus één brief, per PR.** De triage-tabel is naar
   oorzaak gegroepeerd en noemt de brief; pak de bovenste die binnen jouw
   opdracht valt. Niet drie oorzaken tegelijk: dan is de baseline-delta niet
   meer toe te schrijven.
6. **Bouw de regel met unit-tests** in `backend/tests/`, met minstens één
   negatief geval - het geval dat de regel *niet* mag opeten.
7. **Draai opnieuw** en zet de baseline-delta-tabel **letterlijk** in de
   PR-beschrijving, onder een kop `## Evaluatie`. Getallen, geen samenvatting.
8. **Zakt de recall op de geplante waarden?** Dan staat er in dezelfde
   PR-beschrijving één zin waarom dat acceptabel is (bijvoorbeeld: de gemiste
   waarden waren fixture-artefacten, of het is de prijs voor een fors lagere
   FP-hard). Staat die zin er niet, dan gaat de PR niet door.

## 3. Doctrine (waar je aan meet)

Uit `CLAUDE.md` en brief #90:

- **Liever een gemiste dan een valse kaart in Tier 2.** Een reviewer die tien
  onzin-suggesties wegklikt, vertrouwt de elfde niet meer.
- **Tier 1 auto-lakken vraagt positief bewijs** - een gevalideerd patroon, niet
  een vermoeden. Wat auto-geaccepteerd wordt, verdwijnt zonder dat iemand kijkt.
- **Twijfel is `pending`**, met een Nederlandse reden die de reviewer kan
  wegen. Nooit stil `rejected`: dat is een beslissing die niemand ziet.
- **Geen LLM.** De hele pijplijn is regels, Deduce en woordenlijsten. Zie
  `docs/reference/llm-revival.md` voordat je daar iets anders over denkt.

## 4. Wat een fixture-artefact is, en dus geen detectorfout

Herkennen scheelt een halve sessie:

- **Waarde staat aan het eind van de pagina-tekst.** Dan is de relocatie
  mislukt; `ontlak.py` schrijft met `overlay=True`, dus in leesvolgorde landt
  alles achteraan. Hoort `pdfio.relocate_planted()` recht te zetten.
- **`·` in een naam** (`Y·ld·r·m`). Oud corpus, gegenereerd met een base-14
  font. Opnieuw genereren.
- **Komma vóór of los achter de naam** na `Geachte`: het origineel had de komma
  verderop staan, dus de join zet er een spatie tussen. Geen fout.
- **De vier zienswijzen-nota's** (planviewer, valkenswaard, middendrenthe,
  molenlanden) zijn **geen** FP-referentie: daar staan namen en adressen van
  indieners gewoon in. Ze staan in `<corpus>/corpus.json` en worden apart
  geteld. Recall telt er wel mee.
- **Blackbox-slots in planviewer** hebben rommelige context; de tabelstructuur
  geeft de generator weinig houvast.

**Bij twijfel: open de ontlakte PDF op die pagina en kijk.** Dat is sneller dan
redeneren over coördinaten.

## 5. Beleidsvragen beslis je hier niet

Sommige kandidaten zijn geen bug maar een keuze: referentiekenmerken
(zaaknummers), objectadressen (het adres van de inrichting, niet van een
persoon), en mandaat-ondertekenaars ("namens dezen"). Die horen bij de brief
die erover gaat. Beslis ze niet in een detectie-PR: laat ze `pending` en zet
in de PR-beschrijving welke brief er over moet.

## 6. De catalogus uitbreiden

Staan er in `unclassified` drie of meer items met dezelfde oorzaak, voeg dan
een regel toe aan `backend/eval/triage_rules.py` - een `TriageRule` is vijf
regels - met een test in `backend/eval/test_triage.py`, in **dezelfde PR** als
het werk dat je op die oorzaak doet. Nieuwe oorzaken zonder brief krijgen
`UNASSIGNED`; de eerste sessie die er iets mee doet, vervangt dat.
