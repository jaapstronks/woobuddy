"""Tier 2 — contextual personal data detected by Deduce NER, with
post-processing (heuristic filter, name-list scoring, huisnummer rule,
title-prefix rule, dedupe)."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from app.logging_config import get_logger
from app.services.name_engine import score_person_candidate

from ._deduce import _DEDUCE_TAG_MAP, _get_deduce, _get_name_lists
from ._huisnummer import _detect_adres_by_huisnummer
from ._initials import _detect_persoon_via_initials
from ._label_anchored_id import _detect_label_anchored_ids
from ._plausibility import _is_plausible_person_name
from ._straatnaam import _detect_adres_by_straatnaam
from ._title_prefix import _detect_persoon_via_title_prefix
from ._types import (
    DEFAULT_WOO_ARTICLE,
    ORGANIZATION_KEYWORDS,
    NERDetection,
    _deduplicate,
    _merge_without_overlap,
)

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
_ADRES_ORG_KEYWORDS = ORGANIZATION_KEYWORDS | {
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
    stripped = span_text.strip()

    # Bare city/place names without a street are too vague to be
    # actionable: "Utrecht", "Rotterdam", "Eindhoven". A genuine home
    # address always contains a space (street + number, or city +
    # postcode). Single-word spans are overwhelmingly just Deduce
    # tagging a city name as `locatie`.
    if " " not in stripped:
        return False

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


# Trailing non-name words Deduce greedily absorbs into person spans.
# Loaded from the functietitels lists plus generic Dutch role/section
# words. Multi-word titles are matched longest-first so "Ruimtelijke
# Ordening" is stripped before "Ordening" alone.


@dataclass(frozen=True)
class _TrailingTitleVocab:
    """Compiled trailing-title vocabulary for person-span trimming."""

    words: frozenset[str]
    phrases: tuple[str, ...]  # multi-word, sorted longest first


def _load_trailing_titles() -> _TrailingTitleVocab:
    """Build the trailing-title vocabulary from the role-engine data files."""
    from pathlib import Path

    data_dir = Path(__file__).resolve().parents[2] / "data"
    words: set[str] = set()
    phrases: list[str] = []

    for fname in ("functietitels_publiek.txt", "functietitels_ambtenaar.txt"):
        path = data_dir / fname
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            normalized = " ".join(line.lower().split())
            tokens = normalized.split()
            if len(tokens) > 1:
                phrases.append(normalized)
            else:
                words.add(normalized)

    # Generic role / section words not in the title lists but commonly
    # swallowed by Deduce into person spans.
    words |= {
        "betreft",
        "rondvraag",
        "toelichting",
        "bijlage",
        "advies",
        "casemanager",
        "coördinator",
        "hoofd",
        "manager",
        "medewerker",
        "sociaal",
        "domein",
        "zaken",
        "financiën",
        # Document-structure words Deduce absorbs after names
        "geboortedatum",
        "geboorteplaats",
        "woonplaats",
        "nationaliteit",
        "adres",
        "telefoonnummer",
        "emailadres",
    }

    return _TrailingTitleVocab(
        words=frozenset(words),
        phrases=tuple(sorted(phrases, key=len, reverse=True)),
    )


_trailing_title_vocab: _TrailingTitleVocab | None = None


def _get_trailing_titles() -> _TrailingTitleVocab:
    """Return the cached trailing-title vocabulary, loading on first use."""
    global _trailing_title_vocab  # noqa: PLW0603
    if _trailing_title_vocab is None:
        _trailing_title_vocab = _load_trailing_titles()
    return _trailing_title_vocab


# Leading non-name words to strip from person spans — section headings,
# greeting words, and connectors Deduce absorbs into the span.
_LEADING_STRIP_WORDS: frozenset[str] = frozenset(
    {
        "rondvraag",
        "toelichting",
        "bijlage",
        "advies",
        "dag",
        "graag",
        "beste",
        "hallo",
        "hi",
        "collega",
    }
)


def _trim_trailing_titles(text: str, start_char: int, end_char: int) -> tuple[str, int, int]:
    """Strip trailing job titles and section headings from a person span.

    Deduce trained on medical records tends to greedily extend person
    spans to absorb the next capitalized word(s), yielding entities
    like ``"Marieke de Vries Beleidsmedewerker Sociaal Domein"`` or
    ``"S. van Dijk Betreft"``.

    Strategy:
      1. Try stripping multi-word title phrases from the end.
      2. Try stripping single known title words from the end.
      3. If end-stripping didn't help, scan for a known title word
         *inside* the span and truncate everything from that word onward
         (handles "A.B. Bakker Wethouder Ruimtelijke Ordening").
      4. Strip leading section heading words (Rondvraag, etc.).

    Only called for ``persoon`` entities — other types are unaffected.
    """
    vocab = _get_trailing_titles()

    original_text = text

    # Pass 1: strip known words/phrases from the end
    changed = True
    while changed:
        changed = False
        lower = text.lower().rstrip()

        # Multi-word phrases first (longest match)
        for phrase in vocab.phrases:
            if lower.endswith(phrase):
                before = text[: len(text) - len(phrase)].rstrip()
                if before:
                    removed_len = len(text) - len(before)
                    text = before
                    end_char -= removed_len
                    changed = True
                    break

        if changed:
            continue

        # Single trailing word
        tokens = text.rsplit(None, 1)
        if len(tokens) == 2:
            last_word = tokens[1].lower().rstrip(".,;:()")
            if last_word in vocab.words:
                before = tokens[0].rstrip()
                if before:
                    removed_len = len(text) - len(before)
                    text = before
                    end_char -= removed_len
                    changed = True

    # Pass 2: if end-stripping didn't change anything, scan for a known
    # title word inside the span and truncate from there. This catches
    # "A.B. Bakker Wethouder Ruimtelijke Ordening" where "Ordening" by
    # itself isn't a title word, but "Wethouder" is.
    if text == original_text:
        words = text.split()
        # Skip the first 2 words (minimum name) to avoid false cuts on
        # names that accidentally overlap a title word.
        for i in range(2, len(words)):
            if words[i].lower().rstrip(".,;:()") in vocab.words:
                before = " ".join(words[:i]).rstrip()
                if before:
                    removed_len = len(text) - len(before)
                    text = before
                    end_char -= removed_len
                break
            # Also check multi-word phrases starting at this position
            suffix_lower = " ".join(w.lower() for w in words[i:])
            for phrase in vocab.phrases:
                if suffix_lower.startswith(phrase):
                    before = " ".join(words[:i]).rstrip()
                    if before:
                        removed_len = len(text) - len(before)
                        text = before
                        end_char -= removed_len
                    break
            else:
                continue
            break

    # Pass 3: strip leading non-name words — section headings and
    # greeting words that Deduce absorbs into the span.
    # "Dag Yvonne" → "Yvonne", "Graag Dirkse" → "Dirkse",
    # "Rondvraag Raadslid X" → "Raadslid X"
    first_space = text.find(" ")
    if first_space > 0:
        first_word = text[:first_space].lower().strip(".,;:()")
        if first_word in _LEADING_STRIP_WORDS:
            after = text[first_space:].lstrip()
            start_char = end_char - len(after)
            text = after

    return text, start_char, end_char


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
            if not _is_plausible_home_address(annotation.text, text, annotation.start_char):
                logger.debug(
                    "ner.adres_dropped_by_org_filter",
                    start=annotation.start_char,
                )
                continue
            confidence = 0.75
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
            reasoning = "Datum gedetecteerd — mogelijk geboortedatum."
        else:  # organisatie — guaranteed by allowlist above
            confidence = 0.50
            reasoning = "Organisatienaam gedetecteerd — beoordeel of herleidbaar tot persoon."

        trimmed_text, trimmed_start, trimmed_end = _trim_span(
            annotation.text, annotation.start_char, annotation.end_char
        )
        if not trimmed_text:
            continue

        # Strip trailing job titles Deduce absorbed into person spans
        if entity_type == "persoon":
            trimmed_text, trimmed_start, trimmed_end = _trim_trailing_titles(
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
