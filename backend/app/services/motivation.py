"""Motivation text generation service.

Generates Dutch motivation texts for redaction decisions that can be used
in the formal Woo decision document. Texts are auto-generated based on
the detection tier, entity type, and Woo article, then editable by the reviewer.
"""

import logging

from app.models.schemas import Detection

logger = logging.getLogger(__name__)

# Standard motivation texts per Woo article
_MOTIVATIONS: dict[str, str] = {
    "5.1.1c": (
        "De informatie betreft bedrijfs- en fabricagegegevens die vertrouwelijk "
        "aan de overheid zijn medegedeeld. Op grond van artikel 5.1 lid 1 sub c "
        "Woo wordt deze informatie niet openbaar gemaakt."
    ),
    "5.1.1d": (
        "De informatie betreft bijzondere persoonsgegevens als bedoeld in "
        "artikel 5.1 lid 1 sub d Woo. Deze gegevens worden niet openbaar gemaakt."
    ),
    "5.1.1e": (
        "Het betreft een identificatienummer als bedoeld in artikel 5.1 lid 1 "
        "sub e Woo. Dit nummer wordt niet openbaar gemaakt."
    ),
    "5.1.2a": (
        "Openbaarmaking van deze informatie zou de betrekkingen van Nederland "
        "met andere landen of met internationale organisaties kunnen schaden "
        "(artikel 5.1 lid 2 sub a Woo). Het belang van het voorkomen van "
        "schade aan deze betrekkingen weegt zwaarder dan het belang van openbaarmaking."
    ),
    "5.1.2c": (
        "Openbaarmaking van deze informatie zou de opsporing en vervolging van "
        "strafbare feiten kunnen belemmeren (artikel 5.1 lid 2 sub c Woo). "
        "Het belang van opsporing en vervolging weegt zwaarder dan het belang "
        "van openbaarmaking."
    ),
    "5.1.2d": (
        "Openbaarmaking van deze informatie zou het toezicht door of vanwege "
        "een bestuursorgaan kunnen belemmeren (artikel 5.1 lid 2 sub d Woo). "
        "Het belang van effectief toezicht weegt zwaarder dan het belang van "
        "openbaarmaking."
    ),
    "5.1.2e": (
        "De informatie bevat persoonsgegevens en openbaarmaking zou inbreuk "
        "maken op de persoonlijke levenssfeer (artikel 5.1 lid 2 sub e Woo). "
        "Het belang van eerbiediging van de persoonlijke levenssfeer weegt in "
        "dit geval zwaarder dan het belang van openbaarmaking."
    ),
    "5.1.2f": (
        "De informatie betreft bedrijfs- en fabricagegegevens die door "
        "openbaarmaking onevenredig zouden kunnen worden benadeeld "
        "(artikel 5.1 lid 2 sub f Woo). Het belang van bescherming van "
        "deze gegevens weegt zwaarder dan het belang van openbaarmaking."
    ),
    "5.1.2h": (
        "Openbaarmaking van deze informatie zou de beveiliging van personen "
        "of bedrijven in gevaar kunnen brengen (artikel 5.1 lid 2 sub h Woo). "
        "Het belang van beveiliging weegt zwaarder dan het belang van openbaarmaking."
    ),
    "5.1.2i": (
        "Openbaarmaking van deze informatie zou het goed functioneren van "
        "het bestuursorgaan onevenredig kunnen schaden (artikel 5.1 lid 2 "
        "sub i Woo). Het belang van goed functioneren weegt zwaarder dan "
        "het belang van openbaarmaking."
    ),
    "5.2": (
        "De informatie betreft persoonlijke beleidsopvattingen in het kader "
        "van intern beraad (artikel 5.2 Woo). Deze worden niet openbaar gemaakt."
    ),
    "5.1.5": (
        "Openbaarmaking van deze informatie zou leiden tot onevenredige "
        "benadeling van bij de aangelegenheid betrokken partijen "
        "(artikel 5.1 lid 5 Woo)."
    ),
}

# Entity-specific motivation additions for art. 5.1.2e
_ENTITY_SPECIFICS: dict[str, str] = {
    "persoon": "De naam van betrokkene is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "bsn": "Het burgerservicenummer (BSN) is gelakt.",
    "iban": "Het IBAN-nummer is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "telefoon": "Het telefoonnummer is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "email": "Het e-mailadres is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "adres": "Het adres is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "postcode": "De postcode is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "kenteken": "Het kenteken is gelakt ter bescherming van de persoonlijke levenssfeer.",
    "creditcard": "Het creditcardnummer is gelakt.",
}


def generate_motivation(
    woo_article: str,
    entity_type: str | None = None,
    tier: str = "1",
) -> str:
    """Generate a standard motivation text for a detection."""
    base = _MOTIVATIONS.get(woo_article, "")
    if not base:
        return f"Gelakt op grond van artikel {woo_article} Woo."

    if entity_type and woo_article == "5.1.2e":
        specific = _ENTITY_SPECIFICS.get(entity_type, "")
        if specific:
            return f"{specific} {base}"

    return base


def generate_motivation_for_detection(detection: Detection) -> str:
    """Generate motivation text for a Detection ORM instance."""
    if not detection.woo_article:
        return ""
    return generate_motivation(
        woo_article=detection.woo_article,
        entity_type=detection.entity_type,
        tier=detection.tier,
    )
