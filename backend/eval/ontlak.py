#!/usr/bin/env python3
"""Ontlak: turn a published (already-redacted) Woo PDF into a test document.

The idea: a published Woo document is real in every respect except that the
personal data has been removed. Its layout, fonts, boilerplate, tables and
prose are exactly what a reviewer sees in the wild -- only the interesting
bits are gone. So instead of inventing documents from scratch, we find the
holes the redactor left, work out from context what kind of value used to sit
there, and drop in a realistic *fictional* value of that type.

That gives two things a synthetic fixture cannot:
  1. real document structure, so the detector is tested on real layout;
  2. exact ground truth, because we know what we inserted and where.

No real personal data is ever read back or reused. Only the *type* of the
missing value is inferred; the value itself is generated.

Usage:
    ./ontlak.py input.pdf [more.pdf ...] --out-dir ontlakt/
    ./ontlak.py input.pdf --seed 42 --off-list-ratio 0.4

Writes, per input:
    <out-dir>/<stem>-ontlakt.pdf     the filled document
    <out-dir>/<stem>-ontlakt.json    ground truth (page, bbox, type, value)
                                     plus `unknown_zones`: places we know
                                     something was removed but could not say
                                     what, so the evaluator can hold its fire.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Run as a script from anywhere: make the sibling helper importable first.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    sys.exit("PyMuPDF ontbreekt: pip install pymupdf")

from pdfio import fullpage_image  # noqa: E402, I001


# --------------------------------------------------------------------------
# Slot detection
# --------------------------------------------------------------------------

# Labels that, when a line contains nothing but the label, mark a value the
# redactor removed. The captured group decides the type.
EMPTY_LABEL = re.compile(
    r"^(?P<label>"
    r"Van|Aan|CC|Bcc|Verzonden|T\.?a\.?v\.?|Betreft|"
    r"Behandeld door|Contactpersoon|Behandelaar|Ondertekend door|"
    r"Telefoon(?:nummer)?|Telefoonnr|Tel|Doorkiesnummer|Mobiel|"
    r"E-?mail(?:adres)?|Mailadres|"
    r"Naam|Voornaam|Achternaam|Initialen|"
    r"Adres|Straat|Woonplaats|Postcode|Postadres|"
    r"IBAN|Rekeningnummer|Bankrekening|"
    r"BSN|Burgerservicenummer|"
    r"Geboortedatum|Geboorteplaats|"
    r"Geachte(?:\s+(?:heer|mevrouw|heer/mevrouw))?|Beste|"
    r"Met vriendelijke groet|Hoogachtend|Handtekening|Functie"
    r")\s*[:,]?\s*$",
    re.IGNORECASE,
)

# When a gap sits mid-line, the text to its left decides the type.
LEFT_CONTEXT = [
    (re.compile(r"(?i)\b(iban|rekeningnummer|bankrekening)\b\W*$"), "iban"),
    (re.compile(r"(?i)\b(bsn|burgerservicenummer|sofinummer)\b\W*$"), "bsn"),
    (re.compile(r"(?i)\b(e-?mail|mailadres|@)\W*$"), "email"),
    (re.compile(r"(?i)\b(tel|telefoon|doorkies|mobiel|gsm|t)\W*$"), "telefoon"),
    (re.compile(r"(?i)\b(postcode)\W*$"), "postcode_plaats"),
    (re.compile(r"(?i)\b(adres|straat|woonachtig aan de|wonende aan)\W*$"), "adres"),
    (re.compile(r"(?i)\b(geachte heer|geachte mevrouw|geachte)\W*$"), "achternaam"),
    (re.compile(r"(?i)\b(beste|hallo|hoi|dag)\W*$"), "voornaam"),
    (re.compile(r"(?i)\b(van|aan|cc|bcc)\s*:\W*$"), "email_met_naam"),
    (re.compile(r"(?i)\b(de heer|mevrouw|dhr\.?|mevr\.?|mw\.?)\W*$"), "achternaam"),
    (re.compile(r"(?i)\b(kenteken)\W*$"), "kenteken"),
    (re.compile(r"(?i)\b(geboren op|geboortedatum)\W*$"), "geboortedatum"),
    (re.compile(r"(?i)\b(kvk|kamer van koophandel)\W*$"), "kvk"),
]

LABEL_TO_TYPE = {
    "van": "email_met_naam",
    "aan": "email_met_naam",
    "cc": "email_met_naam",
    "bcc": "email_met_naam",
    "t.a.v.": "volledige_naam",
    "tav": "volledige_naam",
    "behandeld door": "volledige_naam",
    "contactpersoon": "volledige_naam",
    "behandelaar": "volledige_naam",
    "ondertekend door": "volledige_naam",
    "naam": "volledige_naam",
    "handtekening": "volledige_naam",
    "met vriendelijke groet": "volledige_naam",
    "hoogachtend": "volledige_naam",
    "voornaam": "voornaam",
    "achternaam": "achternaam",
    "initialen": "initialen",
    "geachte": "achternaam",
    "geachte heer": "achternaam",
    "geachte mevrouw": "achternaam",
    "geachte heer/mevrouw": "achternaam",
    "beste": "voornaam",
    "telefoon": "telefoon",
    "telefoonnummer": "telefoon",
    "telefoonnr": "telefoon",
    "tel": "telefoon",
    "doorkiesnummer": "telefoon",
    "mobiel": "mobiel",
    "email": "email",
    "e-mail": "email",
    "emailadres": "email",
    "e-mailadres": "email",
    "mailadres": "email",
    "adres": "adres",
    "straat": "adres",
    "postadres": "adres",
    "postcode": "postcode_plaats",
    "woonplaats": "woonplaats",
    "iban": "iban",
    "rekeningnummer": "iban",
    "bankrekening": "iban",
    "bsn": "bsn",
    "burgerservicenummer": "bsn",
    "geboortedatum": "geboortedatum",
    "geboorteplaats": "woonplaats",
    "functie": "functie",
    "betreft": None,  # not personal data
    "verzonden": None,
}


@dataclass
class Slot:
    page: int
    x: float
    y: float  # text baseline
    bbox: tuple[float, float, float, float]
    kind: str  # empty_label | gap | blackbox
    type: str
    max_width: float
    fontsize: float
    #: The font of the surrounding text. Recorded for diagnosis only: values
    #: are written in one embedded Unicode TrueType face (see FONT_CANDIDATES),
    #: because matching the original family costs the diacritics.
    font: str
    context: str
    bar: tuple[float, float, float, float] | None = None


@dataclass
class UnknownZone:
    """A place where something was removed but we cannot say what.

    Three things end up here: a bar whose surrounding text says nothing
    (`no_context`), a slot too narrow to hold a realistic value
    (`too_narrow`), and a whole scanned page (`scanned_page`). None of them
    get a ground-truth value — guessing would make the truth lie — but the
    evaluator still needs to know about them, because a detection landing on
    such a zone is neither a hit nor a false positive: it is a detection on
    material we deliberately left blank.
    """

    page: int  # 1-based
    bbox: tuple[float, float, float, float]
    reason: str  # no_context | too_narrow | scanned_page


def _luminance(color) -> float | None:
    if color is None:
        return None
    if isinstance(color, (int, float)):
        return float(color)
    return sum(color) / len(color)


def _is_redaction_fill(color) -> bool:
    """Redactors use black bars, but grey ones are just as common."""
    lum = _luminance(color)
    return lum is not None and lum < 0.93


def redaction_bars(page) -> list[fitz.Rect]:
    """Every filled bar on the page that looks like a redaction mark.

    Zebra striping in tables has the same shape and colour as a redaction bar,
    so anything spanning most of the text column is rejected.
    """
    bars = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if not _is_redaction_fill(drawing.get("fill")):
            continue
        if rect.width < 12 or not (4 < rect.height < 40):
            continue
        if rect.width > 0.55 * page.rect.width:  # table row shading
            continue
        bars.append(rect)
    return bars


def address_block(page, bars: list[fitz.Rect]) -> list[tuple[int, str]]:
    """Bars stacked at the top-left of a letter are the addressee's NAW block.

    Nothing sits to their left, so the context probe finds nothing -- but the
    position is unambiguous, and a name/street/postcode block is exactly the
    material a reviewer has to redact.
    """
    top = page.rect.height * 0.42
    left = page.rect.width * 0.55
    column = sorted(
        (i for i, r in enumerate(bars) if r.y1 < top and r.x0 < left),
        key=lambda i: bars[i].y0,
    )
    if len(column) < 2:
        return []
    # keep only bars that line up vertically with the first one
    x0 = bars[column[0]].x0
    column = [i for i in column if abs(bars[i].x0 - x0) < 25]
    if len(column) < 2:
        return []
    # naam / straat / postcode+plaats -- a fourth bar is usually a "t.a.v."
    # or company line, not a second town, so it gets a name too.
    shape = ["volledige_naam", "adres", "postcode_plaats", "volledige_naam"]
    return [(i, shape[min(n, len(shape) - 1)]) for n, i in enumerate(column[:4])]


def find_slots(doc) -> tuple[list[Slot], list[UnknownZone]]:
    slots: list[Slot] = []
    unknown: list[UnknownZone] = []
    for pno, page in enumerate(doc):
        if fullpage_image(page):
            r = page.rect
            unknown.append(UnknownZone(pno + 1, (r.x0, r.y0, r.x1, r.y1), "scanned_page"))
            continue
        page_right = page.rect.x1 - 40
        bars = redaction_bars(page)
        used_bars: set[int] = set()

        # `bars`/`used_bars` are bound as defaults rather than closed over:
        # both are rebound on every page, and a closure would silently read
        # the *last* page's bars if these helpers ever outlived the iteration.
        def bar_after(
            x: float, y: float, bars: list = bars, used_bars: set = used_bars
        ) -> fitz.Rect | None:
            """The redaction bar this slot sits in, if the redactor drew one."""
            best, best_i = None, None
            for i, r in enumerate(bars):
                if (
                    r.y0 - 3 <= y <= r.y1 + 3
                    and r.x1 > x - 2
                    and r.x0 < x + 60
                    and (best is None or r.x0 < best.x0)
                ):
                    best, best_i = r, i
            if best_i is not None:
                used_bars.add(best_i)
            return best

        def bar_below(
            x: float,
            y: float,
            size: float,
            bars: list = bars,
            used_bars: set = used_bars,
        ) -> fitz.Rect | None:
            """A sidebar label ("Contactpersoon") carries its value underneath."""
            best, best_i = None, None
            for i, r in enumerate(bars):
                if i in used_bars or abs(r.x0 - x) > 30:
                    continue
                if y < r.y0 < y + size * 2.6 and (best is None or r.y0 < best.y0):
                    best, best_i = r, i
            if best_i is not None:
                used_bars.add(best_i)
            return best

        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in line["spans"]).strip()

                # (a) the whole line is a label -> value removed behind it
                m = EMPTY_LABEL.match(text)
                if m:
                    label = m.group("label").lower().rstrip(":, ")
                    typ = LABEL_TO_TYPE.get(label, "volledige_naam")
                    if typ is None:
                        continue
                    last = spans[-1]
                    # "Met vriendelijke groet" signs off on the *next* line
                    dy = (
                        last["size"] * 1.35
                        if label in {"met vriendelijke groet", "hoogachtend"}
                        else 0.0
                    )
                    x = last["bbox"][0] if dy else last["bbox"][2] + last["size"] * 0.35
                    y = last["origin"][1] + dy
                    bar = bar_after(x, y)
                    if bar is None:
                        # value on the next line: sidebar labels, sign-offs
                        below = bar_below(spans[0]["bbox"][0], last["bbox"][3], last["size"])
                        if below is not None:
                            bar = below
                            y = below.y1 - below.height * 0.25
                            x = below.x0 + 1
                    # A bar tells us exactly how much room the value had. Without
                    # one, stop at the right margin.
                    right = bar.x1 if bar else page_right
                    if bar and bar.x0 > x:
                        x = bar.x0 + 1
                    slots.append(
                        Slot(
                            page=pno,
                            x=x,
                            y=y,
                            bbox=(x, last["bbox"][1] + dy, right, last["bbox"][3] + dy),
                            kind="empty_label",
                            type=typ,
                            max_width=max(right - x, 0),
                            fontsize=last["size"],
                            font=last["font"],
                            context=text[:60],
                            bar=tuple(bar) if bar else None,
                        )
                    )
                    continue

                # (b) an unusually wide gap between two spans on one baseline
                for a, b in zip(spans, spans[1:], strict=False):
                    gap = b["bbox"][0] - a["bbox"][2]
                    if gap <= 4 * (a["size"] or 10) * 0.5:
                        continue
                    left = "".join(s["text"] for s in spans[: spans.index(a) + 1])[-40:]
                    typ = next((t for rx, t in LEFT_CONTEXT if rx.search(left)), None)
                    if typ is None:
                        continue
                    x = a["bbox"][2] + a["size"] * 0.35
                    bar = bar_after(x, a["origin"][1])
                    slots.append(
                        Slot(
                            page=pno,
                            x=x,
                            y=a["origin"][1],
                            bbox=(a["bbox"][2], a["bbox"][1], b["bbox"][0], a["bbox"][3]),
                            kind="gap",
                            type=typ,
                            # never write past the span that follows the gap, nor
                            # past the bar the redactor drew
                            max_width=min(b["bbox"][0], bar.x1 if bar else b["bbox"][0])
                            - x
                            - a["size"] * 0.25,
                            fontsize=a["size"],
                            font=a["font"],
                            context=left,
                            bar=tuple(bar) if bar else None,
                        )
                    )

        # (c) bars nothing else claimed: a value removed without a text anchor
        naw = dict(address_block(page, bars))
        for i, rect in enumerate(bars):
            if i in used_bars:
                continue
            typ = naw.get(i) or _type_from_neighbourhood(page, rect)
            if typ is None:
                # Nothing in the surrounding text says what was removed. It may
                # not even have been personal data ("werkdagen: <redacted>"), so
                # leaving the bar alone keeps the ground truth honest. It does
                # become an unknown zone: a detector firing here is judging
                # material we never scored.
                unknown.append(
                    UnknownZone(pno + 1, (rect.x0, rect.y0, rect.x1, rect.y1), "no_context")
                )
                continue
            slots.append(
                Slot(
                    page=pno,
                    x=rect.x0 + 1,
                    y=rect.y1 - rect.height * 0.25,
                    bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                    kind="blackbox",
                    type=typ,
                    max_width=rect.width - 2,
                    fontsize=min(rect.height * 0.72, 11),
                    font="helv",
                    context="",
                    bar=tuple(rect),
                )
            )
    return slots, unknown


def _type_from_neighbourhood(page, rect) -> str | None:
    """Read the text just left of a bar to work out what it covered.

    Returns None when the context says nothing -- guessing there would put a
    value in the ground truth that the redactor never removed.
    """
    probe = fitz.Rect(max(page.rect.x0, rect.x0 - 170), rect.y0 - 2, rect.x0, rect.y1 + 2)
    left = page.get_textbox(probe).replace("\n", " ").strip()[-40:]
    return next((typ for rx, typ in LEFT_CONTEXT if rx.search(left)), None)


# --------------------------------------------------------------------------
# Fictional but realistic Dutch values
# --------------------------------------------------------------------------

# Surnames that are common in the Netherlands but absent from the seed CBS
# list the detector ships. These are the interesting half of the test: they
# are what a wordlist-backed detector is most likely to miss.
OFF_LIST_ACHTERNAMEN = [
    "El Haddaoui",
    "Bouzambou",
    "Ait Mansour",
    "Öztürk",
    "Yıldırım",
    "Kowalczyk",
    "Nowakowski",
    "Okonkwo",
    "Adjei",
    "Ramdhani",
    "Sitaldin",
    "Pengel",
    "Codrington",
    "Djojosoeparto",
    "Wongsoredjo",
    "Van der Meulen-Bakx",
    "Terlouw-Van Rossem",
    "De Jong-Mbeki",
    "Ferreira Lopes",
    "Nguyen Van",
    "Kaczmarek",
    "Grabowska",
    "Beširević",
    "Hadžić",
    "Papadopoulos",
    "Fernandes Pinto",
]
OFF_LIST_VOORNAMEN = [
    "Yassine",
    "Oumaima",
    "Berkant",
    "Elif",
    "Kwabena",
    "Shaniqua",
    "Radoslaw",
    "Iwona",
    "Amira",
    "Ilyas",
    "Sanne-Marijke",
    "Jort-Jan",
    "Mohammed-Amin",
    "Roshana",
    "Dewi",
    "Thijmen",
    "Fenna",
    "Djaimy",
]
TUSSENVOEGSELS = ["", "", "", "van", "van der", "de", "van den", "ter", "in 't"]

STRATEN = [
    "Westerbrink",
    "Groningerstraat",
    "Beilerstraat",
    "Molenstraat",
    "Kerkweg",
    "Hoofdstraat",
    "Julianalaan",
    "Emmastraat",
    "Sluisweg",
    "Industrieweg",
    "Vaart Noordzijde",
    "Brink",
    "Havenkade",
    "Schoolpad",
]
PLAATSEN = [
    ("9401", "AC", "Assen"),
    ("7811", "AA", "Emmen"),
    ("7902", "NP", "Hoogeveen"),
    ("9401", "KA", "Assen"),
    ("7941", "LA", "Meppel"),
    ("9331", "PA", "Norg"),
    ("7751", "CB", "Dalen"),
    ("9471", "AC", "Zuidlaren"),
]
BURGERDOMEINEN = ["gmail.com", "hotmail.com", "outlook.com", "ziggo.nl", "kpnmail.nl"]
OVERHEIDSDOMEINEN = [
    "drenthe.nl",
    "assen.nl",
    "emmen.nl",
    "hoogeveen.nl",
    "coevorden.nl",
    "minienw.nl",
    "rvo.nl",
    "odgroningen.nl",
]
FUNCTIES = [
    "senior beleidsmedewerker",
    "toezichthouder Ontgrondingenwet",
    "juridisch adviseur",
    "vergunningverlener",
    "projectleider gebiedsontwikkeling",
    "medewerker Klantcontactcentrum",
    "handhavingsjurist",
]


def _strip(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )


class FakeFactory:
    """Generates fictional values and records whether they are wordlist hits."""

    def __init__(self, data_dir: Path, rng: random.Random, off_list_ratio: float):
        self.rng = rng
        self.off_list_ratio = off_list_ratio
        self.voornamen = self._load(data_dir / "Top_eerste_voornamen_NL_2017.csv")
        self.achternamen = self._load(data_dir / "cbs_achternamen.csv")
        self.vn_set = {_strip(n) for n in self.voornamen}
        self.an_set = {_strip(n) for n in self.achternamen}

    @staticmethod
    def _load(path: Path) -> list[str]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line.split(",")[0].strip())
        return out

    # -- name pieces -------------------------------------------------------
    def voornaam(self) -> str:
        if self.rng.random() < self.off_list_ratio or not self.voornamen:
            return self.rng.choice(OFF_LIST_VOORNAMEN)
        return self.rng.choice(self.voornamen)

    def achternaam(self) -> str:
        if self.rng.random() < self.off_list_ratio or not self.achternamen:
            return self.rng.choice(OFF_LIST_ACHTERNAMEN)
        tv = self.rng.choice(TUSSENVOEGSELS)
        base = self.rng.choice(self.achternamen)
        return f"{tv} {base}".strip()

    def in_wordlist(self, value: str) -> bool:
        parts = [_strip(p) for p in re.split(r"[\s\-]+", value) if p]
        return any(p in self.vn_set or p in self.an_set for p in parts)

    # -- typed values ------------------------------------------------------
    def make(self, typ: str) -> str:
        r = self.rng
        if typ == "voornaam":
            return self.voornaam()
        if typ == "achternaam":
            return self.achternaam()
        if typ == "initialen":
            return f"{r.choice('ABCDEFGHJKLMPRSTVW')}.{r.choice('ABCDEFGHJKLMPRSTVW')}."
        if typ == "volledige_naam":
            return f"{self.voornaam()} {self.achternaam()}"
        if typ == "functie":
            return r.choice(FUNCTIES)
        if typ == "email":
            return self._email()
        if typ == "email_met_naam":
            vn, an = self.voornaam(), self.achternaam()
            mail = self._email(vn, an)
            return f"{vn} {an} <{mail}>" if r.random() < 0.6 else mail
        if typ == "telefoon":
            return r.choice(
                [
                    f"(0592) 36 {r.randint(10, 99)} {r.randint(10, 99)}",
                    f"0592-{r.randint(300000, 399999)}",
                    f"088 {r.randint(100, 999)} {r.randint(1000, 9999)}",
                ]
            )
        if typ == "mobiel":
            # Both alternatives are built before `choice` picks one, exactly as
            # they were when the list was written inline. Draw order is part of
            # the seed contract: change it and every later value shifts.
            nul_zes = f"06-{r.randint(10000000, 59999999)}"
            g1, g2, g3, g4 = (
                r.randint(10, 59),
                r.randint(10, 99),
                r.randint(10, 99),
                r.randint(10, 99),
            )
            return r.choice([nul_zes, f"+31 6 {g1} {g2} {g3} {g4}"])
        if typ == "adres":
            straat = r.choice(STRATEN)
            nummer = r.randint(1, 189)
            return f"{straat} {nummer}{r.choice(['', '', '', 'a', 'B', '-2'])}"
        if typ == "postcode_plaats":
            pc4, pc2, plaats = r.choice(PLAATSEN)
            return f"{pc4} {pc2} {plaats}"
        if typ == "postcode":
            pc4, pc2, _ = r.choice(PLAATSEN)
            return f"{pc4} {pc2}"
        if typ == "woonplaats":
            return r.choice(PLAATSEN)[2]
        if typ == "iban":
            return self._iban()
        if typ == "bsn":
            return self._bsn()
        if typ == "geboortedatum":
            return f"{r.randint(1, 28)}-{r.randint(1, 12):02d}-{r.randint(1955, 2004)}"
        if typ == "kenteken":
            letter = r.choice("GHJKLNPRST")
            cijfers = r.randint(100, 999)
            return f"{letter}-{cijfers}-{r.choice('BDFGHJ')}{r.choice('BDFGHJ')}"
        if typ == "kvk":
            return str(r.randint(10000000, 89999999))
        return self.make("volledige_naam")

    def _email(self, vn: str | None = None, an: str | None = None) -> str:
        r = self.rng
        vn = vn or self.voornaam()
        an = an or self.achternaam()
        slug_v = _strip(vn).replace(" ", "").replace("'", "")
        slug_a = _strip(an).replace(" ", "").replace("'", "")
        local = r.choice([f"{slug_v}.{slug_a}", f"{slug_v[0]}.{slug_a}", f"{slug_v}{slug_a[0]}"])
        domain = r.choice(OVERHEIDSDOMEINEN if r.random() < 0.6 else BURGERDOMEINEN)
        return f"{local}@{domain}"

    def _bsn(self) -> str:
        """Elfproef-valid, so a validating Tier 1 regex must accept it."""
        while True:
            d = [self.rng.randint(0, 9) for _ in range(8)]
            weights = [9, 8, 7, 6, 5, 4, 3, 2]
            total = sum(x * w for x, w in zip(d, weights, strict=True))
            last = total % 11
            if last < 10 and (total - last) % 11 == 0:
                digits = d + [last]
                if digits[0] != 0:
                    return "".join(map(str, digits))

    def _iban(self) -> str:
        bank = self.rng.choice(["INGB", "RABO", "ABNA", "TRIO", "SNSB", "BUNQ"])
        acct = f"{self.rng.randint(0, 10**10 - 1):010d}"
        body = f"{bank}{acct}NL00"
        num = "".join(str(int(c, 36)) for c in body)
        check = 98 - (int(num) % 97)
        return f"NL{check:02d} {bank} {acct[0:4]} {acct[4:8]} {acct[8:10]}"


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


#: Where to look for a font with a full Latin repertoire, in order. The
#: base-14 fonts are not an option: they are Latin-1 only, so `Yıldırım`
#: renders as `Y·ld·r·m` and the text layer hands the detector a name no
#: wordlist and no NER model will ever recognise. Half the point of the
#: fixture is that Dutch names carry Turkish, Slavic and Maghrebi diacritics,
#: so the font has to be embedded and it has to be Unicode.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",  # Fedora/Arch
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)

#: The name the embedded font gets inside the output PDF. One name for the
#: whole document means PyMuPDF embeds one subset, not one per insertion.
FONT_ALIAS = "ontlak"


def resolve_font(explicit: str | None) -> str:
    """Pick the TrueType file to write inserted values with.

    Fails loudly rather than falling back to a base-14 font: a silent fallback
    would produce a fixture that looks fine and quietly measures the detector
    against mangled names.
    """
    candidates = [explicit] if explicit else list(FONT_CANDIDATES)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    tried = "\n  ".join(c for c in candidates if c)
    sys.exit(
        f"geen Unicode-TrueType-font gevonden; geef er een op met --font.\ngeprobeerd:\n  {tried}"
    )


# When the redactor left a narrow slot, a full value will not fit. Fall back to
# a shorter value of a *related* type rather than truncating -- and record the
# type we actually wrote, so the ground truth never lies.
NARROW_FALLBACK = {
    "volledige_naam": "achternaam",
    "email_met_naam": "email",
    "achternaam": "initialen",
    "postcode_plaats": "postcode",
    "mobiel": "telefoon",
}


def _zone_of(slot: Slot, reason: str) -> UnknownZone:
    """The rectangle a skipped slot occupies, preferring the redactor's bar."""
    bbox = slot.bar if slot.bar else slot.bbox
    return UnknownZone(slot.page + 1, tuple(bbox), reason)  # type: ignore[arg-type]


def fill(
    doc,
    slots: list[Slot],
    factory: FakeFactory,
    fontfile: str,
    min_width: float = 24.0,
) -> tuple[list[dict], list[UnknownZone]]:
    truth: list[dict] = []
    unknown: list[UnknownZone] = []
    skipped = 0
    # Measure with the same font we write with, or the ground-truth bbox is a
    # base-14 width around a TrueType string.
    font = fitz.Font(fontfile=fontfile)
    for slot in slots:
        if slot.max_width < min_width:
            skipped += 1
            unknown.append(_zone_of(slot, "too_narrow"))
            continue

        typ = slot.type
        size = max(6.5, min(slot.fontsize or 9.5, 12))

        for _ in range(4):
            value = factory.make(typ)
            width = font.text_length(value, fontsize=size)
            trial = size
            while width > slot.max_width and trial > 6.0:
                trial -= 0.25
                width = font.text_length(value, fontsize=trial)
            if width <= slot.max_width:
                size = trial
                break
            nxt = NARROW_FALLBACK.get(typ)
            if nxt is None:
                value = None
                break
            typ = nxt
        else:
            value = None

        if value is None or width > slot.max_width:
            skipped += 1
            unknown.append(_zone_of(slot, "too_narrow"))
            continue

        page = doc[slot.page]
        # paint out the bar the redactor drew, so the page reads as an original
        if slot.bar:
            page.draw_rect(fitz.Rect(*slot.bar), color=None, fill=(1, 1, 1), overlay=True)
        page.insert_text(
            (slot.x, slot.y),
            value,
            fontname=FONT_ALIAS,
            fontfile=fontfile,
            fontsize=size,
            color=(0, 0, 0),
            overlay=True,
        )

        truth.append(
            {
                "page": slot.page + 1,
                "bbox": [
                    round(v, 2)
                    for v in (slot.x, slot.y - size, slot.x + width, slot.y + size * 0.25)
                ],
                "type": typ,
                "value": value,
                "slot_kind": slot.kind,
                "slot_type": slot.type,
                "context": slot.context,
                "in_wordlist": factory.in_wordlist(value) if "naam" in typ else None,
            }
        )
    if skipped:
        print(f"    ({skipped} slot(s) overgeslagen: te smal voor een realistische waarde)")
    return truth, unknown


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("ontlakt"))
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "app/data/sources",
        help="waar de Meertens/CBS-lijsten staan",
    )
    ap.add_argument("--seed", type=int, default=20260907)
    ap.add_argument(
        "--font",
        help=(
            "TrueType-bestand om ingevulde waarden mee te schrijven "
            f"(standaard de eerste van: {', '.join(FONT_CANDIDATES)})"
        ),
    )
    ap.add_argument(
        "--off-list-ratio",
        type=float,
        default=0.4,
        help="aandeel namen dat NIET in de woordenlijst staat (0-1)",
    )
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fontfile = resolve_font(args.font)
    print(f"font: {fontfile}")
    rng = random.Random(args.seed)
    factory = FakeFactory(args.data_dir, rng, args.off_list_ratio)
    if not factory.voornamen:
        print(f"let op: geen woordenlijsten gevonden in {args.data_dir}", file=sys.stderr)

    grand = 0
    for path in args.pdfs:
        doc = fitz.open(path)
        slots, unknown = find_slots(doc)
        truth, narrow = fill(doc, slots, factory, fontfile)
        unknown.extend(narrow)
        stem = path.stem
        out_pdf = args.out_dir / f"{stem}-ontlakt.pdf"
        out_json = args.out_dir / f"{stem}-ontlakt.json"
        doc.save(out_pdf, garbage=3, deflate=True)
        zones: list[dict[str, Any]] = [
            {
                "page": z.page,
                "bbox": [round(v, 2) for v in z.bbox],
                "reason": z.reason,
            }
            for z in unknown
        ]
        out_json.write_text(
            json.dumps(
                {
                    "bron": path.name,
                    "seed": args.seed,
                    "font": fontfile,
                    "off_list_ratio": args.off_list_ratio,
                    "aantal": len(truth),
                    "detections": truth,
                    "unknown_zones": zones,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        doc.close()

        kinds: dict[str, int] = {}
        for t in truth:
            kinds[t["type"]] = kinds.get(t["type"], 0) + 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
        print(f"{out_pdf.name}: {len(truth)} ingevuld  [{summary}]  {len(zones)} onbekende zone(s)")
        grand += len(truth)

    print(f"\ntotaal {grand} fictieve waarden over {len(args.pdfs)} document(en) -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
