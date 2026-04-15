"""Deduce (Dutch NER) lazy-init + name-list lazy-init.

Both Deduce and the Meertens + CBS name lists take ~1–2s to load, so
they are cached at module level and pre-warmed from the FastAPI
lifespan via ``init_deduce`` / ``init_name_lists``.
"""

from __future__ import annotations

from typing import Any

from app.logging_config import get_logger
from app.services.name_engine import NameLists, load_name_lists

logger = get_logger(__name__)


# Lazy-loaded Deduce instance (takes ~2s to initialize)
_deduce_instance: Any = None

# Lazy-loaded name lists (Meertens voornamen + CBS achternamen + tussenvoegsels).
# Populated once at startup via `init_name_lists()`, or lazily on first use.
_name_lists: NameLists | None = None


def _get_deduce() -> Any:
    """Get or initialize the Deduce instance.

    Return type is `Any` because the upstream `deduce` package ships
    without type stubs — typing it as a concrete class would just push
    the `import-untyped` warning around without buying anything.
    """
    global _deduce_instance
    if _deduce_instance is None:
        from deduce import Deduce

        _deduce_instance = Deduce()
        logger.info("ner.deduce_loaded")
    return _deduce_instance


def init_deduce() -> None:
    """Pre-initialize Deduce (call during app startup)."""
    _get_deduce()


def init_name_lists() -> NameLists:
    """Pre-initialize the Meertens + CBS name lists (call during app startup)."""
    global _name_lists
    if _name_lists is None:
        _name_lists = load_name_lists()
    return _name_lists


def _get_name_lists() -> NameLists:
    """Return the cached name lists, loading them on first use."""
    global _name_lists
    if _name_lists is None:
        _name_lists = load_name_lists()
    return _name_lists


# Mapping from Deduce annotation tags to our entity types
_DEDUCE_TAG_MAP: dict[str, str] = {
    "naam": "persoon",
    "voornaam": "persoon",
    "achternaam": "persoon",
    "initiaal": "persoon",
    "persoon": "persoon",
    "patient": "persoon",
    "locatie": "adres",
    "adres": "adres",
    "straat": "adres",
    "huisnummer": "adres",
    "postcode": "postcode",
    "woonplaats": "adres",
    "instelling": "organisatie",
    "ziekenhuis": "organisatie",
    "datum": "datum",
    "leeftijd": "leeftijd",
    "telefoonnummer": "telefoon",
    "url": "url",
    "bsn": "bsn",
}
