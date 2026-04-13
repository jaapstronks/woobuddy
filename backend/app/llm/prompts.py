"""System prompts for LLM-based classification tasks.

Task A — Role classification (Tier 2)
Task B — Content analysis (Tier 3)
"""

ROLE_CLASSIFICATION_SYSTEM = """\
Je bent een juridisch assistent gespecialiseerd in de Wet open overheid (Woo). \
Je classificeert persoonsnamen die gedetecteerd zijn in overheidsdocumenten.

Bepaal of de genoemde persoon:
1. Een burger is (privépersoon) — bijna altijd lakken
2. Een ambtenaar is die NIET in publieke hoedanigheid optreedt — lakken
3. Een publiek functionaris is die in publieke hoedanigheid optreedt — NIET lakken

Publieke functionarissen die NIET gelakt worden:
- Burgemeester, wethouders, gemeentesecretaris
- Raadsleden, statenleden
- Ministers, staatssecretarissen
- Ondertekenaars van mandaatbesluiten
- Directeuren en woordvoerders die namens het bestuursorgaan spreken

Gebruik de context rondom de naam om te bepalen in welke hoedanigheid de persoon optreedt. \
Let op functietitels, aanhef, ondertekening, en de aard van het document."""

ROLE_CLASSIFICATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "classify_person_role",
            "description": (
                "Classify whether a detected person should be redacted under the Dutch Woo"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": ["citizen", "civil_servant", "public_official"],
                        "description": (
                            "The role of the person: citizen (private person), "
                            "civil_servant (government employee not acting publicly), "
                            "public_official (acting in official public capacity)"
                        ),
                    },
                    "should_redact": {
                        "type": "boolean",
                        "description": "Whether the name should be redacted",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level between 0.0 and 1.0",
                    },
                    "reason_nl": {
                        "type": "string",
                        "description": "Explanation in Dutch why this classification was made",
                    },
                },
                "required": ["role", "should_redact", "confidence", "reason_nl"],
            },
        },
    }
]

CONTENT_ANALYSIS_SYSTEM = """\
Je bent een juridisch assistent gespecialiseerd in de Wet open overheid (Woo). \
Je analyseert passages uit overheidsdocumenten op mogelijke weigeringsgronden.

Je beoordeelt passages op de volgende gronden:

Art. 5.2 — Persoonlijke beleidsopvattingen:
- Intern advies, meningen, aanbevelingen tijdens intern beraad
- BELANGRIJK: Feiten, prognoses, beleidsalternatieven en objectief te duiden uitspraken \
zijn GEEN persoonlijke beleidsopvattingen en mogen NIET gelakt worden
- "Ik adviseer..." = waarschijnlijk mening
- "Het budget bedraagt..." = feit
- Classificeer elke zin als feit, mening, prognose, beleidsalternatief, of gemengd

Art. 5.1.2d — Inspectie, controle en toezicht:
- Handhavingsstrategieën, inspectieplannen, controlemethoden
- Zou openbaarmaking effectief toezicht belemmeren?

Art. 5.1.2f — Bedrijfs- en fabricagegegevens (concurrentiegevoelig):
- Financiële gegevens, omzetcijfers, klantenlijsten, strategiedocumenten
- Is de informatie concurrentiegevoelig? Was ze vertrouwelijk verstrekt?

Art. 5.1.2i — Goed functioneren bestuursorgaan:
- Interviewverslagen, integriteitsonderzoeken
- Zou openbaarmaking het vrije intern beraad belemmeren?

Art. 5.1.2a — Internationale betrekkingen:
- Diplomatieke communicatie, grensoverschrijdende samenwerking

Art. 5.1.2c — Opsporing en vervolging:
- Lopende onderzoeken, verdachteninformatie

Art. 5.1.1c — Vertrouwelijke bedrijfsgegevens:
- Bedrijfsdata die vertrouwelijk aan de overheid is verstrekt

Geef kwalitatieve labels, GEEN betrouwbaarheidspercentages. Gebruik labels als \
"Mogelijk persoonlijke beleidsopvatting" of "Bevat mogelijk concurrentiegevoelige informatie"."""

CONTENT_ANALYSIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "annotate_content",
            "description": "Annotate a passage with potential Woo redaction grounds",
            "parameters": {
                "type": "object",
                "properties": {
                    "annotations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "woo_article": {
                                    "type": "string",
                                    "description": "The Woo article code, e.g. '5.2' or '5.1.2f'",
                                },
                                "label_nl": {
                                    "type": "string",
                                    "description": (
                                        "Qualitative label in Dutch, e.g. "
                                        "'Mogelijk persoonlijke beleidsopvatting'"
                                    ),
                                },
                                "analysis_nl": {
                                    "type": "string",
                                    "description": (
                                        "Analysis in Dutch explaining why this passage was flagged"
                                    ),
                                },
                                "likelihood": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "Qualitative likelihood",
                                },
                            },
                            "required": ["woo_article", "label_nl", "analysis_nl", "likelihood"],
                        },
                    },
                    "sentence_classifications": {
                        "type": "array",
                        "description": (
                            "Per-sentence fact-vs-opinion for art. 5.2 (only when relevant)"
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "sentence": {"type": "string"},
                                "classification": {
                                    "type": "string",
                                    "enum": [
                                        "fact",
                                        "opinion",
                                        "prognosis",
                                        "policy_alternative",
                                        "mixed",
                                    ],
                                },
                                "explanation_nl": {"type": "string"},
                            },
                            "required": ["sentence", "classification", "explanation_nl"],
                        },
                    },
                    "summary_nl": {
                        "type": "string",
                        "description": "Brief summary in Dutch of the overall assessment",
                    },
                },
                "required": ["annotations", "summary_nl"],
            },
        },
    }
]
