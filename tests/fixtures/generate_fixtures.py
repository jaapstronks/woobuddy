"""Generate synthetic test PDFs for WOO Buddy detection testing.

All data is fictional. These fixtures are designed to stress specific
detection categories — see README.md in this directory for what each
fixture covers.

Run from the repo root after activating the backend venv:
    cd backend && source .venv/bin/activate
    python ../tests/fixtures/generate_fixtures.py

Only writes new files; the five hand-crafted originals
(besluit_brief, besluit_ambtenaar, edge_cases, email_mixed,
nota_gezondheid) are left untouched.
"""

from __future__ import annotations

from pathlib import Path

import fitz

FIXTURES_DIR = Path(__file__).parent

A4_WIDTH, A4_HEIGHT = 595, 842
MARGIN = 60
CONTENT_RECT = fitz.Rect(MARGIN, MARGIN, A4_WIDTH - MARGIN, A4_HEIGHT - MARGIN)

CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #000; }
h1 { font-size: 18pt; margin: 0 0 4pt 0; }
h2 { font-size: 11pt; margin: 14pt 0 4pt 0; }
p { margin: 0 0 6pt 0; line-height: 1.45; }
p.row { margin: 0 0 2pt 0; }
.label { color: #555; }
.header-meta { color: #222; font-size: 9pt; margin-bottom: 14pt; }
.note { color: #555; font-style: italic; font-size: 9pt; }
ul { margin: 0 0 8pt 14pt; }
li { margin: 0 0 2pt 0; }
"""


def _render(html_body: str, out_path: Path) -> None:
    """Render an HTML body to a multi-page A4 PDF via fitz.Story.

    Story.place returns more=1 while content is still pending, so we
    loop and emit a new page each iteration until the whole story has
    been drawn.
    """
    mediabox = fitz.Rect(0, 0, A4_WIDTH, A4_HEIGHT)
    story = fitz.Story(html=f"<style>{CSS}</style>{html_body}")
    writer = fitz.DocumentWriter(str(out_path))
    more = 1
    while more:
        dev = writer.begin_page(mediabox)
        more, _filled = story.place(CONTENT_RECT)
        story.draw(dev)
        writer.end_page()
    writer.close()
    print(f"  wrote {out_path.name}")


# ---------------------------------------------------------------------------
# Fixture 1: tier1_all_identifiers.pdf
#
# Every Tier 1 regex pattern in every accepted variant, plus negative
# controls (invalid-Luhn card, failing-11-proef 9-digit number, non-NL
# IBAN, lowercase postcode). Framed as an internal "how identifiers
# appear in real dossiers" note so Deduce still runs naturally.
# ---------------------------------------------------------------------------


TIER1_HTML = """
<h1>Intern voorbeelddocument</h1>
<div class="header-meta">
    Kenmerk: ICT-2024-0118 &nbsp;&nbsp; Datum: 9 maart 2024<br/>
    Onderwerp: overzicht van identificatoren zoals zij voorkomen in Woo-dossiers
</div>

<p>Dit document verzamelt voorbeelden van persoonsgegevens en andere
identificatoren zoals onze redactiemedewerkers ze in echte Woo-dossiers
tegenkomen. <em>Alle onderstaande gegevens zijn fictief en dienen
uitsluitend voor test- en trainingsdoeleinden.</em></p>

<h2>1. BSN-nummers (Burgerservicenummer)</h2>
<p class="row">Geldig BSN &mdash; <span class="label">111222333</span></p>
<p class="row">Nog een geldige &mdash; <span class="label">123456782</span></p>
<p class="row">Referentienummer (geen BSN) &mdash; <span class="label">987654321</span></p>
<p class="row">9 cijfers, faalt 11-proef &mdash; <span class="label">999999999</span></p>
<p class="note">Alleen de eerste twee voldoen aan de 11-proef en moeten
als BSN worden gedetecteerd; de andere twee niet.</p>

<h2>2. IBAN-rekeningnummers</h2>
<p class="row">Compact &mdash; NL91ABNA0417164300</p>
<p class="row">Kleine letters &mdash; nl02rabo0123456789</p>
<p class="row">Gegroepeerd &mdash; NL68 RABO 0338 1615 89</p>
<p class="row">Duitse IBAN &mdash; DE89370400440532013000</p>
<p class="row">Belgische IBAN &mdash; BE68 5390 0754 7034</p>
<p class="note">De NL-varianten moeten worden gedetecteerd; de DE/BE
IBAN's vallen buiten het Nederlandse patroon en blijven staan.</p>

<h2>3. Telefoonnummers</h2>
<p class="row">Nederlandse mobiel &mdash; 06-12345678</p>
<p class="row">Mobiel zonder streepje &mdash; 0612345678</p>
<p class="row">Vaste lijn Amsterdam &mdash; 020-1234567</p>
<p class="row">Vaste lijn Eindhoven &mdash; 040 2345678</p>
<p class="row">Internationaal mobiel &mdash; +31 6 12345678</p>
<p class="row">Idem zonder spaties &mdash; +31612345678</p>
<p class="row">Internationaal vast (gesplitst in groepen) &mdash; +31 40 792 00 35</p>
<p class="row">Referentie (te kort, geen telefoon) &mdash; 06-1234</p>

<h2>4. E-mailadressen</h2>
<p class="row">Standaard &mdash; jan.jansen@voorbeeld.nl</p>
<p class="row">Plus-addressing &mdash; info+woo@overheid.nl</p>
<p class="row">Koppelteken in domein &mdash; h.van-der-berg@gemeente-utrecht.nl</p>

<h2>5. URL's</h2>
<p>Voor de landelijke richtlijnen zie https://www.rijksoverheid.nl.
Het LinkedIn-profiel van de penningmeester staat op
https://www.linkedin.com/in/natasja-paulssen-hallema-20880353/ en wordt
vaak in verslagen genoemd. Interne documentatie: https://intranet.example.nl/woo?ref=x.
Let op dat de punt aan het einde van de vorige zin <em>niet</em> bij de
URL hoort.</p>

<h2>6. Postcodes</h2>
<p class="row">Met spatie &mdash; 1234 AB</p>
<p class="row">Zonder spatie &mdash; 1234AB</p>
<p class="row">Lowercase (ongeldig) &mdash; 1234ab</p>
<p class="note">De eerste twee voldoen aan het patroon; de derde niet &mdash;
postcodes vereisen hoofdletters.</p>

<h2>7. Kentekens</h2>
<p class="row">Sidecode 6 &mdash; AB-123-C</p>
<p class="row">Sidecode 7 &mdash; 1-ABC-23</p>
<p class="row">Sidecode 8 &mdash; AB-12-CD</p>
<p class="row">Sidecode 9 &mdash; 12-AB-34</p>
<p class="row">Sidecode 10 &mdash; 12-ABC-3</p>

<h2>8. Creditcardnummers</h2>
<p class="row">Geldig (Luhn ok) &mdash; 4532 0151 1283 0366</p>
<p class="row">Ongeldig (Luhn fail) &mdash; 1234 5678 9012 3456</p>
<p class="note">Alleen het eerste nummer mag als creditcard worden
gedetecteerd.</p>
"""


# ---------------------------------------------------------------------------
# Fixture 2: false_positives.pdf
#
# A realistic-reading verslag that deliberately contains strings which
# look like Tier 1 identifiers but should NOT fire, plus proper nouns
# that Deduce has historically mis-tagged as persons (institutions,
# museums, ministeries, Dutch article + capitalised noun).
# ---------------------------------------------------------------------------


FALSE_POSITIVES_HTML = """
<h1>Gemeente Eindhoven</h1>
<div class="header-meta">
    Postbus 90150, 5600 RB Eindhoven<br/>
    Telefoon: 040 238 60 60
</div>

<table>
  <tr><td class="label">Kenmerk:</td><td>EZ-2024-00897</td></tr>
  <tr><td class="label">Datum:</td><td>14 februari 2024</td></tr>
  <tr><td class="label">Onderwerp:</td><td>Verslag commissie Economische Zaken</td></tr>
</table>

<h2>1. Samenwerkingsverbanden</h2>
<p>De voorzitter meldt dat de Amsterdamse Hogeschool voor de Kunsten en
het Instituut Beeld en Geluid een samenwerkingsverband zijn aangegaan.
Ook het Rijksmuseum, Naturalis Biodiversity Center, de Kunsthal Rotterdam
en de Universiteit Utrecht hebben hun medewerking toegezegd. Vanuit de
rijksoverheid wordt de samenwerking begeleid door het Ministerie van
Onderwijs, Cultuur en Wetenschap.</p>

<p class="note">Deze organisatienamen moeten NIET als persoonsnaam
worden gedetecteerd. Deduce heeft ze historisch vaak foutief als
<code>persoon</code> getagd — de organisatie-heuristiek in de NER-engine
dient ze weg te filteren.</p>

<h2>2. Budget en projectnummers</h2>
<p>Het beschikbare budget voor dit programma bedraagt EUR 2.345.678,90
over de periode 2019-2024. Het interne projectnummer is EZ-2024-456-A;
dit lijkt qua vorm op een kenteken maar betreft een administratief
kenmerk. Het dossiernummer in het begrotingssysteem is 987654321 —
een 9-cijferig nummer dat niet voldoet aan de 11-proef en dus geen
BSN is.</p>

<h2>3. Openbare handelsregistergegevens</h2>
<p>De volgende rechtspersonen hebben een subsidie ontvangen: Stichting
Cultuurfonds Brabant (KvK 12345678), Vereniging Nederlandse Musea
(KvK 87654321) en de Coöperatie Creatief Zuid U.A. (KvK 24681012).
KvK-nummers zijn openbare handelsregistergegevens en vallen niet
onder de bescherming van de Woo.</p>

<h2>4. Buitenlandse betalingen</h2>
<p>De Europese partners werden uitbetaald op buitenlandse rekeningen:
DE89370400440532013000 (Duitsland) en BE68 5390 0754 7034 (België).
Deze IBAN's vallen onder buitenlandse wetgeving en zijn niet geldig
binnen het Nederlandse IBAN-patroon.</p>

<h2>5. Aanwezige partijen</h2>
<p>Namens de gemeente Amsterdam, de provincie Noord-Holland en het
college van gedeputeerde staten van Utrecht waren delegaties aanwezig.
De vergadering vond plaats in het Stadhuis Eindhoven. De notulen zijn
vastgesteld op 21 februari 2024.</p>

<p class="note">Noten voor het testdoel: &ldquo;gemeente Amsterdam&rdquo;,
&ldquo;provincie Noord-Holland&rdquo;, &ldquo;college van gedeputeerde
staten&rdquo; en &ldquo;Stadhuis Eindhoven&rdquo; zijn organisatienamen
en mogen niet als persoonsnaam worden aangemerkt. &ldquo;21 februari
2024&rdquo; is een vergaderdatum, geen geboortedatum — Deduce flagt
datums als Tier 2, wat correct is, maar de reviewer zal ze afwijzen.</p>
"""


# ---------------------------------------------------------------------------
# Fixture 3: raadsvergadering.pdf
#
# A meeting minutes document that mixes public officials (burgemeester,
# wethouders, raadsleden — should be flagged but typically NOT redacted)
# with private citizens (insprekers, their neighbours — should be
# flagged AND redacted). Tests the system's ability to surface everyone
# for human review.
# ---------------------------------------------------------------------------


RAADSVERGADERING_HTML = """
<h1>Gemeente Leiden</h1>
<div class="header-meta">
    Postbus 9100, 2300 PC Leiden<br/>
    Telefoon: 071 516 50 00
</div>

<table>
  <tr><td class="label">Kenmerk:</td><td>RV-2024-00023</td></tr>
  <tr><td class="label">Datum:</td><td>12 maart 2024</td></tr>
  <tr><td class="label">Onderwerp:</td><td>Verslag openbare raadsvergadering</td></tr>
</table>

<h2>Aanwezig</h2>
<ul>
  <li>Burgemeester H.J.J. Lenferink (voorzitter)</li>
  <li>Wethouder mw. Y. van Delft (Ruimtelijke Ordening)</li>
  <li>Wethouder dhr. A. North (Financi&euml;n)</li>
  <li>Gemeentesecretaris dhr. P. Goedhart</li>
  <li>38 raadsleden, waaronder fractievoorzitters dhr. R. van Gelderen
      (VVD), mw. L. Rozendaal (GroenLinks), dhr. M. Dirkse (PvdA) en
      mw. S. Abdelkader (D66)</li>
</ul>

<p><strong>Inspreker:</strong> mevrouw J. de Vries namens de
bewonersvereniging Morsdistrict. Zij is woonachtig aan de Morsstraat 14
(2312 AB Leiden) en bereikbaar op 071-5123456 of j.devries@voorbeeld.nl.</p>

<h2>1. Opening</h2>
<p>De burgemeester opent de vergadering om 20:00 uur en heet de
aanwezigen welkom. De agenda wordt ongewijzigd vastgesteld.</p>

<h2>2. Inspraak bewoners</h2>
<p>Mw. De Vries voert het woord namens ongeveer vijftig bewoners. Zij
uit zorgen over de parkeerdruk in de wijk en noemt specifiek de
overlast bij haar directe buren, mevrouw T. Bakker (huisnummer 18) en
de familie El Khatib (huisnummer 22). Ook de heer W. de Groot, bewoner
van nummer 26, heeft eerder klachten ingediend.</p>

<p>Wethouder Van Delft reageert dat het college de zorgen serieus
neemt en zegt toe een buurtonderzoek uit te voeren. Zij refereert aan
eerder contact met de bewonerscommissie via voorzitter dhr. K. Hendriks.</p>

<h2>3. Stemming amendement parkeerregulering</h2>
<p>Raadslid Van Gelderen (VVD) dient namens zijn fractie een amendement
in. Het amendement wordt aangenomen met 22 stemmen voor en 16 tegen.
De namen van de individuele raadsleden die voor en tegen stemden zijn
opgenomen in bijlage A en zijn openbaar (raadsleden stemmen in functie
en hun stemgedrag valt niet onder bescherming persoonlijke levenssfeer).</p>

<h2>4. Mededelingen college</h2>
<p>Wethouder North meldt dat de jaarrekening 2023 op 4 april 2024 aan
de raad wordt aangeboden. De burgemeester attendeert op het bezoek van
Commissaris van de Koning drs. J.W. Remkes op 19 maart.</p>

<h2>5. Afsluiting</h2>
<p>De burgemeester sluit de vergadering om 22:30 uur. De volgende
vergadering is op 9 april 2024.</p>

<p class="note">Testdoel: raadsleden, wethouders, burgemeester en
gemeentesecretaris zijn publieke functionarissen en worden doorgaans
niet geredigeerd &mdash; de detector moet ze wel als suggestie
aanbieden zodat een reviewer per geval kan beslissen. Private burgers
(mw. J. de Vries als inspreker, haar buren Bakker / El Khatib / De Groot)
moeten worden geflagd &eacute;n in de meeste gevallen geredigeerd.</p>
"""


README_MD = """# Test fixtures — WOO Buddy

PDF fixtures for testing end-to-end detection (upload → client extraction → server NER → review list). All data is fictional.

## Originals (hand-crafted)

| File | Tests |
|---|---|
| `besluit_brief.pdf` | Standard Woo decision letter to a citizen. Basic Tier 1 coverage: BSN, postcode, Dutch mobile, email, name, address, date. |
| `besluit_ambtenaar.pdf` | Public officials scenario — wethouder, raadsleden, gemeentesecretaris. Should be flagged but typically not redacted. |
| `edge_cases.pdf` | Meeting minutes with mixed citizens + businesses. KvK numbers (should NOT be redacted), house-number references, organization names. |
| `email_mixed.pdf` | Email thread with IBAN, email, phone, license plate, foreign name, a 9-digit non-BSN, a fake birthdate. |
| `nota_gezondheid.pdf` | Tier 3 — health info (Art 5.1.2d bijzondere persoonsgegevens), religion, BSN, IBAN, address. Stress-tests content judgment. |

## Generated (synthetic, regenerate with `generate_fixtures.py`)

| File | Tests |
|---|---|
| `tier1_all_identifiers.pdf` | Every Tier 1 regex pattern in every accepted variant — compact & spaced IBAN, lowercase IBAN, mobile/landline/international phone, plus-addressing email, long hyphenated URL, postcode with/without space, all sidecode license plates, Luhn-valid credit card. Includes negative controls (invalid BSN, failing-Luhn card, foreign IBAN, lowercase postcode) that must NOT fire. |
| `false_positives.pdf` | Deliberate traps: 9-digit reference numbers that fail 11-proef, foreign IBANs, KvK numbers, project numbers shaped like plates, year ranges shaped like dates, and institution names Deduce historically mis-tagged as persons (Amsterdamse Hogeschool, Rijksmuseum, Kunsthal, Universiteit Utrecht, Ministerie van OCW, gemeente Amsterdam, Stichting Cultuurfonds, Vereniging Nederlandse Musea). |
| `raadsvergadering.pdf` | Mixed public/private scenario. Public functionaries (burgemeester, wethouders, raadsleden, gemeentesecretaris, Commissaris van de Koning) should be flagged but typically not redacted. Private citizens (inspreker + her named neighbours) should be flagged AND redacted. Tests that the detector surfaces everyone for human review. |

## Regenerating

```bash
cd backend && source .venv/bin/activate
python ../tests/fixtures/generate_fixtures.py
```

The generator only writes the three files in the "Generated" table above — the hand-crafted originals are never touched.
"""


def main() -> None:
    print(f"Generating fixtures in {FIXTURES_DIR}")
    _render(TIER1_HTML, FIXTURES_DIR / "tier1_all_identifiers.pdf")
    _render(FALSE_POSITIVES_HTML, FIXTURES_DIR / "false_positives.pdf")
    _render(RAADSVERGADERING_HTML, FIXTURES_DIR / "raadsvergadering.pdf")
    readme = FIXTURES_DIR / "README.md"
    readme.write_text(README_MD, encoding="utf-8")
    print(f"  wrote {readme.name}")
    print("Done.")


if __name__ == "__main__":
    main()
