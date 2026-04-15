"""Generate public-facing sample PDFs for the landing-page "probeer een voorbeeld" flow.

These are NOT test fixtures — they are user-facing assets shipped under
``frontend/static/samples/``. The reviewer clicks one on the landing page
and the PDF is loaded into the client-first upload pipeline as if they
had dropped it themselves. See ``docs/todo/done/44-sample-documents-landing.md``.

All content is fictional. Names, addresses, BSNs, IBANs, and phone
numbers are invented — every BSN below satisfies the 11-proef, every
IBAN satisfies the mod-97 check, but no number belongs to a real person.

Run from the repo root after activating the backend venv:

    cd backend && source .venv/bin/activate
    python ../tests/fixtures/generate_samples.py
"""

from __future__ import annotations

from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "frontend" / "static" / "samples"

A4_WIDTH, A4_HEIGHT = 595, 842
MARGIN = 60
CONTENT_RECT = fitz.Rect(MARGIN, MARGIN, A4_WIDTH - MARGIN, A4_HEIGHT - MARGIN)

# Thumbnail render: first page at ~1.5x scale, cropped on the frontend via CSS.
THUMB_ZOOM = 1.5

CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #111; }
h1 { font-size: 16pt; margin: 0 0 4pt 0; }
h2 { font-size: 11pt; margin: 14pt 0 4pt 0; }
h3 { font-size: 10pt; margin: 10pt 0 3pt 0; }
p { margin: 0 0 6pt 0; line-height: 1.5; }
p.row { margin: 0 0 2pt 0; }
.label { color: #555; }
.header-meta { color: #222; font-size: 9pt; margin-bottom: 14pt; }
.note { color: #555; font-style: italic; font-size: 9pt; }
.email-header { background: #f4f4f4; padding: 6pt; font-size: 9pt; margin: 10pt 0 6pt 0; }
.signature { color: #444; font-size: 9pt; margin-top: 8pt; }
hr { border: 0; border-top: 1pt solid #ccc; margin: 14pt 0; }
ul { margin: 0 0 8pt 14pt; }
li { margin: 0 0 2pt 0; }
"""


def _render(html_body: str, out_path: Path) -> None:
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
    print(f"  wrote {out_path.relative_to(REPO_ROOT)}")


def _thumbnail(pdf_path: Path, out_path: Path) -> None:
    """Render the first page of ``pdf_path`` to a PNG thumbnail."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(THUMB_ZOOM, THUMB_ZOOM), alpha=False)
        pix.save(str(out_path))
    finally:
        doc.close()
    print(f"  wrote {out_path.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------------
# Sample 1 — E-mail thread tussen ambtenaren
#
# Covers: e-mailheaders, handtekeningblokken, publiek-functionaris filter
# (the ambtenaren in the cc should NOT be redacted), forwarded citizen
# complaint with name/address/phone/email that SHOULD be redacted.
# ---------------------------------------------------------------------------

EMAIL_THREAD_HTML = """
<h1>E-mailwisseling &mdash; parkeerklacht Morsdistrict</h1>
<div class="header-meta">
    Gemeente Leiden &middot; cluster Ruimtelijke Ordening &middot; dossier RV-2026-00142
</div>

<p>Onderstaande e-mailwisseling is opgevraagd in het kader van een Woo-verzoek
over de parkeerproblematiek in het Morsdistrict. De thread bevat drie e-mails
tussen ambtenaren en een doorgestuurde klacht van een bewoner.</p>

<div class="email-header">
<strong>Van:</strong> Y. van Delft &lt;y.vandelft@leiden.nl&gt;<br/>
<strong>Aan:</strong> P. Goedhart &lt;p.goedhart@leiden.nl&gt;<br/>
<strong>Cc:</strong> A. North &lt;a.north@leiden.nl&gt;, team-RO &lt;ro@leiden.nl&gt;<br/>
<strong>Datum:</strong> dinsdag 3 maart 2026, 09:14<br/>
<strong>Onderwerp:</strong> Klacht bewoners Morsstraat &mdash; hoe verder?
</div>

<p>Beste Pieter,</p>
<p>Ik ontving gisteren onderstaande klacht van mevrouw De Vries uit het
Morsdistrict. De toon is stevig en ze verwijst naar drie eerdere meldingen
die onbeantwoord zouden zijn gebleven. Kun jij bij het KCC laten nagaan
of die meldingen inderdaad zijn binnengekomen en waarom er geen
terugkoppeling is geweest?</p>
<p>Ik wil voorstellen om voor het einde van de maand een buurtonderzoek
op te starten &mdash; parallel aan de evaluatie van de parkeerzone die
toch al gepland staat. Wethouder North heeft hier vorige week ook naar
gevraagd tijdens het coll&eacute;ge-overleg.</p>

<p class="signature">
Met vriendelijke groet,<br/>
Yvonne van Delft<br/>
Wethouder Ruimtelijke Ordening<br/>
Gemeente Leiden &middot; Stadhuis, Stadhuisplein 1, 2311 EJ Leiden<br/>
T 071 516 51 00 &middot; y.vandelft@leiden.nl
</p>

<hr/>

<div class="email-header">
<strong>Van:</strong> P. Goedhart &lt;p.goedhart@leiden.nl&gt;<br/>
<strong>Aan:</strong> Y. van Delft &lt;y.vandelft@leiden.nl&gt;<br/>
<strong>Cc:</strong> A. North &lt;a.north@leiden.nl&gt;, team-RO &lt;ro@leiden.nl&gt;<br/>
<strong>Datum:</strong> dinsdag 3 maart 2026, 11:42<br/>
<strong>Onderwerp:</strong> RE: Klacht bewoners Morsstraat &mdash; hoe verder?
</div>

<p>Dag Yvonne,</p>
<p>Ik heb het bij het KCC laten nalopen. Er zijn inderdaad drie meldingen
geregistreerd op naam van J. de Vries, Morsstraat 14, 2312 AB Leiden, in
de maanden december 2025 en januari 2026. De eerste twee zijn netjes
afgehandeld met een standaardbrief; de derde is blijven hangen bij een
medewerker die sinds half januari met ziekteverlof is. Mijn excuses
namens het cluster &mdash; dit had niet mogen gebeuren.</p>
<p>Wat betreft het buurtonderzoek: ik stel voor dat wij het inplannen
voor week 12 (16&ndash;20 maart). Ik kan collega M. Dirkse vragen het te
co&ouml;rdineren. Hij heeft het vorig jaar ook gedaan voor de wijk
Professorenbuurt en daar werkte de aanpak goed.</p>
<p>Ik voeg de originele klacht van mevrouw De Vries hieronder toe voor
het dossier.</p>

<p class="signature">
Met vriendelijke groet,<br/>
Pieter Goedhart<br/>
Gemeentesecretaris Leiden<br/>
T 071 516 50 00 &middot; p.goedhart@leiden.nl
</p>

<hr/>

<div class="email-header">
<strong>Van:</strong> J. de Vries &lt;j.devries@voorbeeld.nl&gt;<br/>
<strong>Aan:</strong> info@leiden.nl<br/>
<strong>Datum:</strong> maandag 2 maart 2026, 22:07<br/>
<strong>Onderwerp:</strong> Derde melding parkeeroverlast Morsstraat &mdash; nu graag antwoord
</div>

<p>Geachte mevrouw, mijnheer,</p>
<p>Dit is de derde keer dat ik de gemeente aanschrijf over de
parkeeroverlast in onze straat. Mijn eerdere meldingen van 8 december
2025 en 14 januari 2026 zijn niet beantwoord. Ik ben het beu.</p>
<p>De situatie is als volgt. Sinds de herinrichting van het Noordeinde
parkeren dagelijks tientallen auto&rsquo;s van niet-bewoners in onze straat.
Mijn buurvrouw op nummer 18 (mevrouw T. Bakker) kan haar oprit vaak
niet op of af. De familie op nummer 22 heeft twee keer een deuk
gemeld. Zelf woon ik op Morsstraat 14 en moet regelmatig mijn auto
een halve kilometer verderop kwijt.</p>
<p>Ik vraag de gemeente om <em>binnen twee weken</em> te laten weten
welke concrete stappen worden genomen. Ik ben bereikbaar op
06-12345678 of via dit e-mailadres. Voor de volledigheid voeg ik mijn
contactgegevens en die van enkele mede-ondertekenaars toe.</p>

<h3>Ondertekenaars</h3>
<ul>
  <li>Jolanda de Vries &mdash; Morsstraat 14, 2312 AB Leiden &mdash; 06-12345678</li>
  <li>Tineke Bakker &mdash; Morsstraat 18, 2312 AB Leiden &mdash; 071-5123456</li>
  <li>Walter de Groot &mdash; Morsstraat 26, 2312 AB Leiden &mdash; 06-98765432</li>
</ul>

<p>Met vriendelijke groet,<br/>
Jolanda de Vries</p>

<hr/>

<div class="email-header">
<strong>Van:</strong> A. North &lt;a.north@leiden.nl&gt;<br/>
<strong>Aan:</strong> Y. van Delft &lt;y.vandelft@leiden.nl&gt;, P. Goedhart &lt;p.goedhart@leiden.nl&gt;<br/>
<strong>Datum:</strong> woensdag 4 maart 2026, 08:31<br/>
<strong>Onderwerp:</strong> RE: Klacht bewoners Morsstraat &mdash; hoe verder?
</div>

<p>Yvonne, Pieter,</p>
<p>Prima voorstel. Ik ondersteun het buurtonderzoek in week 12. Graag
Dirkse vragen; ik spreek hem vrijdag en zal het kort toelichten.</p>
<p>Belangrijk: mevrouw De Vries verdient een persoonlijk antwoord
voor het einde van deze week. Yvonne, kun jij dat oppakken? Inhoudelijk
korte excuses voor de stilte, toezegging van het buurtonderzoek,
terugkoppeling toegezegd uiterlijk 27 maart.</p>

<p class="signature">
Arjen North<br/>
Wethouder Financi&euml;n<br/>
Gemeente Leiden<br/>
T 071 516 52 00 &middot; a.north@leiden.nl
</p>
"""


# ---------------------------------------------------------------------------
# Sample 2 — Raadsverslag met deelnemerslijst
#
# Covers: attendee list detection, role classification, mixed public/
# private persons, inspreker, references to neighbours.
# ---------------------------------------------------------------------------

RAADSVERSLAG_HTML = """
<h1>Verslag openbare commissievergadering</h1>
<div class="header-meta">
    Gemeente Leiden &middot; commissie Leefbaarheid en Bestuur<br/>
    Kenmerk RV-2026-00023 &middot; donderdag 12 maart 2026, 20:00&ndash;22:45 uur<br/>
    Raadszaal, Stadhuis Leiden
</div>

<h2>Aanwezig</h2>
<ul>
  <li>Burgemeester H.J.J. Lenferink (voorzitter)</li>
  <li>Wethouder mw. Y. van Delft (Ruimtelijke Ordening)</li>
  <li>Wethouder dhr. A. North (Financi&euml;n)</li>
  <li>Wethouder mw. S. El Idrissi (Sociaal Domein)</li>
  <li>Gemeentesecretaris dhr. P. Goedhart</li>
  <li>Fractievoorzitters:
    <ul>
      <li>dhr. R. van Gelderen (VVD)</li>
      <li>mw. L. Rozendaal (GroenLinks)</li>
      <li>dhr. M. Dirkse (PvdA)</li>
      <li>mw. S. Abdelkader (D66)</li>
      <li>dhr. J. Beckers (CDA)</li>
      <li>mw. I. Tjon (Partij voor de Dieren)</li>
    </ul>
  </li>
  <li>38 raadsleden (aanwezigheidslijst bijlage A)</li>
</ul>

<h2>Insprekers</h2>
<p><strong>Mevrouw Jolanda de Vries</strong>, namens de
bewonersvereniging Morsdistrict. Woonachtig aan de Morsstraat 14,
2312 AB Leiden. Bereikbaar op 06-12345678 of
j.devries@voorbeeld.nl.</p>
<p><strong>De heer Bastiaan Kooij</strong>, ondernemer aan het
Noordeinde, eigenaar van caf&eacute; De Tussenstop (KvK 12345678).
Bereikbaar via info@detussenstop.nl.</p>

<h2>1. Opening en vaststelling agenda</h2>
<p>De burgemeester opent de vergadering om 20:00 uur en heet de
aanwezigen welkom. De agenda wordt ongewijzigd vastgesteld. Er zijn
geen berichten van verhindering binnengekomen.</p>

<h2>2. Vaststelling verslag vorige vergadering</h2>
<p>Het verslag van de vergadering van 13 februari 2026 wordt
ongewijzigd vastgesteld.</p>

<h2>3. Inspraakronde &mdash; parkeerproblematiek Morsdistrict</h2>
<p>Mevrouw De Vries voert het woord namens ongeveer vijftig bewoners
van het Morsdistrict. Zij uit zorgen over de parkeerdruk in de wijk
en noemt de overlast bij haar directe buren &mdash; mevrouw T. Bakker
(Morsstraat 18) en de familie El Khatib (Morsstraat 22). Ook de heer
W. de Groot, bewoner van nummer 26, heeft eerder klachten ingediend.</p>
<p>Mevrouw De Vries overhandigt een petitie met 147 handtekeningen
aan de voorzitter. De petitie is als bijlage B aan dit verslag
toegevoegd; de namen en adressen van de ondertekenaars zijn daarin
opgenomen.</p>
<p>Wethouder Van Delft reageert dat het college de zorgen serieus
neemt en zegt toe een buurtonderzoek uit te voeren in week 12. Zij
refereert aan eerder contact met de bewonerscommissie via voorzitter
dhr. K. Hendriks.</p>

<h2>4. Inspraakronde &mdash; horecasluiting Noordeinde</h2>
<p>De heer Kooij licht toe dat de voorgestelde sluitingstijd van
01:00 uur voor de horeca aan het Noordeinde een omzetverlies van naar
schatting EUR 48.500 per jaar betekent voor zijn onderneming.
Hij verzoekt de raad de uitzondering voor weekenden te handhaven.</p>
<p>Wethouder El Idrissi antwoordt dat de afweging tussen leefbaarheid
en ondernemersbelangen in de volgende raadsvergadering integraal
wordt behandeld.</p>

<h2>5. Stemming amendement parkeerregulering</h2>
<p>Raadslid Van Gelderen (VVD) dient namens zijn fractie een
amendement in. Het amendement beoogt een vergunninghoudersregeling
voor bewoners van het Morsdistrict in te voeren. Na korte beraadslaging
wordt het amendement aangenomen met 22 stemmen voor en 16 tegen. De
stemverdeling per raadslid is opgenomen in bijlage C en is openbaar
(raadsleden stemmen in functie en hun stemgedrag valt niet onder
bescherming persoonlijke levenssfeer).</p>

<h2>6. Mededelingen college</h2>
<p>Wethouder North meldt dat de jaarrekening 2025 op 4 april 2026 aan
de raad wordt aangeboden. De burgemeester attendeert op het bezoek
van Commissaris van de Koning drs. J.W. Remkes op 19 maart.</p>

<h2>7. Rondvraag</h2>
<p>Raadslid Rozendaal (GroenLinks) vraagt wanneer het
klimaatadaptatieplan wordt ge&euml;valueerd. Wethouder Van Delft zegt toe
hierop schriftelijk terug te komen voor de volgende commissievergadering.</p>
<p>Raadslid Beckers (CDA) vraagt naar de voortgang van de motie
over huiselijk geweld van 15 januari 2026. Wethouder El Idrissi
verwijst naar de voortgangsrapportage die in april wordt gepubliceerd.</p>

<h2>8. Sluiting</h2>
<p>De voorzitter sluit de vergadering om 22:45 uur. De volgende
commissievergadering is op 9 april 2026.</p>

<p class="note">Bijlage A (aanwezigheidslijst raadsleden), bijlage B
(petitie bewoners Morsdistrict met 147 handtekeningen) en bijlage C
(stemverdeling amendement parkeerregulering) zijn afzonderlijk bij
dit verslag gevoegd.</p>
"""


# ---------------------------------------------------------------------------
# Sample 3 — Klachtbrief met Tier 1 identifiers
#
# Covers: BSN, IBAN, address, postcode, phone, email, birthdate. All
# hard identifiers — classic Tier 1 stress test.
# ---------------------------------------------------------------------------

KLACHTBRIEF_HTML = """
<h1>Klacht bezwaarprocedure huurtoeslag</h1>
<div class="header-meta">
    Aan: gemeente Leiden, team Sociaal Domein<br/>
    Postbus 9100, 2300 PC Leiden<br/>
    Datum: 6 februari 2026
</div>

<p>Geachte mevrouw, mijnheer,</p>

<p>Met deze brief dien ik formeel een klacht in over de afhandeling
van mijn bezwaarschrift tegen de beschikking huurtoeslag 2025. Hieronder
treft u mijn gegevens, een korte feitenweergave en mijn verzoek.</p>

<h2>Persoonsgegevens klager</h2>
<p class="row"><span class="label">Naam:</span> Jolanda Maria de Vries</p>
<p class="row"><span class="label">Geboortedatum:</span> 14 juli 1978</p>
<p class="row"><span class="label">BSN:</span> 111222333</p>
<p class="row"><span class="label">Adres:</span> Morsstraat 14, 2312 AB Leiden</p>
<p class="row"><span class="label">Telefoon:</span> 06-12345678</p>
<p class="row"><span class="label">E-mail:</span> j.devries@voorbeeld.nl</p>
<p class="row"><span class="label">Rekeningnummer:</span> NL91 ABNA 0417 1643 00</p>
<p class="row"><span class="label">Dossiernummer gemeente:</span> SD-2025-04517</p>

<h2>Feitenweergave</h2>
<p>Op 14 oktober 2025 ontving ik de beschikking huurtoeslag 2025 met
kenmerk SD-2025-04517. In die beschikking werd mijn toeslag verlaagd
van EUR 287 per maand naar EUR 112 per maand op basis van een
inkomensschatting die naar mijn mening niet klopt. Op 20 oktober 2025
heb ik tijdig bezwaar aangetekend via het digitale bezwaarformulier.</p>

<p>Op 3 november 2025 ontving ik een ontvangstbevestiging, met de
toezegging dat ik binnen zes weken uitsluitsel zou krijgen. Die
termijn is inmiddels ruim drie maanden verstreken. Meerdere
telefonische navragen bij het KCC op 15 december 2025, 8 januari 2026
en 22 januari 2026 leverden steeds de boodschap op dat het dossier
&ldquo;nog in behandeling&rdquo; is.</p>

<p>In de tussentijd heb ik mijn huur maandelijks volledig moeten
betalen uit een reserve die daar niet voor bedoeld is. Mijn
werkgeversinkomen bij de Universiteit Leiden is met ingang van
1 januari 2026 gewijzigd; de nieuwe inkomensgegevens zijn op
5 januari 2026 doorgegeven via Mijn Toeslagen.</p>

<h2>Overige betrokken gegevens</h2>
<p>Ter onderbouwing verwijs ik naar onderstaande documenten, die als
bijlagen zijn toegevoegd:</p>
<ul>
  <li>Kopie beschikking 14 oktober 2025, kenmerk SD-2025-04517</li>
  <li>Bezwaarschrift 20 oktober 2025</li>
  <li>Ontvangstbevestiging 3 november 2025, kenmerk KCC-2025-88231</li>
  <li>Loonstrook december 2025 Universiteit Leiden (werkgeversnummer 871234567)</li>
  <li>Bankafschrift NL91 ABNA 0417 1643 00 over januari 2026</li>
</ul>

<p>Mijn huisarts, mevrouw dr. A. Chen (Gezondheidscentrum Morsdistrict,
Morsweg 45, 2312 CD Leiden, 071-5123400), kan op verzoek bevestigen
dat de aanhoudende onzekerheid over de toeslag invloed heeft gehad
op mijn gezondheid.</p>

<h2>Verzoek</h2>
<p>Ik verzoek u:</p>
<ol>
  <li>binnen twee weken na ontvangst van deze brief een inhoudelijk
  besluit op mijn bezwaar te nemen;</li>
  <li>mij schriftelijk te informeren waarom de wettelijke termijn is
  overschreden;</li>
  <li>de eventueel te veel ingehouden bedragen terug te storten op
  rekening NL91 ABNA 0417 1643 00 ten name van J.M. de Vries.</li>
</ol>

<p>Indien ik binnen twee weken geen inhoudelijk antwoord ontvang,
zal ik de Nationale Ombudsman inschakelen.</p>

<p>Met vriendelijke groet,</p>
<p>Jolanda M. de Vries<br/>
Morsstraat 14<br/>
2312 AB Leiden<br/>
06-12345678 &middot; j.devries@voorbeeld.nl</p>

<p class="note">Bijlagen: 5 stuks zoals hierboven opgesomd. Kopie van
deze brief gaat naar mijn rechtsbijstandsverzekeraar (DAS
Rechtsbijstand, dossier DAS-2026-0014).</p>
"""


SAMPLES = [
    ("email-thread.pdf", EMAIL_THREAD_HTML),
    ("raadsverslag.pdf", RAADSVERSLAG_HTML),
    ("klachtbrief.pdf", KLACHTBRIEF_HTML),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating landing-page samples in {OUT_DIR.relative_to(REPO_ROOT)}")
    for filename, html in SAMPLES:
        pdf_path = OUT_DIR / filename
        _render(html, pdf_path)
        _thumbnail(pdf_path, pdf_path.with_suffix(".png"))
    print("Done.")


if __name__ == "__main__":
    main()
