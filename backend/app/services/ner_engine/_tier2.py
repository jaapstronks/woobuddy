"""Tier 2 — contextual personal data detected by Deduce NER, with
post-processing (heuristic filter, name-list scoring, huisnummer rule,
title-prefix rule, dedupe)."""

from __future__ import annotations

import datetime
import re

from app.logging_config import get_logger
from app.services.name_engine import score_person_candidate

from ._deduce import _DEDUCE_TAG_MAP, _get_deduce, _get_name_lists
from ._huisnummer import _detect_adres_by_huisnummer
from ._initials import _detect_persoon_via_initials
from ._label_anchored_id import _detect_label_anchored_ids
from ._plausibility import _ORGANIZATION_KEYWORDS, _is_plausible_person_name
from ._straatnaam import _detect_adres_by_straatnaam
from ._title_prefix import _detect_persoon_via_title_prefix
from ._types import NERDetection, _deduplicate, _merge_without_overlap

logger = get_logger(__name__)


# Tier 2 `datum` filter: Deduce flags every date it finds as a possible
# geboortedatum, but in Woo documents plain dates are overwhelmingly event
# dates (meeting dates, letter dates, request dates). If the year is within
# the last few years the subject would be a toddler and almost never appears
# by name — so we drop it. Genuine recent birth dates with an explicit
# anchor word are still caught by the Tier 1 path above.
_RECENT_DATE_MIN_BIRTH_AGE_YEARS = 2
_DATE_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Event-date context markers. If any of these appears within
# ``_EVENT_DATE_WINDOW_CHARS`` characters before the date span, we treat
# the date as an administrative date (letter date, meeting date, decision
# date) rather than a personal geboortedatum and drop it from Tier 2.
# Genuine birth dates are still caught by the Tier 1 geboortedatum
# anchor path regardless of what the surrounding context says.
_EVENT_DATE_WINDOW_CHARS = 30
_EVENT_DATE_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"datum\s*[:\-]|"
    r"d\.?\s*d\.?|"
    r"dd\s*[:\-]|"
    r"verzonden(?:\s+op)?|"
    r"verstuurd(?:\s+op)?|"
    r"vastgesteld(?:\s+op)?|"
    r"besloten(?:\s+op)?|"
    r"ondertekend(?:\s+op)?|"
    r"vergadering(?:\s+van)?|"
    r"vergaderd(?:\s+op)?|"
    r"brief\s+van|"
    r"per\s+brief\s+van|"
    r"ingediend(?:\s+op)?|"
    r"ontvangen(?:\s+op)?"
    r")\s*$",
    re.IGNORECASE,
)

# Address-context keywords specific to the `adres` branch. Deduce
# frequently emits institutional addresses as `adres`/`locatie` spans
# (Postbus-adressen, gemeentehuizen, ministerie-bezoekadressen). These
# are public and should not be redacted. A span that *contains* one of
# these keywords as a whole token, OR is preceded within ~30 chars by
# an institutional label, is dropped from Tier 2 adres results.
_ADRES_ORG_KEYWORDS = _ORGANIZATION_KEYWORDS | {
    "postbus",
    "stadhuis",
    "rijksoverheid",
    "gemeentehuis",
    "provinciehuis",
    "raadhuis",
}
_ADRES_CONTEXT_WINDOW_CHARS = 30
_ADRES_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"postadres|bezoekadres|correspondentieadres|"
    r"postbus|gemeentehuis|stadhuis|raadhuis|"
    r"provinciehuis|ministerie|rijksoverheid|"
    r"gemeente|provincie"
    r")\s*[:\-]?\s*$",
    re.IGNORECASE,
)


def _is_plausible_home_address(span_text: str, full_text: str, start_char: int) -> bool:
    """Reject adres spans that are clearly institutional/public.

    Mirrors the `persoon` plausibility filter: if the span text contains
    an organization keyword as a whole token, or if the preceding
    ~30 characters end in an institutional label, we treat the hit as a
    public address and drop it. The alternative would be to flip the
    default to `rejected`, but the whitelist engine already does that
    when the address is known — here we want to prevent the card from
    ever being surfaced.
    """
    tokens = {t.lower().strip(".,;:()") for t in span_text.split()}
    if _ADRES_ORG_KEYWORDS & tokens:
        return False
    ctx_start = max(0, start_char - _ADRES_CONTEXT_WINDOW_CHARS)
    preceding = full_text[ctx_start:start_char]
    return not _ADRES_CONTEXT_PATTERN.search(preceding)


# Characters Deduce sometimes swallows into an entity span that we want
# to trim off before the detection reaches the reviewer: trailing commas
# and sentence punctuation, stray quotes, leading parentheses. Spaces
# are included so "  Jan Jansen " becomes "Jan Jansen".
_TRIM_CHARS = " \t\n\r,.;:!?\"'()[]"


def _trim_span(annotation_text: str, start_char: int, end_char: int) -> tuple[str, int, int]:
    """Strip punctuation/whitespace from both ends of an entity span.

    Returns the (text, start, end) triple ready to be stored on the
    NERDetection. The caller is responsible for dropping empty results.
    """
    text = annotation_text
    start = start_char
    end = end_char
    while text and text[0] in _TRIM_CHARS:
        text = text[1:]
        start += 1
    while text and text[-1] in _TRIM_CHARS:
        text = text[:-1]
        end -= 1
    return text, start, end


def detect_tier2(text: str) -> list[NERDetection]:
    """Detect Tier 2 contextual personal data using Deduce NER."""
    deduce = _get_deduce()
    doc = deduce.deidentify(text)
    name_lists = _get_name_lists()
    detections: list[NERDetection] = []
    for annotation in doc.annotations:
        tag = annotation.tag.lower()
        entity_type = _DEDUCE_TAG_MAP.get(tag, tag)

        # Skip types already handled by Tier 1 regex
        if entity_type in ("bsn", "telefoon", "postcode", "url"):
            continue

        # Explicit allowlist. Deduce occasionally emits tags we do not
        # model (`id`, `zorginstelling`, `leeftijd`, etc.). Without this
        # guard they fell through to a generic fallback branch that
        # produced unactionable cards — including re-flagging Tier 1
        # validation failures (foreign IBANs, BSNs that fail 11-proef)
        # as `id`. Drop anything we cannot describe to the reviewer.
        if entity_type not in ("persoon", "adres", "datum", "organisatie"):
            logger.debug(
                "ner.tier2_tag_dropped",
                deduce_tag=tag,
                mapped_type=entity_type,
            )
            continue

        # Cheap heuristic pre-filter for `persoon` false positives.
        # Deduce was trained on medical records and over-tags
        # institution names, fragments, and common nouns as persons.
        # We drop the obvious garbage here before it ever enters the
        # review list.
        if entity_type == "persoon" and not _is_plausible_person_name(annotation.text):
            logger.debug(
                "ner.persoon_dropped_by_heuristic",
                text_length=len(annotation.text),
            )
            continue

        # Persons are the primary Tier 2 entity
        if entity_type == "persoon":
            # Name-list scoring: after the structural heuristic passes,
            # raise the bar by requiring at least one token to match
            # Meertens (first name) or CBS (surname). When the lists
            # are empty (e.g. tests with missing fixtures) we fall back
            # to the heuristic-only verdict to keep the pipeline working.
            confidence = 0.80
            woo_article = "5.1.2e"
            reasoning = (
                "Persoonsnaam gedetecteerd door NER. "
                "Classificatie nodig: burger, ambtenaar, of publiek functionaris."
            )
            if name_lists.first_names or name_lists.last_names:
                score = score_person_candidate(annotation.text, name_lists)
                if not score.is_plausible:
                    logger.debug(
                        "ner.persoon_dropped_by_name_lists",
                        text_length=len(annotation.text),
                    )
                    continue
                # Boost confidence for positive list hits. +0.10 for a
                # known first name, +0.05 extra if a known surname
                # also appears. Cap at 0.95 so manual review still
                # sees a sliver of uncertainty.
                if score.has_known_first_name:
                    confidence = min(confidence + 0.10, 0.95)
                if score.has_known_last_name:
                    confidence = min(confidence + 0.05, 0.95)
                # Attribution string — exact wording matters because
                # `Tier2Card.svelte` pattern-matches "Meertens Instituut"
                # to render the link back to the NVB.
                if score.has_known_first_name and score.has_known_last_name:
                    reasoning = (
                        "Persoonsnaam herkend: voornaam op lijst van het "
                        "Meertens Instituut (Nederlandse Voornamenbank), "
                        "achternaam op CBS-achternamenlijst."
                    )
                elif score.has_known_first_name:
                    reasoning = (
                        "Voornaam herkend in Nederlandse Voornamenbank (Meertens Instituut)."
                    )
                else:
                    reasoning = "Achternaam herkend op CBS-achternamenlijst."
        elif entity_type == "adres":
            if not _is_plausible_home_address(annotation.text, text, annotation.start_char):
                logger.debug(
                    "ner.adres_dropped_by_org_filter",
                    start=annotation.start_char,
                )
                continue
            confidence = 0.75
            woo_article = "5.1.2e"
            reasoning = "Adres gedetecteerd — mogelijk woonadres."
        elif entity_type == "datum":
            # Drop dates too recent to plausibly be a birth date of anyone
            # named in a Woo document — they're almost always event dates
            # (meeting, letter, request). Tier 1 still catches explicit
            # `geboortedatum:`-anchored dates regardless of year.
            year_match = _DATE_YEAR_PATTERN.search(annotation.text)
            if year_match is not None:
                year = int(year_match.group(0))
                cutoff_year = datetime.date.today().year - _RECENT_DATE_MIN_BIRTH_AGE_YEARS
                if year >= cutoff_year:
                    continue
            # Preceding-context check: drop administrative dates anchored
            # by a nearby "datum:", "d.d.", "vastgesteld", "vergadering
            # van", etc. These are letter/meeting/decision dates and never
            # geboortedata. We look at the N characters just before the
            # span and require the anchor to end right next to the date.
            ctx_start = max(0, annotation.start_char - _EVENT_DATE_WINDOW_CHARS)
            preceding = text[ctx_start : annotation.start_char]
            if _EVENT_DATE_CONTEXT_PATTERN.search(preceding):
                logger.debug(
                    "ner.tier2_datum_dropped_event_context",
                    start=annotation.start_char,
                )
                continue
            confidence = 0.60
            woo_article = "5.1.2e"
            reasoning = "Datum gedetecteerd — mogelijk geboortedatum."
        else:  # organisatie — guaranteed by allowlist above
            confidence = 0.50
            woo_article = ""
            reasoning = "Organisatienaam gedetecteerd — beoordeel of herleidbaar tot persoon."

        trimmed_text, trimmed_start, trimmed_end = _trim_span(
            annotation.text, annotation.start_char, annotation.end_char
        )
        if not trimmed_text:
            continue

        detections.append(
            NERDetection(
                text=trimmed_text,
                entity_type=entity_type,
                tier="2",
                confidence=confidence,
                woo_article=woo_article,
                source="deduce",
                start_char=trimmed_start,
                end_char=trimmed_end,
                reasoning=reasoning,
            )
        )

    # ---- Post-Deduce sub-rules ----
    #
    # Each sub-rule runs a regex-based detector on the full text, then
    # merges hits into the accumulation list with overlap dedup. Order
    # matters: earlier rules take priority at the same char span. The
    # numbers below are the execution order.
    #
    # 1. straatnaam   — "Havenstraat 194" (Deduce misses plain prose)
    # 2. huisnummer   — "huisnummer 22" / "bewoner van nummer 26"
    # 3. initials     — "G.J. Stronks" (CBS surname miss)
    # 4. label-id     — "Klantnummer: 123" / "Kenmerk: OT-…"
    # 5. title-prefix — "de heer El Khatib" (non-CBS after salutation)

    # 1. Straatnaam: full Dutch street+number spans. Institutional-
    # address filter applied so gemeentehuis addresses are dropped.
    straatnaam_hits = [
        h
        for h in _detect_adres_by_straatnaam(text)
        if _is_plausible_home_address(h.text, text, h.start_char)
    ]
    _merge_without_overlap(detections, straatnaam_hits, "adres", "ner.straatnaam_dropped_overlap")

    # 2. Huisnummer: partially-anonymized "huisnummer N" / "bewoner
    # van nummer N". Special semantics: replaces existing adres hits
    # fully contained within a huisnummer span (prevents double cards).
    huisnummer_hits = _detect_adres_by_huisnummer(text)
    if huisnummer_hits:
        hn_ranges = [(h.start_char, h.end_char) for h in huisnummer_hits]
        detections = [
            d
            for d in detections
            if not (
                d.entity_type == "adres"
                and any(s <= d.start_char and e >= d.end_char for s, e in hn_ranges)
            )
        ]
        detections.extend(huisnummer_hits)

    # 3. Initials: "G.J. Stronks"-style structural pattern (no
    # wordlist required). Deduped against existing persoon hits.
    _merge_without_overlap(
        detections,
        _detect_persoon_via_initials(text),
        "persoon",
        "ner.initials_rule_dropped_overlap",
    )

    # 4. Label-anchored IDs: "Klantnummer: 123", "Kenmerk: OT-…".
    # No dedup — these reference numbers don't overlap NER entities.
    detections.extend(_detect_label_anchored_ids(text))

    # 5. Title-prefix: salutation + capitalized non-CBS surnames.
    # Deduped against existing persoon hits so CBS wins aren't demoted.
    _merge_without_overlap(
        detections,
        _detect_persoon_via_title_prefix(text, name_lists),
        "persoon",
        "ner.title_rule_dropped_overlap",
    )

    return _deduplicate(detections)
