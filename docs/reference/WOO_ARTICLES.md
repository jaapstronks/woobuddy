# WOO Buddy — Woo Articles Reference

Overview of all Woo (Wet open overheid) chapter 5 articles with their detection approach per tier.

---

## Absolute Grounds (Art. 5.1 lid 1)

These always apply — no interest-weighing needed.

### Art. 5.1.1c — Bedrijfs- en fabricagegegevens (vertrouwelijk verstrekt)

Business and manufacturing data that was confidentially provided to the government.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis — identify confidential business data based on document context and confidentiality markers |
| **UX** | Annotation with decision support. Human determines whether the data was truly provided confidentially |
| **Auto-redact** | No |

### Art. 5.1.1d — Bijzondere persoonsgegevens

Special categories of personal data: race/ethnicity, political opinions, religious beliefs, union membership, genetic/biometric data, health data, sexual orientation, criminal convictions.

| Aspect | Detail |
|--------|--------|
| **Tier** | 2 (primary) + 3 (edge cases) |
| **Detection** | Tier 2: Medical NER (UMLS terminology, medication names), keyword matching for sensitive categories. Tier 3: LLM analysis for subtle references |
| **UX** | Tier 2: Suggested redaction with one-click confirm. Tier 3: Full analysis panel for ambiguous cases |
| **Auto-redact** | No — even though the ground is absolute, detection confidence varies |

### Art. 5.1.1e — Identificatienummers

BSN (burgerservicenummer), BIG-nummer, AGB-code, patient numbers.

| Aspect | Detail |
|--------|--------|
| **Tier** | 1 |
| **Detection** | Regex with validation (BSN: 11-proef, credit cards: Luhn check). High certainty pattern matching |
| **UX** | Auto-redacted. Reviewer sees black bars. One-click un-redact for exceptions |
| **Auto-redact** | Yes |
| **Motivation** | Auto-generated: "Het identificatienummer is gelakt op grond van art. 5.1 lid 1 sub e Woo." |

---

## Relative Grounds (Art. 5.1 lid 2)

These require an interest-weighing — the interest of withholding must outweigh the interest of disclosure.

### Art. 5.1.2a — Internationale betrekkingen

Diplomatic relations, cross-border cooperation, international treaties.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis — identify references to international relations, diplomatic communications, cross-border cooperation |
| **UX** | Full decision panel with interest-weighing checklist |
| **Auto-redact** | No |
| **Five-year rule** | Applies — warn if document is older than 5 years |

### Art. 5.1.2c — Opsporing en vervolging van strafbare feiten

References to ongoing criminal investigations, prosecutions, enforcement actions.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis — identify references to ongoing investigations, suspect information, enforcement strategies |
| **UX** | Full decision panel with interest-weighing checklist |
| **Auto-redact** | No |
| **Five-year rule** | Applies |

### Art. 5.1.2d — Inspectie, controle en toezicht

Inspection strategies, enforcement plans, audit approaches, oversight methods.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis — identify inspection strategies, enforcement plans, control methods that would be undermined by disclosure |
| **UX** | Full decision panel with interest-weighing checklist |
| **Auto-redact** | No |
| **Five-year rule** | Applies |

### Art. 5.1.2e — Persoonlijke levenssfeer

Names of private persons, email addresses, phone numbers, home addresses, IBAN numbers, dates of birth, license plates.

This is the **most frequently applied ground** in Woo practice and spans all three tiers.

| Entity | Tier | Detection |
|--------|------|-----------|
| BSN, IBAN, phone, email, postcode, license plate | 1 | Regex + validation |
| Person names (citizens) | 2 | Deduce NER + role classification |
| Person names (officials — do NOT redact) | 2 | Deduce NER + public officials reference list |
| Home addresses + house numbers | 2 | Deduce NER |
| Dates of birth | 1 or 2 | Regex (standalone) or NER (in context) |
| Function titles traceable to individuals | 2/3 | LLM traceability assessment |

| Aspect | Detail |
|--------|--------|
| **UX** | Tier 1: Auto-redacted. Tier 2: Suggested with one-click confirm/reject. Context panel shows reasoning |
| **Auto-redact** | Tier 1 entities only |
| **Five-year rule** | Applies |
| **Name propagation** | When a reviewer confirms a name, all other occurrences across the dossier are auto-accepted |
| **Motivation** | "De persoonsgegevens zijn gelakt ter bescherming van de persoonlijke levenssfeer (art. 5.1 lid 2 sub e Woo). Het belang van eerbiediging van de persoonlijke levenssfeer weegt zwaarder dan het belang van openbaarmaking." |

**Exceptions (do NOT redact):**
- Public officials acting in official capacity (burgemeester, wethouders, gemeentesecretaris, raadsleden)
- Information already publicly available (Handelsregister, public BIG-register)
- Information where the person has given explicit consent

### Art. 5.1.2f — Bedrijfs- en fabricagegegevens (concurrentiegevoelig)

Competitively sensitive business information, trade secrets, financial data, client lists, strategy documents.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis — identify financial data, revenue figures, client lists, strategy documents, tender offers |
| **UX** | Full decision panel. Key question: is the business information competitively sensitive? Was it provided confidentially? |
| **Auto-redact** | No |
| **Five-year rule** | Applies |

### Art. 5.1.2h — Beveiliging van personen en bedrijven

Security details, access codes, building security plans, personal protection arrangements.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 (with some Tier 1 for access codes/passwords) |
| **Detection** | LLM analysis for security context. Regex for obvious patterns (access codes, passwords) |
| **UX** | Full decision panel |
| **Auto-redact** | No (except obvious access codes) |
| **Five-year rule** | Applies |

### Art. 5.1.2i — Goed functioneren van de Staat, bestuursorganen of andere overheidsorganen

Information that would impair frank internal deliberation, integrity investigations, interview records.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis — identify internal deliberation content, integrity investigations, information whose disclosure would impair government functioning |
| **UX** | Full decision panel with interest-weighing checklist |
| **Auto-redact** | No |
| **Five-year rule** | Applies |

---

## Personal Policy Opinions (Art. 5.2)

Special regime — the most complex article in Woo practice.

### Art. 5.2 — Persoonlijke beleidsopvattingen

Internal policy advice, opinions, recommendations made during "intern beraad" (internal deliberation).

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | LLM analysis with fact-vs-opinion classification per sentence |
| **Indicators** | "Ik adviseer...", "mijn inschatting is...", "het lijkt mij verstandig...", "ik zou voorstellen..." |
| **UX** | Full decision panel with **fact-vs-opinion indicator** per sentence |
| **Auto-redact** | No |

**Critical rules:**
- Facts, prognoses, policy alternatives, and objectively-natured content are explicitly **NOT** personal policy opinions and **may NOT** be redacted under 5.2
- "Het budget bedraagt EUR 2M" = fact (may not redact)
- "Ik adviseer om optie B te kiezen" = opinion (may redact)
- In formal administrative decisions, personal policy opinions must be provided in **anonymized form**
- The fact-vs-opinion distinction is the hardest judgment call in Woo practice

**LLM output for art. 5.2:**
- Possible applicable grounds, ranked by likelihood
- Per-sentence fact/opinion classification
- Analysis text explaining why the passage was flagged
- Three decision buttons: Redact / Don't redact / Defer

---

## Residual Ground

### Art. 5.1 lid 5 — Onevenredige benadeling

Disproportionate disadvantage. Only applicable in exceptional cases. May NOT be used as a subsidiary ground when another specific ground could apply.

| Aspect | Detail |
|--------|--------|
| **Tier** | 3 |
| **Detection** | Not actively detected — available as a manual ground choice when no other article fits |
| **UX** | Selectable in the Tier 3 decision panel when the reviewer chooses a ground |
| **Auto-redact** | No |

---

## Cross-Cutting Rules

### Five-Year Rule (Art. 5.3)

Relative grounds (Art. 5.1 lid 2) do **not** automatically apply to information older than five years. The system must:
- Detect document dates from metadata and content
- Warn when a relative ground is applied to a document older than 5 years
- Require extra justification from the reviewer

### Environmental Information (Art. 5.1 lid 6-7)

Environmental information (air, water, soil, energy, emissions, health effects) has more limited redaction possibilities. The system must:
- Detect environmental content
- Flag which grounds are restricted for environmental information

### Third-Party Consultation (Zienswijze)

When detected passages concern third parties (companies, citizens whose data appears), the system must flag that a formal consultation procedure may be required before publication.

---

## Detection Summary by Tier

### Tier 1 — Regex + Validation (auto-redact)

| Entity | Pattern | Article |
|--------|---------|---------|
| BSN | 9 digits, 11-proef validation | 5.1.1e |
| IBAN | NL + 2 digits + 4 letters + 10 digits | 5.1.2e |
| Phone numbers | Dutch mobile/landline patterns | 5.1.2e |
| Email addresses | Standard email regex | 5.1.2e |
| Postcodes | 4 digits + 2 letters | 5.1.2e |
| License plates | Dutch license plate patterns | 5.1.2e |
| Credit card numbers | Luhn check validation | 5.1.2e |
| Passport/driver's license numbers | Pattern matching | 5.1.1e |

### Tier 2 — NER + Role Classification (suggested)

| Entity | Detection | Article |
|--------|-----------|---------|
| Person names (private citizens) | Deduce NER + role classification | 5.1.2e |
| Person names (non-public civil servants) | Deduce NER + role classification | 5.1.2e |
| Person names (public officials) | Deduce NER + reference list → do NOT redact | — |
| Street addresses + house numbers | Deduce NER | 5.1.2e |
| Special personal data (medical) | Medical NER, medication names | 5.1.1d |
| Special personal data (other) | Keyword matching for sensitive categories | 5.1.1d |
| Traceable function titles | LLM traceability assessment | 5.1.2e |

### Tier 3 — LLM Analysis (annotated)

| Content | Analysis | Article(s) |
|---------|----------|------------|
| Personal policy opinions | Fact-vs-opinion classification | 5.2 |
| Competitive business data | Sensitivity + confidentiality assessment | 5.1.2f |
| Inspection/oversight strategies | Impairment assessment | 5.1.2d |
| Government functioning | Frank deliberation impairment | 5.1.2i |
| International relations | Diplomatic sensitivity | 5.1.2a |
| Criminal investigation references | Ongoing investigation assessment | 5.1.2c |
| Security information | Security risk assessment | 5.1.2h |
| Confidential business data | Confidentiality assessment | 5.1.1c |
