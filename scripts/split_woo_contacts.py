"""Split Woo-contactpersoon rows into named individuals vs function inboxes.

Reads `backend/app/data/medewerkers_gemeenten.csv`, filters to rows where
Functie == "Woo-contactpersoon", and emits two CSVs alongside this script:
- woo_contacts_named.csv  — entries whose Naam looks like a person
- woo_contacts_inbox.csv  — entries whose Naam is a department/function label

Heuristic: a name is a person if it has initials (`X.` followed by another
letter or initial) OR a Dutch honorific prefix (Mw./Dhr./Mr./...) OR a known
tussenvoegsel pattern. Otherwise it is treated as a function inbox.

Usage: python scripts/split_woo_contacts.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "backend" / "app" / "data" / "medewerkers_gemeenten.csv"
OUT_NAMED = Path(__file__).resolve().parent / "woo_contacts_named.csv"
OUT_INBOX = Path(__file__).resolve().parent / "woo_contacts_inbox.csv"

HONORIFICS = re.compile(r"^\s*(Mw\.|Mevr\.|Dhr\.|Hr\.|Mr\.|Drs\.|Dr\.|Ing\.|Ir\.|Prof\.)", re.I)
INITIALS = re.compile(r"\b[A-Z]\.")
TUSSENVOEGSEL = re.compile(
    r"\b(van|de|den|der|ten|ter|te|op|in 't|in het|aan|bij)\s+[A-Z]",
)
FUNCTION_HINTS = re.compile(
    r"(woo|juridisch|secretari|klant|bestuur|communicatie|griffier|"
    r"informatie|documentatie|archief|team|afdeling|bureau|cluster|"
    r"co[oö]rdin|contactfunctionaris|frontoffice|backoffice|kcc|loket)",
    re.I,
)


def looks_like_person(naam: str) -> bool:
    name = naam.strip().strip('"')
    if not name:
        return False
    if HONORIFICS.search(name):
        return True
    initials = INITIALS.findall(name)
    if len(initials) >= 1 and re.search(r"[A-Z][a-z]{2,}", name):
        return True
    if TUSSENVOEGSEL.search(name):
        return True
    if FUNCTION_HINTS.search(name):
        return False
    tokens = [t for t in re.split(r"\s+", name) if t]
    if len(tokens) >= 2 and all(t[0:1].isupper() for t in tokens) and not any(t.lower() in {"en", "of"} for t in tokens):
        return True
    return False


def main() -> int:
    if not INPUT.exists():
        print(f"input not found: {INPUT}", file=sys.stderr)
        return 1

    named: list[dict[str, str]] = []
    inbox: list[dict[str, str]] = []

    with INPUT.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            if (row.get("Functie") or "").strip().strip('"') != "Woo-contactpersoon":
                continue
            keep = {
                "Gemeente": (row.get("Organisatie (onderdeel)") or "").strip().strip('"'),
                "Naam": (row.get("Naam") or "").strip().strip('"'),
                "Functie": (row.get("Functie") or "").strip().strip('"'),
                "TOOI": (row.get("Resource identifier v5.0 organisatie") or "").strip().strip('"'),
            }
            (named if looks_like_person(keep["Naam"]) else inbox).append(keep)

    fieldnames = ["Gemeente", "Naam", "Functie", "TOOI"]
    for path, rows in ((OUT_NAMED, named), (OUT_INBOX, inbox)):
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"named individuals: {len(named):>4}  -> {OUT_NAMED}")
    print(f"function inboxes:  {len(inbox):>4}  -> {OUT_INBOX}")
    print(f"total:             {len(named) + len(inbox):>4}")
    print()
    print("--- named sample ---")
    for r in named[:5]:
        print(f"  {r['Gemeente']:<35} {r['Naam']}")
    print("--- inbox sample ---")
    for r in inbox[:5]:
        print(f"  {r['Gemeente']:<35} {r['Naam']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
