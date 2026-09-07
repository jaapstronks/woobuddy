"""Tests for a sample of the triage catalogue.

Every rule in `triage_rules.py` is a claim about what a detection error *is*,
and a rule that fires too eagerly is worse than no rule: it hides the item in
a bucket nobody rereads. So the ones that carry the most weight get a positive
and a negative case here, including the negative that motivates the rule (a
real person's address must not be waved through as an object address).

Run from `backend/`:

    pytest eval/test_triage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from triage_rules import TriageItem, classify  # noqa: E402


def fp(text: str, entity_type: str, context: str = "", **kw: object) -> TriageItem:
    return TriageItem(
        kind="fp",
        doc="doc.pdf",
        page=1,
        text=text,
        entity_type=entity_type,
        context=context or text,
        **kw,  # type: ignore[arg-type]
    )


def fn(value: str, truth_type: str, outcome: str, **kw: object) -> TriageItem:
    return TriageItem(
        kind="fn",
        doc="doc.pdf",
        page=1,
        text=value,
        truth_type=truth_type,
        outcome=outcome,
        **kw,  # type: ignore[arg-type]
    )


def names(item: TriageItem) -> set[str]:
    return {r.name for r in classify(item)}


def test_functional_mailbox_separates_desks_from_people() -> None:
    assert "functional_mailbox" in names(fp("post@drenthe.nl", "email"))
    assert "functional_mailbox" in names(fp("bezwaarschriften@emmen.nl", "email"))
    # A named person at the same domain is exactly what we do want redacted.
    assert "functional_mailbox" not in names(fp("k.harmsen@drenthe.nl", "email"))


def test_street_as_person_needs_a_real_suffix() -> None:
    assert "street_as_person" in names(fp("Maasdijk 191", "persoon"))
    assert "street_as_person" in names(fp("Van Echtenstraat", "persoon"))
    # "de Weg" is a surname, not a street: the suffix must not be the whole
    # token, or every short Dutch name gets excused.
    assert "street_as_person" not in names(fp("de Weg", "persoon"))
    assert "street_as_person" not in names(fp("Sigrid van den Oosterman", "persoon"))


def test_object_address_reads_the_window_before_the_span() -> None:
    hit = fp(
        "Turfweg 10a",
        "adres",
        context="Onderwerp: Besluit op bezwaar woo-verzoek Turfweg 10a te Roden",
    )
    assert "object_address" in names(hit)
    # A citizen's own address in a greeting block has no object cue and must
    # stay a candidate.
    miss = fp(
        "Julianalaan 135",
        "adres",
        context="Sigrid van den Oosterman Julianalaan 135 9331 PA Norg",
    )
    assert "object_address" not in names(miss)


def test_date_in_prose_spares_a_birth_date() -> None:
    assert "date_in_prose" in names(fp("23 januari 2023", "datum", context="Op 23 januari 2023"))
    born = fp("23 januari 1978", "datum", context="geboren op 23 januari 1978 te Assen")
    assert "date_in_prose" not in names(born)


def test_repeated_address_uses_document_level_counts() -> None:
    boilerplate = fp("Westerbrink 1", "adres")
    boilerplate.doc_facts = {"text_counts": {"westerbrink 1": 31}}
    assert "repeated_address" in names(boilerplate)
    once = fp("Julianalaan 135", "adres")
    once.doc_facts = {"text_counts": {"julianalaan 135": 1}}
    assert "repeated_address" not in names(once)


def test_bare_surname_after_greeting_and_off_wordlist_are_distinct() -> None:
    greeting = fn("Ait Mansour", "achternaam", "missed", context="Geachte Ait Mansour ,")
    assert "bare_surname_after_greeting" in names(greeting)
    off_list = fn("Kaczmarek", "volledige_naam", "missed", in_wordlist=False)
    assert names(off_list) == {"off_wordlist_name"}
    # A name that *is* on the list and was missed needs a different diagnosis,
    # so the off-list rule must not claim it.
    on_list = fn("Jansen", "volledige_naam", "missed", in_wordlist=True)
    assert "off_wordlist_name" not in names(on_list)


def test_no_bbox_matches_against_the_document_facts() -> None:
    item = fn("Berend Luermans", "volledige_naam", "missed")
    item.doc_facts = {"no_bbox_texts": ("Berend Luermans",)}
    assert "no_bbox" in names(item)
    item.doc_facts = {"no_bbox_texts": ("Iemand Anders",)}
    assert "no_bbox" not in names(item)


def test_rejected_causes_read_the_source_and_the_reasoning() -> None:
    whitelisted = fn("Turenhout", "achternaam", "rejected", source="whitelist_gemeente")
    assert "whitelist_surname_only" in names(whitelisted)
    body = fn(
        "Y. Turenhout",
        "volledige_naam",
        "rejected",
        source="rule_engine",
        reasoning="gedeputeerde staten van Drenthe is een bestuursorgaan",
    )
    assert "governing_body_as_title" in names(body)
