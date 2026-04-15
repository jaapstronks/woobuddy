"""Name engine — rule-based plausibility scoring for Deduce `persoon` hits.

Deduce (trained on medical records) over-tags institution names, place
names, and fragments as `persoon`. This module provides the cheap
rule-based replacement for the old LLM person-role verification pass:
the Meertens voornamen and CBS achternamen lists give a positive signal
("first token is a known Dutch first name") that sharpens a true hit,
and the absence of any known first or last name is a strong signal
that the detection is junk.

The lists are loaded once at application startup from
`backend/app/data/sources/` and cached on `app.state.name_lists`. See
`docs/todo/done/12-name-lists-meertens-cbs.md` and
`backend/app/data/sources/README.md` for provenance.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)


# The raw files live alongside this module under `backend/app/data/sources/`.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sources"
_VOORNAMEN_FILE = _DATA_DIR / "Top_eerste_voornamen_NL_2017.csv"
_ACHTERNAMEN_FILE = _DATA_DIR / "cbs_achternamen.csv"


# Dutch naamvoorvoegsels ("tussenvoegsels") plus a pragmatic set of
# non-Dutch particles that routinely precede surnames in Woo documents
# (see todo #48 — Woo-stukken name residents, ambtenaren, and
# inspraak-deelnemers with Arabic, Italian, Portuguese, German, … roots).
# A surname may legitimately start with one of these — e.g. "Van den
# Berg", "El Khatib", "Da Silva" — so we strip them before the surname
# lookup while still accepting the span as a potential name. Kept as
# space-joined strings so multi-word tussenvoegsels like "van den" or
# "de la" match too.
_TUSSENVOEGSELS_RAW: tuple[str, ...] = (
    # Dutch
    "van",
    "van den",
    "van der",
    "van de",
    "van 't",
    "van het",
    "de",
    "der",
    "den",
    "ter",
    "ten",
    "te",
    "het",
    "'t",
    "op",
    "op den",
    "op de",
    "aan de",
    "aan den",
    "uit den",
    "uit de",
    "in 't",
    "in de",
    "in den",
    # Arabic / Maghrebi (todo #48). "El" / "Al" before a capitalized
    # surname ("El Khatib", "Al Hassan") needs to be skipped or the CBS
    # lookup lands on the particle instead of the real surname.
    "el",
    "al",
    "abu",
    "abd",
    "ben",
    "bin",
    "ibn",
    # Italian / Portuguese / Brazilian
    "da",
    "do",
    "dos",
    "das",
    "di",
    "del",
    "della",
    "dal",
    "lo",
    "la",
    # Spanish — "de" already covered, add the multi-word forms.
    "de la",
    "de los",
    "de las",
    # German — "von der" mirrors "van der".
    "von",
    "von der",
    "von den",
    "zu",
    "vom",
)


@dataclass(frozen=True)
class NameLists:
    """Normalized first-name / surname / tussenvoegsel lookup sets."""

    first_names: frozenset[str]
    last_names: frozenset[str]
    # Single-token tussenvoegsels, normalized (e.g. "van", "de", "ter").
    tussenvoegsels: frozenset[str]
    # Multi-token tussenvoegsel sequences as tuples of normalized tokens
    # (e.g. ("van", "den"), ("op", "de")). Order matters so we can walk
    # them from the start of a name.
    tussenvoegsel_sequences: frozenset[tuple[str, ...]]


@dataclass
class NameScore:
    """Result of scoring a candidate person span against the name lists."""

    has_known_first_name: bool = False
    has_known_last_name: bool = False
    first_name_index: int | None = None  # token index where the first name lives
    last_name_index: int | None = None  # token index where the surname lives
    is_plausible: bool = False
    matched_tokens: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize(token: str) -> str:
    """Lowercase + strip diacritics (NFKD decomposition).

    Used consistently for both list ingestion and candidate lookup so
    that `Gülnur` matches `gulnur` and `Adrián` matches `adrian`.
    Also strips trailing punctuation (periods, commas) so an initial
    like "A." normalizes to "a".
    """
    if not token:
        return ""
    # Decompose and drop combining marks (diacritics).
    decomposed = unicodedata.normalize("NFKD", token)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    # Strip surrounding whitespace and punctuation that doesn't belong to the name.
    ascii_only = ascii_only.strip().strip(".,;:!?()[]\"'").strip()
    return ascii_only.lower()


def normalize_reference_name(text: str) -> str:
    """Normalize a full name for reference-list matching (#17).

    Used by the per-document reference-list API and by the analyze
    pipeline to decide whether a Deduce `persoon` span matches a name
    the reviewer has marked as "niet lakken". Differs from `_normalize`
    (which operates on a single token) in two ways:

    - Tussenvoegsels are **kept** — "De Vries" normalizes to "de vries",
      not "vries". This is what the reviewer typed; we honour it.
    - Internal whitespace is collapsed to a single space so
      "Jan  de   Vries" and "Jan de Vries" match.

    Otherwise it is the same lowercase + NFKD + strip-combining-marks
    pipeline so "De Vries", "de vries", and "DE VRIES" all match, and
    "Adrián" matches "adrian".
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    # Collapse internal whitespace. `.split()` handles tabs, multi-space,
    # and leading/trailing whitespace in one pass.
    tokens = ascii_only.split()
    return " ".join(tokens).lower()


def _load_csv_names(path: Path) -> frozenset[str]:
    """Load a one-name-per-line CSV into a normalized frozenset.

    Tolerant of `#` comment lines, blank lines, and multi-column rows
    (first column wins — split on `;`, `,`, or tab). Missing files
    return an empty set and log a warning so the pipeline keeps
    running with just the heuristic filter.
    """
    if not path.exists():
        logger.warning("name_engine.source_missing", path=str(path))
        return frozenset()

    names: set[str] = set()
    splitter = re.compile(r"[;,\t]")
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            first = splitter.split(line, maxsplit=1)[0].strip()
            normalized = _normalize(first)
            if normalized:
                names.add(normalized)
    return frozenset(names)


def load_name_lists() -> NameLists:
    """Load Meertens voornamen + CBS achternamen + tussenvoegsels once.

    Call from `main.lifespan` and cache on `app.state.name_lists`. The
    operation is I/O only — normalization is trivial for the current
    list sizes (~1k–10k entries) — so the cost is a few hundred
    microseconds per call at most.
    """
    first_names = _load_csv_names(_VOORNAMEN_FILE)
    last_names = _load_csv_names(_ACHTERNAMEN_FILE)

    single_tussenvoegsels: set[str] = set()
    sequence_tussenvoegsels: set[tuple[str, ...]] = set()
    for tv in _TUSSENVOEGSELS_RAW:
        tokens = tuple(_normalize(t) for t in tv.split())
        tokens = tuple(t for t in tokens if t)
        if not tokens:
            continue
        if len(tokens) == 1:
            single_tussenvoegsels.add(tokens[0])
        else:
            sequence_tussenvoegsels.add(tokens)

    logger.info(
        "name_engine.lists_loaded",
        first_names=len(first_names),
        last_names=len(last_names),
        tussenvoegsels=len(single_tussenvoegsels) + len(sequence_tussenvoegsels),
    )

    return NameLists(
        first_names=first_names,
        last_names=last_names,
        tussenvoegsels=frozenset(single_tussenvoegsels),
        tussenvoegsel_sequences=frozenset(sequence_tussenvoegsels),
    )


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def is_known_first_name(token: str, lists: NameLists) -> bool:
    """Return True if `token` matches any entry in the Meertens list."""
    return _normalize(token) in lists.first_names


def is_known_last_name(token: str, lists: NameLists) -> bool:
    """Return True if `token` matches any entry in the CBS list."""
    return _normalize(token) in lists.last_names


def _skip_leading_tussenvoegsels(
    tokens: list[str],
    start: int,
    lists: NameLists,
) -> int:
    """Walk past any tussenvoegsel sequence starting at `tokens[start]`.

    Returns the index of the first token that is NOT part of a
    tussenvoegsel run. Multi-token sequences ("van den") are preferred
    over single-token matches ("van") so we don't stop halfway through.
    """
    if start >= len(tokens):
        return start

    # Prefer longest multi-token tussenvoegsel match first.
    normalized = [_normalize(t) for t in tokens]
    max_seq_len = max((len(s) for s in lists.tussenvoegsel_sequences), default=0)

    idx = start
    while idx < len(tokens):
        matched = False
        # Try multi-token sequences longest first.
        for seq_len in range(min(max_seq_len, len(tokens) - idx), 1, -1):
            window = tuple(normalized[idx : idx + seq_len])
            if window in lists.tussenvoegsel_sequences:
                idx += seq_len
                matched = True
                break
        if matched:
            continue
        # Try single-token tussenvoegsel.
        if normalized[idx] in lists.tussenvoegsels:
            idx += 1
            continue
        break
    return idx


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def score_person_candidate(text: str, lists: NameLists) -> NameScore:
    """Score a candidate person span against the name lists.

    The heuristic rules:

    - The first non-tussenvoegsel token is checked against the
      first-name list. If it matches, that's a strong positive signal.
    - Every remaining token (and the trailing token in particular) is
      checked against the surname list, with leading tussenvoegsels
      stripped so "Van den Berg" matches on "Berg".
    - `is_plausible` is True when the span contains at least one
      known first name OR at least one known surname. An empty span,
      or a span that is entirely tussenvoegsels/unknown words, is
      rejected.
    """
    score = NameScore()
    stripped = (text or "").strip()
    if not stripped:
        return score

    # Split on whitespace; we keep the ORIGINAL tokens so the returned
    # indices line up with how a caller would see the span.
    tokens = stripped.split()
    if not tokens:
        return score

    # ---- First name: scan tokens left-to-right for the first match. ----
    # Deduce's person span often includes a salutation ("De heer Jan
    # Bakker") or a title ("Dr. Anna Jansen"), so we can't assume the
    # first token is the given name. We skip any leading tussenvoegsels
    # but also fall back to scanning every token so "heer" and "Dr."
    # don't block the Meertens lookup.
    first_non_tv = _skip_leading_tussenvoegsels(tokens, 0, lists)
    for idx in range(first_non_tv, len(tokens)):
        candidate = tokens[idx]
        if _normalize(candidate) in lists.first_names:
            score.has_known_first_name = True
            score.first_name_index = idx
            score.matched_tokens.append(candidate)
            break

    # ---- Last name: scan remaining tokens, allowing interior tussenvoegsels. ----
    # Typical Dutch names put the surname last: "Jan de Vries", "A.M.
    # van der Berg". We walk from the end backwards, skipping
    # tussenvoegsels, to find the rightmost non-tussenvoegsel token.
    for idx in range(len(tokens) - 1, -1, -1):
        normalized = _normalize(tokens[idx])
        if not normalized:
            continue
        if normalized in lists.tussenvoegsels:
            continue
        if normalized in lists.last_names:
            score.has_known_last_name = True
            score.last_name_index = idx
            if tokens[idx] not in score.matched_tokens:
                score.matched_tokens.append(tokens[idx])
        break

    # If we didn't find a surname at the tail, also try any interior
    # token (e.g. "Jan Bakker de Grote" — "Bakker" is the surname). We
    # only record the first hit so the score stays deterministic.
    if not score.has_known_last_name:
        for idx, tok in enumerate(tokens):
            if idx == score.first_name_index:
                continue
            normalized = _normalize(tok)
            if normalized in lists.last_names:
                score.has_known_last_name = True
                score.last_name_index = idx
                score.matched_tokens.append(tok)
                break

    score.is_plausible = score.has_known_first_name or score.has_known_last_name
    return score
