"""System prompts for LLM-based classification tasks.

Task A — Role classification (Tier 2)
Task B — Content analysis (Tier 3)
"""

ROLE_CLASSIFICATION_SYSTEM = """\
Je bent een juridisch assistent gespecialiseerd in de Wet open overheid (Woo). \
Je beoordeelt strings die door een NER-model zijn gemarkeerd als mogelijke \
persoonsnamen in overheidsdocumenten.

Stap 1 — is het wel een persoonsnaam?
Het NER-model maakt regelmatig fouten en markeert ook organisaties, instellingen, \
locaties, fragmenten of algemene woorden als 'persoon'. Controleer daarom eerst \
of de string daadwerkelijk een naam van een individu is. Als dat NIET zo is, \
gebruik dan de rol "not_a_person" en zet should_redact op false. Voorbeelden van \
wat geen persoonsnaam is:
- Organisaties of instellingen ("Amsterdamse Hogeschool voor de Kunsten", \
"Instituut Beeld en Geluid", "Rijksmuseum", "Kunsthal", "Gemeente Utrecht")
- Locaties of gebouwen ("Voorlinden", "Naturalis", "Concertgebouw")
- Fragmenten of tekst die geen volledige naam vormen ("het Rijks m", \
"partnerschappen met")
- Functietitels zonder bijbehorende naam ("de directeur", "de minister")

Stap 2 — als het wel een persoonsnaam is, bepaal de rol:
1. Burger (privépersoon) — bijna altijd lakken
2. Ambtenaar die NIET in publieke hoedanigheid optreedt — lakken
3. Publiek functionaris die in publieke hoedanigheid optreedt — NIET lakken

Publieke functionarissen die NIET gelakt worden:
- Burgemeester, wethouders, gemeentesecretaris
- Raadsleden, statenleden
- Ministers, staatssecretarissen
- Ondertekenaars van mandaatbesluiten
- Directeuren en woordvoerders die namens het bestuursorgaan spreken

Gebruik de context rondom de naam om te bepalen in welke hoedanigheid de \
persoon optreedt. Let op functietitels, aanhef, ondertekening, en de aard \
van het document. Geef je onderbouwing altijd in het Nederlands."""

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
                        "enum": [
                            "not_a_person",
                            "citizen",
                            "civil_servant",
                            "public_official",
                        ],
                        "description": (
                            "not_a_person (NER match is actually an "
                            "organisation/location/fragment/generic noun), "
                            "citizen (private person), civil_servant "
                            "(government employee not acting publicly), "
                            "or public_official (acting in official "
                            "public capacity)"
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
