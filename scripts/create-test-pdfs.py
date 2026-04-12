#!/usr/bin/env python3
"""Generate test PDF documents for WOO Buddy development.

Creates 5 realistic Dutch government documents with various entity types
for testing privacy redaction functionality.

Usage:
    python scripts/create-test-pdfs.py

Output goes to tests/fixtures/
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("fpdf2 is required. Install with: pip install fpdf2")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def make_pdf() -> FPDF:
    """Return a pre-configured FPDF instance."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)
    return pdf


def _header(pdf: FPDF, gemeente: str, kenmerk: str, datum: str, onderwerp: str) -> None:
    """Add a standard municipality letter header."""
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Gemeente {gemeente}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Postbus 16200, 3500 CE {gemeente}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Telefoon: 030-286 00 00", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(40, 6, "Kenmerk:", new_x="RIGHT")
    pdf.cell(0, 6, kenmerk, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(40, 6, "Datum:", new_x="RIGHT")
    pdf.cell(0, 6, datum, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(40, 6, "Onderwerp:", new_x="RIGHT")
    pdf.cell(0, 6, onderwerp, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)


def create_besluit_brief(output_dir: Path) -> None:
    """1. Simple letter with private citizen data (Tier 1 targets)."""
    pdf = make_pdf()
    _header(
        pdf,
        gemeente="Utrecht",
        kenmerk="BZ-2024-04518",
        datum="14 maart 2024",
        onderwerp="Besluit op uw Woo-verzoek d.d. 12 januari 2024",
    )

    pdf.set_font("Helvetica", "", 10)
    lines = [
        "Geachte heer Van der Berg,",
        "",
        "Op 12 januari 2024 hebben wij uw verzoek ontvangen op grond van de Wet open",
        "overheid (Woo). U verzoekt om openbaarmaking van documenten betreffende de",
        "herinrichting van de Kerkstraat en omgeving.",
        "",
        "Uw gegevens zoals bij ons bekend:",
        "",
        "    Naam:           dhr. Jan van der Berg",
        "    BSN:            123456782",
        "    Adres:          Kerkstraat 42",
        "    Postcode:       3511 LX Utrecht",
        "    Telefoon:       06-12345678",
        "    E-mail:         j.vanderberg@gmail.com",
        "",
        "Na zorgvuldige beoordeling van uw verzoek heb ik besloten de gevraagde",
        "documenten gedeeltelijk openbaar te maken. Een aantal passages is gelakt",
        "op grond van artikel 5.1, tweede lid, aanhef en onder e, van de Woo",
        "(de eerbiediging van de persoonlijke levenssfeer).",
        "",
        "De heer Van der Berg heeft op 20 februari 2024 telefonisch contact opgenomen",
        "met onze medewerker om nadere toelichting te vragen. In dat gesprek is",
        "afgesproken dat de stukken per post naar bovenstaand adres worden verzonden.",
        "",
        "Indien u het niet eens bent met dit besluit, kunt u binnen zes weken na",
        "de datum van verzending van dit besluit een bezwaarschrift indienen bij",
        "het college van burgemeester en wethouders van de gemeente Utrecht.",
        "",
        "Met vriendelijke groet,",
        "",
        "Namens het college van burgemeester en wethouders,",
        "",
        "",
        "mw. C.J. Vermeer",
        "Afdelingshoofd Juridische Zaken",
    ]
    for line in lines:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    path = output_dir / "besluit_brief.pdf"
    pdf.output(str(path))
    print(f"  Created {path.name}")


def create_besluit_ambtenaar(output_dir: Path) -> None:
    """2. Official decision signed by public officials (should NOT redact names)."""
    pdf = make_pdf()
    _header(
        pdf,
        gemeente="Amsterdam",
        kenmerk="WOO-2024-0892",
        datum="28 februari 2024",
        onderwerp="Besluit op Woo-verzoek inzake woningbouwproject Zuidas",
    )

    pdf.set_font("Helvetica", "", 10)
    lines = [
        "Het college van burgemeester en wethouders van de gemeente Amsterdam,",
        "",
        "Overwegende dat:",
        "",
        "- op 5 januari 2024 een verzoek is ontvangen op grond van de Wet open overheid;",
        "- het verzoek betrekking heeft op documenten inzake het woningbouwproject Zuidas;",
        "- wethouder P.M. de Vries het dossier persoonlijk heeft beoordeeld;",
        "- de gemeenteraad op 15 februari 2024 is ge\xefnformeerd door raadslid",
        "  dhr. K.L. Jansen (D66) en raadslid mw. F.A. \xd6zt\xfcrk (GroenLinks);",
        "",
        "Besluit:",
        "",
        "1. De gevraagde documenten gedeeltelijk openbaar te maken conform de bij",
        "   dit besluit gevoegde inventarislijst.",
        "2. De in de inventarislijst genoemde weigeringsgronden toe te passen.",
        "",
        "Burgemeester en wethouders hebben dit besluit genomen in hun vergadering",
        "van 25 februari 2024.",
        "",
        "Dit besluit is voorbereid door de afdeling Bestuurszaken onder",
        "verantwoordelijkheid van gemeentesecretaris A.B. Bakker.",
        "",
        "",
        "Hoogachtend,",
        "",
        "namens het college van burgemeester en wethouders van Amsterdam,",
        "",
        "",
        "",
        "P.M. de Vries                          A.B. Bakker",
        "Wethouder Ruimtelijke Ordening          Gemeentesecretaris",
        "",
        "",
        "Bijlage: Inventarislijst (3 pagina's)",
    ]
    for line in lines:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    path = output_dir / "besluit_ambtenaar.pdf"
    pdf.output(str(path))
    print(f"  Created {path.name}")


def create_email_mixed(output_dir: Path) -> None:
    """3. Email thread with mixed entity types (IBANs, plates, DOBs, etc.)."""
    pdf = make_pdf()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "E-mailcorrespondentie - Dossier WOO-2024-1137", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Email 1
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Van: m.devries@amsterdam.nl", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Aan: subsidies@amsterdam.nl", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Datum: 10 januari 2024 14:32", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Onderwerp: Subsidieaanvraag Stichting Buurtzorg Noord", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    email1 = [
        "Beste collega's,",
        "",
        "Hierbij stuur ik de subsidieaanvraag door van Stichting Buurtzorg Noord.",
        "De aanvrager is mw. Fatima El Amrani (geboortedatum: 15-03-1985).",
        "",
        "Bankgegevens voor de uitbetaling:",
        "    IBAN: NL91ABNA0417164300",
        "    t.n.v. Stichting Buurtzorg Noord",
        "    KvK-nummer: 87654321",
        "",
        "Mw. El Amrani is bereikbaar op f.elamrani@buurtzorgnoord.nl of via",
        "telefoon 020-6234567.",
        "",
        "Het kenteken van het bedrijfsbusje dat voor het project wordt ingezet",
        "is AB-123-CD.",
        "",
        "Graag beoordeling door het hoofd subsidies, dhr. R.W. Hendriks.",
        "",
        "Met vriendelijke groet,",
        "Marieke de Vries",
        "Beleidsmedewerker Sociaal Domein",
    ]
    for line in email1:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # Email 2 (reply)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Van: r.hendriks@amsterdam.nl", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Aan: m.devries@amsterdam.nl", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "CC: directie@amsterdam.nl", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Datum: 11 januari 2024 09:15", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Onderwerp: RE: Subsidieaanvraag Stichting Buurtzorg Noord", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    email2 = [
        "Beste Marieke,",
        "",
        "Dank voor het doorsturen. Ik heb de aanvraag bekeken. De BSN van",
        "mevrouw El Amrani (999999990) is geverifieerd in het BRP.",
        "",
        "De aanvraag voldoet aan de voorwaarden. Ik adviseer positief.",
        "Het subsidiebedrag van EUR 45.000 kan worden overgemaakt naar",
        "bovengenoemd IBAN.",
        "",
        "Wethouder De Groot is akkoord (zie bijgevoegd mandaatbesluit).",
        "",
        "Groet,",
        "Rob Hendriks",
        "Hoofd Subsidies",
    ]
    for line in email2:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    path = output_dir / "email_mixed.pdf"
    pdf.output(str(path))
    print(f"  Created {path.name}")


def create_nota_gezondheid(output_dir: Path) -> None:
    """4. Document with health/sensitive data (Art. 5.1.1d absolute grounds)."""
    pdf = make_pdf()
    _header(
        pdf,
        gemeente="Rotterdam",
        kenmerk="JZ-2024-0234",
        datum="5 maart 2024",
        onderwerp="Interne nota: Beoordeling bijzondere bijstandsaanvraag",
    )

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "VERTROUWELIJK", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 10)
    lines = [
        "Aan: Team Bijzondere Bijstand",
        "Van: Casemanager S. van Dijk",
        "",
        "Betreft: Aanvraag bijzondere bijstand voor medische kosten",
        "Cli\xebnt: dhr. Mohammed Al-Hassan (BSN: 123456782)",
        "",
        "1. Situatieschets",
        "",
        "Betrokkene is een 52-jarige man, woonachtig aan de Mathenesserweg 88,",
        "3027 RJ Rotterdam. Hij is sinds 2019 bekend als diabetespati\xebnt (type 2)",
        "en staat onder behandeling bij het Erasmus MC.",
        "",
        "Uit het intakegesprek op 1 februari 2024 is gebleken dat betrokkene",
        "lid is van de Islamitische Stichting Rotterdam en daar wekelijks",
        "activiteiten bijwoont. Dit is relevant voor de beoordeling van zijn",
        "sociale netwerk en participatiemogelijkheden.",
        "",
        "2. Medische onderbouwing",
        "",
        "De huisarts, dr. E.M. Groen (AGB-code: 01-123456), heeft verklaard",
        "dat betrokkene naast diabetes ook kampt met chronische rugklachten",
        "waarvoor fysiotherapie is ge\xefndiceerd.",
        "",
        "De medisch adviseur van de gemeente, dhr. dr. P. Willemsen, heeft",
        "de medische stukken beoordeeld en onderschrijft de noodzaak van de",
        "aangevraagde voorzieningen.",
        "",
        "3. Financi\xeble gegevens",
        "",
        "    Netto maandinkomen:    EUR 1.285,00 (Participatiewet-uitkering)",
        "    Maandelijkse zorgkosten: EUR 340,00",
        "    IBAN:                  NL02RABO0123456789",
        "",
        "4. Advies",
        "",
        "Gelet op de medische situatie en de financi\xeble draagkracht adviseer",
        "ik de aanvraag toe te wijzen voor een bedrag van EUR 2.400 per jaar.",
        "",
        "S. van Dijk",
        "Casemanager Werk & Inkomen",
    ]
    for line in lines:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    path = output_dir / "nota_gezondheid.pdf"
    pdf.output(str(path))
    print(f"  Created {path.name}")


def create_edge_cases(output_dir: Path) -> None:
    """5. Document with edge cases for entity detection."""
    pdf = make_pdf()
    _header(
        pdf,
        gemeente="Den Haag",
        kenmerk="BWT-2024-7891",
        datum="20 maart 2024",
        onderwerp="Verslag bestuurlijk overleg herinrichting marktgebied",
    )

    pdf.set_font("Helvetica", "", 10)
    lines = [
        "Aanwezig:",
        "- De directeur Stadsontwikkeling (voorzitter)",
        "- Dhr. Kees de Kok, bewonersvertegenwoordiger",
        "- Mw. Anna van den Berg-Mulder, wijkraadslid",
        "- De projectleider (notulen)",
        "",
        "1. Opening",
        "",
        "De directeur heeft besloten het overleg te openen met een terugblik",
        "op de voortgang. De voorzitter merkt op dat het project op schema ligt.",
        "",
        "2. Stand van zaken marktgebied",
        "",
        "De projectleider meldt dat aannemer Bouwbedrijf De Kok & Zonen B.V.",
        "(KvK-nummer: 12345678) de werkzaamheden volgens planning uitvoert.",
        "Het bedrijf is gevestigd aan de Laan van Meerdervoort 200, 2517 BJ",
        "Den Haag.",
        "",
        "NB: Het KvK-nummer betreft een openbaar handelsregistergegeven en",
        "valt niet onder de bescherming van de Woo.",
        "",
        "3. Bewonersparticipatie",
        "",
        "Dhr. De Kok geeft aan dat de bewoners van de Kerkstraat ontevreden",
        "zijn over de communicatie. Hij noemt specifiek de overlast voor",
        "mevrouw De Bruin op huisnummer 14 en de heer Bakker op nummer 22.",
        "",
        "De wijkmanager heeft toegezegd een bewonersbrief te sturen. De tekst",
        "wordt opgesteld door de communicatieadviseur.",
        "",
        "4. Financi\xebn",
        "",
        "Het projectbudget bedraagt EUR 2.3 miljoen. De gemeente heeft een",
        "subsidie ontvangen van de provincie Zuid-Holland (beschikkingsnummer",
        "PZH-2024-00456123).",
        "",
        "De penningmeester van de bewonersvereniging, dhr. Willem de Groot,",
        "vraagt of de bijdrage van EUR 15.000 al is overgemaakt. De",
        "projectleider bevestigt dat dit op 15 maart is gebeurd.",
        "",
        "5. Rondvraag en sluiting",
        "",
        "Mw. Van den Berg-Mulder vraagt aandacht voor de toegankelijkheid",
        "van het marktplein voor mindervaliden. De architect zal dit meenemen",
        "in het definitief ontwerp.",
        "",
        "De volgende vergadering is gepland op 17 april 2024 om 14:00 uur.",
        "",
        "De directeur sluit de vergadering om 16:15 uur.",
        "",
        "",
        "Vastgesteld in de vergadering van 17 april 2024.",
    ]
    for line in lines:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    path = output_dir / "edge_cases.pdf"
    pdf.output(str(path))
    print(f"  Created {path.name}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating test PDFs in {OUTPUT_DIR}/\n")

    create_besluit_brief(OUTPUT_DIR)
    create_besluit_ambtenaar(OUTPUT_DIR)
    create_email_mixed(OUTPUT_DIR)
    create_nota_gezondheid(OUTPUT_DIR)
    create_edge_cases(OUTPUT_DIR)

    print(f"\nDone. {len(list(OUTPUT_DIR.glob('*.pdf')))} PDFs created.")


if __name__ == "__main__":
    main()
