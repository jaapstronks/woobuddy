"""Address / public-contact whitelisting.

Value-based checks (postcode, street, info-email, general phone,
municipal website) are not context-gated — these values are public
everywhere regardless of the surrounding document. The postbus check
IS context-gated: callers that want it must pass ``full_text`` and
``start_char`` so the engine can inspect the characters before the
span.
"""

from __future__ import annotations

import re

from ._text import _normalize_phrase, _strip_bbox_markers
from ._types import WhitelistIndex

# "Postbus <nummer>" immediately preceding a postcode indicates an
# organisational PO-box address — structurally never a person's home
# address. We suppress such postcodes from Tier 1 auto-redact even
# though the bare regex in ``ner_engine`` flags them. The window is
# deliberately tight (30 chars) so an unrelated "Postbus" earlier in
# the same sentence cannot leak into a real residential postcode
# later on the line. The anchor ``\Z`` forces the match to butt up
# against the end of the look-behind window, i.e. directly against
# the postcode span.
_POSTBUS_PREFIX_RE = re.compile(r"(?i)\bpostbus\s+\d{1,6}[\s,.;:\-]*\Z")


def is_postbus_context_postcode(
    full_text: str,
    start_char: int,
    window: int = 30,
) -> bool:
    """True when the postcode at ``start_char`` is immediately preceded
    by a ``Postbus <nummer>`` construction within ``window`` characters.

    Used to suppress Tier 1 postcode auto-redaction when the postcode is
    part of an organisational PO-box address. See the module docstring
    for the rationale.
    """
    if not full_text or start_char <= 0:
        return False
    before = full_text[max(0, start_char - window) : start_char]
    return _POSTBUS_PREFIX_RE.search(before) is not None


def match_address_whitelist(
    detection_text: str,
    entity_type: str,
    index: WhitelistIndex,
    full_text: str | None = None,
    start_char: int | None = None,
) -> str | None:
    """Return a Dutch reason string when the detection matches a municipal
    public-address/contact value, or ``None`` when nothing matches.

    The value-based checks (postcode, street, info-email, general phone,
    municipal website) are not context-gated — these values are public
    everywhere regardless of the surrounding document. The *postbus*
    check is context-gated: callers that want it must pass ``full_text``
    and ``start_char`` so the engine can inspect the characters before
    the span. Omitting them preserves the pre-postbus-rule behaviour.
    """
    if not detection_text:
        return None

    text = detection_text.strip()

    if entity_type == "postcode":
        normalized = text.replace(" ", "").upper()
        if normalized in index.postcodes:
            return "Postcode van een gemeentelijk adres — openbare informatie."
        if (
            full_text is not None
            and start_char is not None
            and is_postbus_context_postcode(full_text, start_char)
        ):
            return "Postcode hoort bij een postbusadres — geen persoonlijk adres."
        return None

    if entity_type == "email":
        if text.lower() in index.emails:
            return "Algemeen e-mailadres van een gemeente — openbare informatie."
        return None

    if entity_type == "telefoon":
        digits = re.sub(r"\D+", "", text)
        if digits and digits in index.phones:
            return "Algemeen telefoonnummer van een gemeente — openbare informatie."
        return None

    if entity_type == "url":
        lower = text.lower().rstrip("/")
        if lower in index.websites:
            return "Officiële website van een gemeente — openbare informatie."
        # Also accept a prefix match so a deep link under gemeente.nl
        # still whitelists.
        for site in index.websites:
            if lower.startswith(site):
                return "Pagina op een officiële gemeentelijke website — openbare informatie."
        return None

    if entity_type == "adres":
        normalized = _normalize_phrase(_strip_bbox_markers(text))
        if normalized in index.addresses:
            return "Bezoekadres/Woo-adres van een gemeente — openbare informatie."
        # Street-only match (no huisnummer) — still public.
        if normalized in index.woonplaatsen:
            return "Woonplaats van een gemeentelijk adres — openbare informatie."
        return None

    return None
