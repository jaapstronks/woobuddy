# Test fixtures — WOO Buddy

PDF fixtures for testing end-to-end detection (upload → client extraction → server NER → review list). All data is fictional.

## Originals (hand-crafted)

| File | Tests |
|---|---|
| `besluit_brief.pdf` | Standard Woo decision letter to a citizen. Basic Tier 1 coverage: BSN, postcode, Dutch mobile, email, name, address, date. |
| `besluit_ambtenaar.pdf` | Public officials scenario — wethouder, raadsleden, gemeentesecretaris. Should be flagged but typically not redacted. |
| `edge_cases.pdf` | Meeting minutes with mixed citizens + businesses. KvK numbers (should NOT be redacted), house-number references, organization names. |
| `email_mixed.pdf` | Email thread with IBAN, email, phone, license plate, foreign name, a 9-digit non-BSN, a fake birthdate. |
| `nota_gezondheid.pdf` | Tier 3 — health info (Art 5.1.2d bijzondere persoonsgegevens), religion, BSN, IBAN, address. Stress-tests content judgment. |

## Generated (synthetic, regenerate with `generate_fixtures.py`)

| File | Tests |
|---|---|
| `tier1_all_identifiers.pdf` | Every Tier 1 regex pattern in every accepted variant — compact & spaced IBAN, lowercase IBAN, mobile/landline/international phone, plus-addressing email, long hyphenated URL, postcode with/without space, all sidecode license plates, Luhn-valid credit card. Includes negative controls (invalid BSN, failing-Luhn card, foreign IBAN, lowercase postcode) that must NOT fire. |
| `false_positives.pdf` | Deliberate traps: 9-digit reference numbers that fail 11-proef, foreign IBANs, KvK numbers, project numbers shaped like plates, year ranges shaped like dates, and institution names Deduce historically mis-tagged as persons (Amsterdamse Hogeschool, Rijksmuseum, Kunsthal, Universiteit Utrecht, Ministerie van OCW, gemeente Amsterdam, Stichting Cultuurfonds, Vereniging Nederlandse Musea). |
| `raadsvergadering.pdf` | Mixed public/private scenario. Public functionaries (burgemeester, wethouders, raadsleden, gemeentesecretaris, Commissaris van de Koning) should be flagged but typically not redacted. Private citizens (inspreker + her named neighbours) should be flagged AND redacted. Tests that the detector surfaces everyone for human review. |

## Regenerating

```bash
cd backend && source .venv/bin/activate
python ../tests/fixtures/generate_fixtures.py
```

The generator only writes the three files in the "Generated" table above — the hand-crafted originals are never touched.
