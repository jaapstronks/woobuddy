"""Tier 2 — contextual personal data detected by Deduce NER, with
post-processing (heuristic filter, name-list scoring, huisnummer rule,
title-prefix rule, dedupe).

The heavy lifting lives in sibling modules:
- ``_tier2_trim``    — span trimming (punctuation, trailing titles)
- ``_tier2_filters`` — plausibility filters (birth cues, street shape, public addresses)
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.services.name_engine import NameLists, score_person_candidate

from ._anchor_rules import detect_persoon_via_anchors
from ._corroboration import suppress_uncorroborated_single_tokens
from ._deduce import _DEDUCE_TAG_MAP, _get_deduce, _get_name_lists
from ._huisnummer import _detect_adres_by_huisnummer
from ._initials import _detect_persoon_via_initials
from ._label_anchored_id import _detect_label_anchored_ids
from ._person_shape import drop_non_person_spans
from ._plausibility import _is_plausible_person_name
from ._straatnaam import _detect_adres_by_straatnaam
from ._tier2_filters import (
    has_birth_cue,
    has_postcode_nearby,
    has_strong_street_shape,
    is_plausible_home_address,
    is_recent_event_date,
)
from ._tier2_trim import split_merged_span, trim_span, trim_trailing_titles
from ._title_prefix import _detect_persoon_via_title_prefix
from ._types import (
    DEFAULT_WOO_ARTICLE,
    NERDetection,
    _deduplicate,
    _merge_without_overlap,
)
from ._wordlist_pairs import detect_persoon_via_wordlists

logger = get_logger(__name__)


def _persoon_detection(
    text: str,
    start_char: int,
    end_char: int,
    name_lists: NameLists,
) -> NERDetection | None:
    """Judge one candidate `persoon` span and build its detection.

    Split out of the loop because a Deduce annotation is not always one
    span (#98): "Jansen. Jansen" and "M.F.\\nVan" are two, and each half
    has to face the plausibility heuristic and the name lists on its own
    evidence rather than inherit the other half's.
    """
    # Cheap heuristic pre-filter for `persoon` false positives. Deduce
    # was trained on medical records and over-tags institution names,
    # fragments, and common nouns as persons. Drop the obvious garbage
    # here before it ever enters the review list.
    if not _is_plausible_person_name(text):
        logger.debug("ner.persoon_dropped_by_heuristic", text_length=len(text))
        return None

    # Name-list scoring: after the structural heuristic passes, raise
    # the bar by requiring at least one token to match Meertens (first
    # name) or CBS (surname). When the lists are empty (e.g. tests with
    # missing fixtures) we fall back to the heuristic-only verdict to
    # keep the pipeline working.
    confidence = 0.80
    reasoning = (
        "Persoonsnaam gedetecteerd door NER. "
        "Classificatie nodig: burger, ambtenaar, of publiek functionaris."
    )
    if name_lists.first_names or name_lists.last_names:
        score = score_person_candidate(text, name_lists)
        if not score.is_plausible:
            logger.debug("ner.persoon_dropped_by_name_lists", text_length=len(text))
            return None
        # Boost confidence for positive list hits. +0.10 for a known
        # first name, +0.05 extra if a known surname also appears. Cap
        # at 0.95 so manual review still sees a sliver of uncertainty.
        if score.has_known_first_name:
            confidence = min(confidence + 0.10, 0.95)
        if score.has_known_last_name:
            confidence = min(confidence + 0.05, 0.95)
        # Attribution string — exact wording matters because
        # `Tier2Card.svelte` pattern-matches "Meertens Instituut" to
        # render the link back to the NVB.
        if score.has_known_first_name and score.has_known_last_name:
            reasoning = (
                "Persoonsnaam herkend: voornaam op lijst van het "
                "Meertens Instituut (Nederlandse Voornamenbank), "
                "achternaam op CBS-achternamenlijst."
            )
        elif score.has_known_first_name:
            reasoning = "Voornaam herkend in Nederlandse Voornamenbank (Meertens Instituut)."
        else:
            reasoning = "Achternaam herkend op CBS-achternamenlijst."

    trimmed_text, trimmed_start, trimmed_end = trim_span(text, start_char, end_char)
    if not trimmed_text:
        return None
    # Strip trailing job titles Deduce absorbed into person spans
    trimmed_text, trimmed_start, trimmed_end = trim_trailing_titles(
        trimmed_text, trimmed_start, trimmed_end
    )
    if not trimmed_text:
        return None

    return NERDetection.tier2(
        text=trimmed_text,
        entity_type="persoon",
        confidence=confidence,
        start_char=trimmed_start,
        end_char=trimmed_end,
        reasoning=reasoning,
        woo_article=DEFAULT_WOO_ARTICLE,
    )


def detect_tier2(text: str) -> list[NERDetection]:
    """Detect Tier 2 contextual personal data using Deduce NER."""
    deduce = _get_deduce()
    doc = deduce.deidentify(text)
    name_lists = _get_name_lists()
    detections: list[NERDetection] = []
    # `doc.annotations` is a `docdeid.AnnotationSet`, i.e. a plain `set`
    # subclass — iterating it yields hash order, and `Annotation` is a
    # frozen dataclass whose hash comes from its `text`/`tag` strings.
    # Python randomizes string hashing per process, so the same document
    # handed to the same code produced a different annotation order on
    # every run. That leaked all the way through: the overlap dedup in
    # `_merge_without_overlap` and `_deduplicate` below keeps whichever
    # hit it sees first, so the order decided not only how the list was
    # laid out but occasionally which detection survived (#103). Sort
    # once, here at the source, and everything downstream is a
    # deterministic list operation.
    for annotation in doc.annotations.sorted(by=("start_char", "end_char", "tag")):
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
        #
        # `organisatie` (Deduce's hospital / healthcare-institution
        # annotators) is deliberately absent: an organisation name is
        # not personal data, the annotators are medical-domain, and the
        # 0.50 "beoordeel of herleidbaar" card it produced was noise on
        # every document that mentioned a GGD or ziekenhuis.
        if entity_type not in ("persoon", "adres", "datum"):
            logger.debug(
                "ner.tier2_tag_dropped",
                deduce_tag=tag,
                mapped_type=entity_type,
            )
            continue

        # Persons are the primary Tier 2 entity. One annotation may hold
        # more than one span — Deduce reaches over a sentence boundary
        # and over a line break — so split first and judge each piece on
        # its own evidence (#98).
        if entity_type == "persoon":
            for piece, piece_start, piece_end in split_merged_span(
                annotation.text, annotation.start_char, annotation.end_char
            ):
                persoon = _persoon_detection(piece, piece_start, piece_end, name_lists)
                if persoon is not None:
                    detections.append(persoon)
            continue

        if entity_type == "adres":
            if not is_plausible_home_address(annotation.text, text, annotation.start_char):
                logger.debug(
                    "ner.adres_dropped_by_org_filter",
                    start=annotation.start_char,
                )
                continue
            # Same evidence tiers as the regex straatnaam rule, so a
            # Deduce hit that wins the overlap dedupe does not demote a
            # letterhead address to 0.75.
            if has_postcode_nearby(text, annotation.start_char, annotation.end_char):
                confidence = 0.92
                reasoning = (
                    "Adres gedetecteerd vlak bij een postcode — vrijwel zeker een volledig adres."
                )
            elif has_strong_street_shape(annotation.text):
                confidence = 0.85
                reasoning = "Straatnaam + huisnummer gedetecteerd — mogelijk woonadres."
            else:
                confidence = 0.75
                reasoning = (
                    "Adres gedetecteerd op basis van de woonaanduiding ervoor — mogelijk woonadres."
                )
        else:  # datum — guaranteed by allowlist above
            # A plain date only earns a card when a birth cue ("geboren",
            # "geboortedatum", "geb.") sits within ~200 chars before it.
            # Woo documents are full of event dates (besluit, vergadering,
            # brief) and every one of them used to surface as "mogelijk
            # geboortedatum". Tier 1 still catches the tight
            # `geboortedatum:`-anchored shape regardless of year; the
            # recent-year / administrative-anchor filter stays as a
            # second guard for cued dates.
            if not has_birth_cue(text, annotation.start_char):
                logger.debug(
                    "ner.tier2_datum_dropped_no_birth_cue",
                    start=annotation.start_char,
                )
                continue
            if is_recent_event_date(annotation.text, text, annotation.start_char):
                logger.debug(
                    "ner.tier2_datum_dropped_event_context",
                    start=annotation.start_char,
                )
                continue
            confidence = 0.60
            reasoning = "Datum gedetecteerd bij een geboorte-aanduiding — mogelijk geboortedatum."

        trimmed_text, trimmed_start, trimmed_end = trim_span(
            annotation.text, annotation.start_char, annotation.end_char
        )
        if not trimmed_text:
            continue

        detections.append(
            NERDetection.tier2(
                text=trimmed_text,
                entity_type=entity_type,
                confidence=confidence,
                start_char=trimmed_start,
                end_char=trimmed_end,
                reasoning=reasoning,
                woo_article=DEFAULT_WOO_ARTICLE,
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
    # 6. anchors      — "Hoogachtend, / Yıldırım", "Naam: Djaimy Pijpker"
    # 7. wordlists    — "Mandy Loon" (Meertens ∧ CBS, no Deduce span)

    # 1. Straatnaam: full Dutch street+number spans. The plausibility
    # filter drops institutional addresses AND every weak-suffix
    # candidate ("Uitvoering 7", "Loopbaan 4") that no postcode or
    # residence cue corroborates.
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

    # 6. Structure anchors: a closing, a form label, an aanhef, or a
    # mail display name says a person follows, whatever the wordlists
    # know (#97). Deduped against existing persoon hits.
    _merge_without_overlap(
        detections,
        detect_persoon_via_anchors(text, name_lists),
        "persoon",
        "ner.anchor_rule_dropped_overlap",
    )

    # 7. Wordlist pairs: a Meertens given name next to a CBS surname
    # that Deduce never proposed. Runs last of the persoon rules so
    # every anchored span keeps its own, wider boundaries.
    _merge_without_overlap(
        detections,
        detect_persoon_via_wordlists(text, name_lists),
        "persoon",
        "ner.wordlist_rule_dropped_overlap",
    )

    # 8. Shape gate: the four shapes every persoon rule mistakes for a
    # name — a list marker ("A. Gemengd"), a street with a house number
    # ("P. de Keyserstraat 18"), an author in a reference list, a place
    # absorbed into the span ("Kersten te Nieuw-Dordrecht"). Runs over
    # the merged list because each of them arrived by more than one
    # route (#98).
    detections = drop_non_person_spans(detections, text, name_lists)

    # 9. Corroboration gate: a bare one-word persoon hit ("Roos",
    # "Storm", "Kunst") survives only when the document vouches for it
    # — same token in a multi-word name, an anchored rule, or a
    # greeting right before it.
    detections = suppress_uncorroborated_single_tokens(detections, text, name_lists)

    return _deduplicate(detections)
