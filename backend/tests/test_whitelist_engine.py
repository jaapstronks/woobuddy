"""Unit tests for `app.services.whitelist_engine`.

Exercises the CSV loader, the `find_active_gemeenten` context scan, the
global address whitelist, and the context-gated public-officials
whitelist including the common-surname initials gate.

Also includes a pipeline-level smoke test that verifies a whitelist hit
produces a `review_status="rejected"` detection via `run_pipeline`.
"""

from __future__ import annotations

import re

import pytest

from app.services.pipeline_engine import run_pipeline
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan
from app.services.whitelist_engine import (
    find_active_gemeenten,
    load_whitelist_index,
    match_address_whitelist,
    match_person_whitelist,
)


@pytest.fixture(scope="module")
def index():
    return load_whitelist_index()


# ---------------------------------------------------------------------------
# Loader smoke tests
# ---------------------------------------------------------------------------


def test_loader_parses_all_municipalities(index):
    # We ship all 342 current Dutch municipalities. This number is
    # allowed to drift slightly across refreshes (mergers), so the
    # assertion is a floor — below 300 something is clearly wrong.
    assert len(index.municipalities) >= 300
    # Every municipality has at least one alias.
    for muni in index.municipalities:
        assert muni.aliases, f"municipality {muni.official_name} has no aliases"


def test_loader_parses_officials(index):
    # Officials are indexed per municipality; the total should be in
    # the low five figures (~14k raadsleden + wethouders + Woo-contact).
    total = sum(len(v) for v in index.officials_by_gm.values())
    assert total >= 10_000, f"expected many officials, got {total}"
    # And per-municipality lists are non-empty for the gemeenten we
    # know have raadsleden.
    # Aalsmeer = gm0358 (see sample in gemeenten.csv top rows).
    assert "gm0358" in index.officials_by_gm
    assert len(index.officials_by_gm["gm0358"]) > 0


def test_loader_captures_public_contact_data(index):
    # Postcodes, phones and emails are only whitelisted when they come
    # out of the Adressen / contact columns. Each should have hundreds
    # of entries, not be empty.
    assert len(index.postcodes) > 500
    assert len(index.emails) > 200
    assert len(index.phones) > 100


# ---------------------------------------------------------------------------
# find_active_gemeenten
# ---------------------------------------------------------------------------


def test_find_active_gemeenten_matches_explicit_prefix(index):
    text = "Betreft: subsidieaanvraag gemeente Aalsmeer."
    active = find_active_gemeenten(text, index)
    # gm0358 is Aalsmeer's TOOi code in our index.
    assert "gm0358" in active


def test_find_active_gemeenten_matches_bare_long_name(index):
    # Bare "Alblasserdam" (>= 5 chars) fires without a "gemeente " prefix.
    text = "De raad van Alblasserdam heeft vergaderd op 3 april."
    active = find_active_gemeenten(text, index)
    assert "gm0482" in active


def test_find_active_gemeenten_empty_without_mention(index):
    text = "Beste mevrouw Jansen, hartelijk dank voor uw bericht."
    active = find_active_gemeenten(text, index)
    assert active == set()


# ---------------------------------------------------------------------------
# Address whitelist (global, not context-gated)
# ---------------------------------------------------------------------------


def test_address_whitelist_postcode(index):
    # Aalsmeer's bezoekadres is Raadhuisplein 1, 1431 EH Aalsmeer.
    reason = match_address_whitelist("1431 EH", "postcode", index)
    assert reason is not None
    assert "openbare informatie" in reason


def test_address_whitelist_postcode_unknown(index):
    # A random valid-format postcode that is NOT a municipal address
    # should pass through (return None).
    reason = match_address_whitelist("9999 ZZ", "postcode", index)
    assert reason is None


def test_address_whitelist_email_info(index):
    reason = match_address_whitelist("info@aalsmeer.nl", "email", index)
    assert reason is not None


def test_address_whitelist_phone_normalised(index):
    # Aalsmeer: "(0297) 38 75 75" — digits-only normalisation.
    reason = match_address_whitelist("0297 38 75 75", "telefoon", index)
    assert reason is not None


def test_address_whitelist_private_email_not_matched(index):
    # A private email stays unlisted and the pipeline keeps it as a
    # normal Tier 1 auto-accepted detection.
    reason = match_address_whitelist("j.smit@gmail.com", "email", index)
    assert reason is None


# ---------------------------------------------------------------------------
# Postbus-context postcode suppression
# ---------------------------------------------------------------------------


def test_postbus_postcode_suppressed_with_comma(index):
    # Standard formal-letter layout: "Postbus 16200, 9999 ZZ Amsterdam".
    # We use a non-municipal postcode so the value-based postcode
    # whitelist does NOT match; the suppression must come entirely
    # from the postbus-context rule. (Many real postbus postcodes like
    # "3500 CE" happen to also be in the gemeentelijk-adres index,
    # which would mask this test.)
    text = "Postbus 16200, 9999 ZZ Amsterdam"
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is not None
    assert "postbusadres" in reason


def test_postbus_postcode_suppressed_without_comma(index):
    # Some layouts drop the comma: "Postbus 16200 9999 ZZ".
    text = "Postbus 16200 9999 ZZ"
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is not None
    assert "postbusadres" in reason


def test_bare_postcode_not_suppressed(index):
    # A postcode without any Postbus context stays on the auto-redact
    # path (returns None from the whitelist).
    text = "Op de brief staat 9999 ZZ vermeld."
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is None


def test_street_address_postcode_not_suppressed(index):
    # A street + huisnummer before the postcode is a residential layout,
    # not a postbus, and must NOT be suppressed.
    text = "Raadhuisstraat 12, 9999 ZZ Amsterdam"
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is None


def test_postbus_mention_far_from_postcode_does_not_suppress(index):
    # "Postbus" earlier in the sentence must not leak into an unrelated
    # residential postcode later on the line. The 30-char look-behind
    # window keeps this local.
    text = (
        "Postbus 93 is al jaren niet meer in gebruik; uw nieuwe adres is "
        "Raadhuisstraat 12, 9999 ZZ Amsterdam."
    )
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is None


def test_postbus_without_context_args_is_inert(index):
    # Backwards-compat: callers that do not pass full_text/start_char
    # still get the old value-based behaviour. A non-municipal postcode
    # returns None even if the caller knows nothing about context.
    reason = match_address_whitelist("9999 ZZ", "postcode", index)
    assert reason is None


# ---------------------------------------------------------------------------
# Person whitelist (context gated + initials gate)
# ---------------------------------------------------------------------------


def _span(text: str, needle: str) -> tuple[int, int]:
    m = re.search(re.escape(needle), text)
    assert m is not None, f"needle {needle!r} not in text"
    return m.start(), m.end()


def test_person_whitelist_hits_when_gemeente_mentioned(index):
    text = "Geachte raadsleden van gemeente Alblasserdam, namens dhr. van der Ende..."
    active = find_active_gemeenten(text, index)
    start, end = _span(text, "van der Ende")
    hit = match_person_whitelist("van der Ende", start, end, text, active, index)
    assert hit is not None
    assert hit.municipality_name == "Gemeente Alblasserdam"


def test_person_whitelist_requires_gemeente_in_document(index):
    # No gemeente name in text → whitelist stays inert even for a name
    # that happens to match a raadslid somewhere.
    text = "Klacht ingediend door mw. Erdogan over overlast."
    active = find_active_gemeenten(text, index)
    start, end = _span(text, "Erdogan")
    hit = match_person_whitelist("Erdogan", start, end, text, active, index)
    assert hit is None


def test_person_whitelist_common_surname_needs_initials(index):
    # Utrecht is in the text, but "Jansen" is common: without visible
    # initials the whitelist must refuse to fire.
    text = "Bezoek aan gemeente Utrecht door burger Jansen."
    active = find_active_gemeenten(text, index)
    start, end = _span(text, "Jansen")
    hit = match_person_whitelist("Jansen", start, end, text, active, index)
    assert hit is None


def test_person_whitelist_common_surname_with_matching_initials(index):
    # Find any Jansen raadslid in any active gemeente to build a
    # deterministic positive case. We need one whose initials are set
    # in the CSV.
    candidate = None
    for gm_code, officials in index.officials_by_gm.items():
        for o in officials:
            if o.surname_normalized == "jansen" and o.initials:
                candidate = (gm_code, o)
                break
        if candidate is not None:
            break
    if candidate is None:
        pytest.skip("no Jansen raadslid with initials found in current CSV snapshot")

    gm_code, official = candidate
    muni = next(m for m in index.municipalities if m.gm_code == gm_code)
    # Use the first initial from the CSV official so the gate fires.
    initial_letter = official.initials[0].upper()
    text = f"Brief aan {muni.official_name}: {initial_letter}. Jansen heeft gereageerd."
    active = find_active_gemeenten(text, index)
    needle = f"{initial_letter}. Jansen"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, active, index)
    assert hit is not None
    assert hit.used_initials is True


def test_person_whitelist_rejects_mismatching_initials(index):
    # Uncommon surname + explicit initial that does NOT match the
    # official's first initial → whitelist refuses.
    # Pick any Alblasserdam official with initials to probe.
    officials = index.officials_by_gm.get("gm0482", ())
    with_initials = [o for o in officials if o.initials]
    if not with_initials:
        pytest.skip("no Alblasserdam official with initials in current CSV snapshot")
    official = with_initials[0]
    # Choose a wrong first initial (never equal to official's).
    wrong_letter = "Z" if official.initials[0].upper() != "Z" else "Q"
    display_surname = official.display_name.split()[-1]
    text = f"Gemeente Alblasserdam: {wrong_letter}. {display_surname} niet aanwezig."
    active = find_active_gemeenten(text, index)
    needle = f"{wrong_letter}. {display_surname}"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, active, index)
    # Either no match (surname uncommon → strict initial gate) or a
    # match that did NOT use initials. The important invariant is that
    # a mismatching explicit initial never produces a used_initials
    # match — it either fails or falls through the uncommon-surname path
    # without initials.
    assert hit is None or hit.used_initials is False


# ---------------------------------------------------------------------------
# Pipeline integration — whitelist hits must produce rejected detections
# ---------------------------------------------------------------------------


def _single_page_extraction(text: str) -> ExtractionResult:
    """Wrap a single line of text in the structures run_pipeline expects.

    The span list is intentionally minimal: a single text-item spanning
    the whole line at fake coordinates. The pipeline's bbox resolver
    will return one bbox per detection, which is all we need for the
    assertion.
    """
    return ExtractionResult(
        full_text=text,
        pages=[
            PageText(
                page_number=1,
                full_text=text,
                spans=[TextSpan(page=1, text=text, x0=0.0, y0=0.0, x1=500.0, y1=20.0)],
            )
        ],
        page_count=1,
        document_date=None,
    )


@pytest.mark.asyncio
async def test_pipeline_whitelists_municipal_postcode():
    # Aalsmeer's bezoekadres postcode is 1431 EH — the Tier 1 regex
    # will pick it up, then the pipeline address whitelist should flip
    # it to `rejected`.
    text = "Bezoekadres gemeente Aalsmeer: Raadhuisplein 1, 1431 EH."
    extraction = _single_page_extraction(text)
    result = await run_pipeline(extraction=extraction)
    pc = [d for d in result.detections if d.entity_type == "postcode"]
    assert pc, "expected a postcode detection"
    assert pc[0].review_status == "rejected"
    assert pc[0].source == "whitelist_gemeente"
