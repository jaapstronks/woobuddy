"""Unit tests for `app.services.whitelist_engine`.

Exercises the CSV loader, the `find_gemeente_mentions` context scan, the
global address whitelist, and the context- and identity-gated
public-officials whitelist: the initials gate, the given-name gate and
the gemeente-proximity gate that together keep a bare surname from
silently rejecting a private citizen (#92).

Also includes a pipeline-level smoke test that verifies a whitelist hit
produces a `review_status="rejected"` detection via `run_pipeline`, and
two classifier-level tests for the confirmed/unconfirmed split.
"""

from __future__ import annotations

import re

import pytest

from app.services.pipeline_engine import run_pipeline
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan
from app.services.whitelist_engine import (
    find_gemeente_mentions,
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
# find_gemeente_mentions
# ---------------------------------------------------------------------------


def test_find_gemeente_mentions_matches_explicit_prefix(index):
    text = "Betreft: subsidieaanvraag gemeente Aalsmeer."
    active = find_gemeente_mentions(text, index)
    # gm0358 is Aalsmeer's TOOi code in our index.
    assert "gm0358" in active


def test_find_gemeente_mentions_matches_bare_long_name(index):
    # Bare "Alblasserdam" (>= 5 chars) fires without a "gemeente " prefix.
    text = "De raad van Alblasserdam heeft vergaderd op 3 april."
    active = find_gemeente_mentions(text, index)
    assert "gm0482" in active


def test_find_gemeente_mentions_empty_without_mention(index):
    text = "Beste mevrouw Jansen, hartelijk dank voor uw bericht."
    active = find_gemeente_mentions(text, index)
    assert active == {}


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


def test_bezoekadres_line_postcode_suppressed(index):
    # "Bezoekadres: Stadhuisplein 1, 9999 ZZ Rotterdam" — the label
    # sits earlier on the line, not directly before the postcode, and
    # still marks the whole line as an organisation's address.
    text = "Bezoekadres: Stadhuisplein 1, 9999 ZZ Rotterdam"
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is not None
    assert "organisatie" in reason


def test_plain_home_postcode_not_suppressed(index):
    text = "Kerkstraat 12, 9999 ZZ Rotterdam"
    start = text.index("9999 ZZ")
    reason = match_address_whitelist(
        "9999 ZZ",
        "postcode",
        index,
        full_text=text,
        start_char=start,
    )
    assert reason is None


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
    # The surname is on Alblasserdam's officials list, so there is a hit
    # — but "van der Ende" carries no given name or initials, so it is a
    # lead and not a licence to un-redact (#92).
    text = "Geachte raadsleden van gemeente Alblasserdam, namens dhr. van der Ende..."
    mentions = find_gemeente_mentions(text, index)
    start, end = _span(text, "van der Ende")
    hit = match_person_whitelist("van der Ende", start, end, text, mentions, index)
    assert hit is not None
    assert hit.municipality_name == "Gemeente Alblasserdam"
    assert hit.confirmed is False
    assert hit.hint_reason == "no_given_name"


def test_person_whitelist_requires_gemeente_in_document(index):
    # No gemeente name in text → whitelist stays inert even for a name
    # that happens to match a raadslid somewhere.
    text = "Klacht ingediend door mw. Erdogan over overlast."
    mentions = find_gemeente_mentions(text, index)
    start, end = _span(text, "Erdogan")
    hit = match_person_whitelist("Erdogan", start, end, text, mentions, index)
    assert hit is None


def test_person_whitelist_common_surname_needs_initials(index):
    # Utrecht is in the text, but "Jansen" is common: without visible
    # initials the whitelist must refuse to fire.
    text = "Bezoek aan gemeente Utrecht door burger Jansen."
    mentions = find_gemeente_mentions(text, index)
    start, end = _span(text, "Jansen")
    hit = match_person_whitelist("Jansen", start, end, text, mentions, index)
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
    mentions = find_gemeente_mentions(text, index)
    needle = f"{initial_letter}. Jansen"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, mentions, index)
    assert hit is not None
    assert hit.used_initials is True
    assert hit.confirmed is True


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
    mentions = find_gemeente_mentions(text, index)
    needle = f"{wrong_letter}. {display_surname}"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, mentions, index)
    # Either no match (surname uncommon → strict initial gate) or a
    # match that did NOT use initials. The important invariant is that
    # a mismatching explicit initial never produces a used_initials
    # match — it either fails or falls through the uncommon-surname path
    # without initials.
    assert hit is None or hit.used_initials is False


# ---------------------------------------------------------------------------
# #92 — identity gate: a surname alone never rejects
# ---------------------------------------------------------------------------


def _official_with_initials(index, gm_code: str, *, common: bool = False):
    """Pick a deterministic official from a gemeente for gate probing."""
    from app.services.whitelist_engine._text import _COMMON_SURNAMES

    for official in index.officials_by_gm.get(gm_code, ()):
        if not official.initials:
            continue
        if (official.surname_normalized in _COMMON_SURNAMES) is not common:
            continue
        if len(official.surname_normalized.split()) > 1:
            continue
        return official
    return None


def test_person_whitelist_given_name_mismatch_never_hits(index):
    # The #92 leak: a private citizen whose surname collides with a
    # raadslid. Her given name starts with a letter the official's
    # initials do not, so the whitelist must not produce a hit at all.
    official = _official_with_initials(index, "gm0482")
    if official is None:
        pytest.skip("no single-token Alblasserdam official with initials in this CSV")
    wrong_given = "Quirina" if official.initials[0] != "q" else "Zeger"
    surname = official.surname_normalized.title()
    text = f"Gemeente Alblasserdam ontving een brief van {wrong_given} {surname}."
    mentions = find_gemeente_mentions(text, index)
    needle = f"{wrong_given} {surname}"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, mentions, index)
    assert hit is None


def test_person_whitelist_given_name_match_confirms(index):
    # Same shape, but the given name agrees with the official's first
    # initial — that is enough to confirm and default to "niet lakken".
    official = _official_with_initials(index, "gm0482")
    if official is None:
        pytest.skip("no single-token Alblasserdam official with initials in this CSV")
    given = official.initials[0].upper() + "arolien"
    surname = official.surname_normalized.title()
    text = f"Gemeente Alblasserdam: {given} {surname} was aanwezig."
    mentions = find_gemeente_mentions(text, index)
    needle = f"{given} {surname}"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, mentions, index)
    assert hit is not None
    assert hit.confirmed is True
    assert hit.used_initials is True


def test_person_whitelist_bare_surname_is_only_a_hint(index):
    # "Geachte van der Groot" — an uncommon surname with nothing to
    # identify it. A hit, but unconfirmed, so the caller keeps it pending.
    official = _official_with_initials(index, "gm0482")
    if official is None:
        pytest.skip("no single-token Alblasserdam official with initials in this CSV")
    surname = official.surname_normalized.title()
    text = f"Gemeente Alblasserdam. Geachte {surname}, hierbij ons antwoord."
    mentions = find_gemeente_mentions(text, index)
    start, end = _span(text, surname)
    hit = match_person_whitelist(surname, start, end, text, mentions, index)
    assert hit is not None
    assert hit.confirmed is False
    assert hit.hint_reason == "no_given_name"


def test_person_whitelist_distant_gemeente_downgrades_to_hint(index):
    # The gemeente is named far past the letterhead and far from the
    # span, so even a matching given name only earns a hint.
    official = _official_with_initials(index, "gm0482")
    if official is None:
        pytest.skip("no single-token Alblasserdam official with initials in this CSV")
    given = official.initials[0].upper() + "arolien"
    surname = official.surname_normalized.title()
    filler = "Deze alinea gaat over iets volstrekt anders. " * 30
    text = f"{filler}Gemeente Alblasserdam wordt hier genoemd. {filler}{given} {surname} tekende."
    mentions = find_gemeente_mentions(text, index)
    needle = f"{given} {surname}"
    start, end = _span(text, needle)
    hit = match_person_whitelist(needle, start, end, text, mentions, index)
    assert hit is not None
    assert hit.confirmed is False
    assert hit.hint_reason == "gemeente_far"


def test_person_whitelist_leading_placename_is_trimmed(index):
    # Deduce runs a city into the following name ("Assen Berkant Vecht").
    # The city must not become the surname the whitelist matches on.
    from app.services.whitelist_engine._persons import _detection_name_tokens

    assert _detection_name_tokens("Assen Berkant Vecht", index) == ["berkant", "vecht"]
    # ...but a two-token name that happens to start with a place name
    # keeps its surname, so real officials still match.
    assert _detection_name_tokens("M.H. Assen", index) == ["assen"]


def test_person_whitelist_common_surname_stays_silent_without_evidence(index):
    # Regression guard on the negative case: a common surname carries no
    # information, so it earns neither a rejection nor a hint.
    official = _official_with_initials(index, "gm0344", common=True) or _official_with_initials(
        index, "gm0363", common=True
    )
    if official is None:
        pytest.skip("no common-surname official with initials in this CSV")
    muni = next(m for m in index.municipalities if m.gm_code == official.gm_code)
    surname = official.surname_normalized.title()
    text = f"{muni.official_name} ontving een klacht van {surname}."
    mentions = find_gemeente_mentions(text, index)
    start, end = _span(text, surname)
    hit = match_person_whitelist(surname, start, end, text, mentions, index)
    assert hit is None


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


# ---------------------------------------------------------------------------
# #92 — the classifier turns the two hit strengths into two review states
# ---------------------------------------------------------------------------


def _classify_name(index, text: str, needle: str):
    """Run the Tier 2 persoon classifier over one hand-placed name.

    Goes through the real `_build_doc_context` + `_classify_persoon` so
    the rule ordering is exercised, but skips Deduce: the detection is
    handed in directly, which keeps the test deterministic.
    """
    from app.services.ner_engine import DEFAULT_WOO_ARTICLE, NERDetection
    from app.services.pipeline_engine import _build_doc_context, _classify_persoon

    start, end = _span(text, needle)
    det = NERDetection(
        text=needle,
        entity_type="persoon",
        tier="2",
        confidence=0.7,
        woo_article=DEFAULT_WOO_ARTICLE,
        source="deduce",
        start_char=start,
        end_char=end,
    )
    ctx = _build_doc_context(_single_page_extraction(text), None)
    return _classify_persoon(det, [], ctx)


def test_classifier_rejects_a_confirmed_official(index):
    # The negative control for #92: a real raadslid, named with a given
    # name that matches the CSV initials, must keep defaulting to
    # "niet lakken".
    official = _official_with_initials(index, "gm0482")
    if official is None:
        pytest.skip("no single-token Alblasserdam official with initials in this CSV")
    given = official.initials[0].upper() + "arolien"
    surname = official.surname_normalized.title()
    needle = f"{given} {surname}"
    text = f"Gemeente Alblasserdam meldt dat {needle} het voorstel steunde."
    result = _classify_name(index, text, needle)
    assert result.review_status == "rejected"
    assert result.source == "whitelist_gemeente"
    assert result.subject_role == "publiek_functionaris"


def test_classifier_keeps_a_bare_surname_pending_with_the_lead(index):
    # The leak itself: the same surname without a given name stays
    # pending, so the reviewer still sees it as a redaction candidate.
    official = _official_with_initials(index, "gm0482")
    if official is None:
        pytest.skip("no single-token Alblasserdam official with initials in this CSV")
    surname = official.surname_normalized.title()
    text = f"Gemeente Alblasserdam meldt dat {surname} het voorstel steunde."
    result = _classify_name(index, text, surname)
    assert result.review_status == "pending"
    assert result.source == "whitelist_gemeente_hint"
    assert result.subject_role is None
    assert result.woo_article is not None
    assert "niet bevestigd" in result.reasoning
