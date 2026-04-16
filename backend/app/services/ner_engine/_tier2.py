"""Tier 2 — contextual personal data detected by Deduce NER, with
post-processing (heuristic filter, name-list scoring, huisnummer rule,
title-prefix rule, dedupe).

The heavy lifting lives in sibling modules:
- ``_tier2_trim``    — span trimming (punctuation, trailing titles)
- ``_tier2_filters`` — plausibility filters (event dates, public addresses)
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.services.name_engine import score_person_candidate

from ._deduce import _DEDUCE_TAG_MAP, _get_deduce, _get_name_lists
from ._huisnummer import _detect_adres_by_huisnummer
from ._initials import _detect_persoon_via_initials
from ._label_anchored_id import _detect_label_anchored_ids
from ._plausibility import _is_plausible_person_name
from ._straatnaam import _detect_adres_by_straatnaam
from ._tier2_filters import is_plausible_home_address, is_recent_event_date
from ._tier2_trim import trim_span, trim_trailing_titles
from ._title_prefix import _detect_persoon_via_title_prefix
from ._types import (
    DEFAULT_WOO_ARTICLE,
    NERDetection,
    _deduplicate,
    _merge_without_overlap,
)

logger = get_logger(__name__)


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
            if not is_plausible_home_address(annotation.text, text, annotation.start_char):
                logger.debug(
                    "ner.adres_dropped_by_org_filter",
                    start=annotation.start_char,
                )
                continue
            confidence = 0.75
            reasoning = "Adres gedetecteerd — mogelijk woonadres."
        elif entity_type == "datum":
            # Drop dates too recent to plausibly be a birth date, or
            # administrative dates anchored by a nearby "datum:", "d.d.",
            # "vastgesteld", "vergadering van", etc. Tier 1 still catches
            # explicit `geboortedatum:`-anchored dates regardless of year.
            if is_recent_event_date(annotation.text, text, annotation.start_char):
                logger.debug(
                    "ner.tier2_datum_dropped_event_context",
                    start=annotation.start_char,
                )
                continue
            confidence = 0.60
            reasoning = "Datum gedetecteerd — mogelijk geboortedatum."
        else:  # organisatie — guaranteed by allowlist above
            confidence = 0.50
            reasoning = "Organisatienaam gedetecteerd — beoordeel of herleidbaar tot persoon."

        trimmed_text, trimmed_start, trimmed_end = trim_span(
            annotation.text, annotation.start_char, annotation.end_char
        )
        if not trimmed_text:
            continue

        # Strip trailing job titles Deduce absorbed into person spans
        if entity_type == "persoon":
            trimmed_text, trimmed_start, trimmed_end = trim_trailing_titles(
                trimmed_text, trimmed_start, trimmed_end
            )
            if not trimmed_text:
                continue

        woo_article = DEFAULT_WOO_ARTICLE if entity_type != "organisatie" else ""
        detections.append(
            NERDetection.tier2(
                text=trimmed_text,
                entity_type=entity_type,
                confidence=confidence,
                start_char=trimmed_start,
                end_char=trimmed_end,
                reasoning=reasoning,
                woo_article=woo_article,
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
        if is_plausible_home_address(h.text, text, h.start_char)
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
