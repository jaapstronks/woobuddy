"""Environmental-content classifier (Art. 5.1 lid 6-7 Woo).

Environmental information has restricted redaction possibilities under
the Woo — the pipeline flags documents containing environmental
signals so the frontend can warn the reviewer. The detection is a
simple keyword scan against the combined full text; nothing else in
the pipeline consumes the keyword list today.

Extracted from `pipeline_engine.py` so the rule can be tested in
isolation and grown without reopening the orchestration module.
"""

import re

# Environmental information keywords (Art. 5.1 lid 6-7 Woo).
_ENVIRONMENTAL_SIGNALS = [
    r"milieu",
    r"luchtkwaliteit",
    r"bodemverontreiniging",
    r"waterkwaliteit",
    r"geluidshinder",
    r"geluidsoverlast",
    r"emissie",
    r"uitstoot",
    r"fijnstof",
    r"stikstof",
    r"PFAS",
    r"asbest",
    r"afvalstoffen",
    r"afvalwater",
    r"grondwater",
    r"oppervlaktewater",
    r"lozingen",
    r"milieuvergunning",
    r"omgevingsvergunning",
    r"bestrijdingsmiddelen",
    r"biodiversiteit",
    r"natuurbescherming",
    r"Natura\s*2000",
    r"gezondheidsrisico",
    r"volksgezondheid",
    r"energieverbruik",
    r"CO2",
    r"klimaat",
    r"stralingsbescherming",
]

_ENVIRONMENTAL_PATTERN = re.compile(
    r"\b(?:" + "|".join(_ENVIRONMENTAL_SIGNALS) + r")\b",
    re.IGNORECASE,
)


def check_environmental_content(text: str) -> bool:
    """Return True if `text` contains environmental information (Art. 5.1 lid 6-7 Woo)."""
    return bool(_ENVIRONMENTAL_PATTERN.search(text))
