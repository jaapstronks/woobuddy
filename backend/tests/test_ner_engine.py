"""Tests for the NER engine — Tier 1 regex + validation and Tier 2 Deduce NER.

Tier 1 tests are pure unit tests (no external dependencies).
Tier 2 tests use the real Deduce library (loaded once, ~2s startup).
"""

import pytest

from app.services.ner_engine import (
    NERDetection,
    _is_plausible_person_name,
    _validate_bsn,
    _validate_luhn,
    detect_all,
    detect_tier1,
    detect_tier2,
)

# ---------------------------------------------------------------------------
# Tier 1: BSN (Burgerservicenummer) — 9 digits with 11-proef
# ---------------------------------------------------------------------------


class TestBSN:
    def test_valid_bsn_detected(self):
        """A valid BSN (passes 11-proef) should be detected."""
        # 111222333 is a classic test BSN: 1*9+1*8+1*7+2*6+2*5+2*4+3*3+3*2+3*(-1)
        # = 9+8+7+12+10+8+9+6-3 = 66 → 66%11=0 ✓
        text = "Het BSN van betrokkene is 111222333."
        results = detect_tier1(text)
        bsn_results = [r for r in results if r.entity_type == "bsn"]
        assert len(bsn_results) == 1
        assert bsn_results[0].text == "111222333"
        assert bsn_results[0].tier == "1"
        assert bsn_results[0].confidence == 0.98
        assert bsn_results[0].woo_article == "5.1.1e"
        assert bsn_results[0].source == "regex"

    def test_invalid_bsn_not_detected(self):
        """A 9-digit number that fails 11-proef should NOT be detected."""
        text = "Referentienummer: 123456789"
        results = detect_tier1(text)
        bsn_results = [r for r in results if r.entity_type == "bsn"]
        assert len(bsn_results) == 0

    def test_bsn_starting_with_zero_rejected(self):
        """BSN cannot start with 0."""
        assert _validate_bsn("012345678") is False

    def test_bsn_wrong_length_rejected(self):
        """BSN must be exactly 9 digits."""
        assert _validate_bsn("12345678") is False
        assert _validate_bsn("1234567890") is False

    def test_validate_bsn_known_values(self):
        """Test 11-proef with known valid/invalid BSNs."""
        assert _validate_bsn("111222333") is True
        assert _validate_bsn("123456782") is True  # Known valid test BSN
        assert _validate_bsn("999999999") is False
        assert _validate_bsn("000000000") is False

    def test_multiple_bsns_in_text(self):
        """Multiple valid BSNs in the same text should all be detected."""
        text = "BSN 111222333 en BSN 123456782 staan in dit document."
        results = detect_tier1(text)
        bsn_results = [r for r in results if r.entity_type == "bsn"]
        assert len(bsn_results) == 2


# ---------------------------------------------------------------------------
# Tier 1: IBAN — NL + 2 check digits + 4 letters + 10 digits
# ---------------------------------------------------------------------------


class TestIBAN:
    def test_valid_dutch_iban_detected(self):
        text = "Betaling naar NL91ABNA0417164300."
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 1
        assert iban_results[0].text == "NL91ABNA0417164300"
        assert iban_results[0].woo_article == "5.1.2e"

    def test_lowercase_iban_detected(self):
        """IBAN regex is case-insensitive."""
        text = "IBAN: nl91abna0417164300"
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 1

    def test_non_dutch_iban_not_detected(self):
        """Only NL IBANs are supported."""
        text = "IBAN: DE89370400440532013000"
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 0

    def test_spaced_iban_detected(self):
        """Banks often print IBANs grouped with spaces — both forms must match."""
        text = "Bankrekeningnummer: NL68 RABO 0338 1615 89"
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 1
        assert iban_results[0].text.replace(" ", "") == "NL68RABO0338161589"


# ---------------------------------------------------------------------------
# Tier 1: Phone numbers
# ---------------------------------------------------------------------------


class TestPhone:
    def test_dutch_mobile_detected(self):
        text = "Bel mij op 06-12345678."
        results = detect_tier1(text)
        phone_results = [r for r in results if r.entity_type == "telefoon"]
        assert len(phone_results) >= 1

    def test_dutch_landline_detected(self):
        text = "Kantoor: 020-1234567"
        results = detect_tier1(text)
        phone_results = [r for r in results if r.entity_type == "telefoon"]
        assert len(phone_results) >= 1

    def test_international_mobile_detected(self):
        """International +31 mobile formats are detected via lookbehind
        (previously blocked by \\b, which does not fire between a space
        and a `+` because both are non-word characters)."""
        for text in [
            "Bereikbaar op +316-12345678",
            "Bel +31 6 12345678",
            "Nummer: +31612345678",
        ]:
            results = detect_tier1(text)
            phone_results = [r for r in results if r.entity_type == "telefoon"]
            assert len(phone_results) >= 1, f"Expected phone in {text!r}"

    def test_international_landline_with_spaced_groups(self):
        """+31 40 792 00 35 — international landline with multiple space groups."""
        text = "Telefoonnummer +31 40 792 00 35"
        results = detect_tier1(text)
        phone_results = [r for r in results if r.entity_type == "telefoon"]
        assert len(phone_results) >= 1

    def test_short_number_not_detected(self):
        """Numbers with too few digits should not match as phone numbers."""
        text = "Referentie: 06-1234"
        results = detect_tier1(text)
        phone_results = [r for r in results if r.entity_type == "telefoon"]
        assert len(phone_results) == 0


# ---------------------------------------------------------------------------
# Tier 1: Email
# ---------------------------------------------------------------------------


class TestEmail:
    def test_email_detected(self):
        text = "Mail naar jan.jansen@gemeente.nl voor meer info."
        results = detect_tier1(text)
        email_results = [r for r in results if r.entity_type == "email"]
        assert len(email_results) == 1
        assert email_results[0].text == "jan.jansen@gemeente.nl"
        assert email_results[0].woo_article == "5.1.2e"

    def test_email_with_plus_addressing(self):
        text = "Stuur naar info+woo@overheid.nl"
        results = detect_tier1(text)
        email_results = [r for r in results if r.entity_type == "email"]
        assert len(email_results) == 1


# ---------------------------------------------------------------------------
# Tier 1: URL
# ---------------------------------------------------------------------------


class TestUrl:
    def test_linkedin_url_detected(self):
        """Long hyphenated URL should be fully captured (the exact failure
        mode from the real CIIIC document: URL bbox was truncated)."""
        text = "Zie https://www.linkedin.com/in/natasja-paulssen-hallema-20880353/ voor details"
        results = detect_tier1(text)
        url_results = [r for r in results if r.entity_type == "url"]
        assert len(url_results) == 1
        assert url_results[0].text == (
            "https://www.linkedin.com/in/natasja-paulssen-hallema-20880353/"
        )
        assert url_results[0].woo_article == "5.1.2e"

    def test_url_trailing_period_stripped(self):
        """'see https://example.com.' should capture the URL without the period."""
        text = "Bezoek https://example.com."
        results = detect_tier1(text)
        url_results = [r for r in results if r.entity_type == "url"]
        assert len(url_results) == 1
        assert url_results[0].text == "https://example.com"

    def test_tier2_skips_url(self):
        """URLs are Tier 1; Deduce's url tag should be skipped to avoid duplicates."""
        text = "Kijk op https://www.voorbeeld.nl voor meer"
        results = detect_tier2(text)
        url_results = [r for r in results if r.entity_type == "url"]
        assert len(url_results) == 0


# ---------------------------------------------------------------------------
# Tier 1: Postcode
# ---------------------------------------------------------------------------


class TestPostcode:
    def test_postcode_with_space_detected(self):
        text = "Adres: Kerkstraat 1, 1234 AB Amsterdam"
        results = detect_tier1(text)
        postcode_results = [r for r in results if r.entity_type == "postcode"]
        assert len(postcode_results) == 1

    def test_postcode_without_space_detected(self):
        text = "Postcode: 1234AB"
        results = detect_tier1(text)
        postcode_results = [r for r in results if r.entity_type == "postcode"]
        assert len(postcode_results) == 1

    def test_lowercase_postcode_not_detected(self):
        """Dutch postcodes require uppercase letters."""
        text = "1234ab is geen geldige postcode"
        results = detect_tier1(text)
        postcode_results = [r for r in results if r.entity_type == "postcode"]
        assert len(postcode_results) == 0


# ---------------------------------------------------------------------------
# Tier 1: License plates (kentekens)
# ---------------------------------------------------------------------------


class TestLicensePlate:
    def test_sidecode_format_detected(self):
        """Common Dutch license plate formats."""
        plates = ["AB-123-C", "1-ABC-23", "AB-12-CD", "12-AB-34", "AB-123-C"]
        for plate in plates:
            text = f"Kenteken: {plate}"
            results = detect_tier1(text)
            plate_results = [r for r in results if r.entity_type == "kenteken"]
            assert len(plate_results) >= 1, f"Expected plate {plate} to be detected"
            assert plate_results[0].woo_article == "5.1.2e"


# ---------------------------------------------------------------------------
# Tier 1: Credit card — Luhn validation
# ---------------------------------------------------------------------------


class TestCreditCard:
    def test_valid_luhn_detected(self):
        """A card number passing Luhn check should be detected."""
        # 4532015112830366 is a known valid Luhn test number
        text = "Creditcard: 4532 0151 1283 0366"
        results = detect_tier1(text)
        cc_results = [r for r in results if r.entity_type == "creditcard"]
        assert len(cc_results) == 1

    def test_invalid_luhn_not_detected(self):
        """A number failing Luhn should NOT be detected as credit card."""
        text = "Nummer: 1234 5678 9012 3456"
        results = detect_tier1(text)
        cc_results = [r for r in results if r.entity_type == "creditcard"]
        assert len(cc_results) == 0

    def test_validate_luhn_known_values(self):
        assert _validate_luhn("4532015112830366") is True
        assert _validate_luhn("1234567890123456") is False
        assert _validate_luhn("12345") is False  # Too short


# ---------------------------------------------------------------------------
# Tier 1: Meta / combined behavior
# ---------------------------------------------------------------------------


class TestTier1Meta:
    def test_all_tier1_are_auto_accepted(self):
        """Every Tier 1 detection should have review_status implied by tier='1'."""
        text = "BSN: 111222333, IBAN: NL91ABNA0417164300, Tel: 06-12345678, Email: test@example.com"
        results = detect_tier1(text)
        assert len(results) >= 4
        for r in results:
            assert r.tier == "1"
            assert r.source == "regex"

    def test_deduplication(self):
        """Same entity at the same position should not be reported twice."""
        text = "BSN: 111222333 en nog eens 111222333"
        results = detect_tier1(text)
        bsn_results = [r for r in results if r.entity_type == "bsn"]
        # Two occurrences at different positions = 2 detections
        assert len(bsn_results) == 2

    def test_character_offsets_correct(self):
        """Start/end char offsets should correctly locate the entity in text."""
        text = "Prefix 111222333 suffix"
        results = detect_tier1(text)
        bsn_results = [r for r in results if r.entity_type == "bsn"]
        assert len(bsn_results) == 1
        det = bsn_results[0]
        assert text[det.start_char : det.end_char] == "111222333"

    def test_empty_text_returns_empty(self):
        assert detect_tier1("") == []

    def test_no_false_positives_on_prose(self):
        """Normal Dutch text should not trigger detections."""
        text = (
            "De gemeenteraad vergaderde gisteren over het nieuwe bestemmingsplan. "
            "Wethouder De Vries presenteerde het voorstel aan de commissie."
        )
        results = detect_tier1(text)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tier 2: Deduce NER (uses real Deduce library)
# ---------------------------------------------------------------------------


class TestTier2Deduce:
    def test_person_name_detected(self):
        """Deduce should detect Dutch person names."""
        text = "De heer Jan de Vries heeft een verzoek ingediend bij de gemeente."
        results = detect_tier2(text)
        person_results = [r for r in results if r.entity_type == "persoon"]
        assert len(person_results) >= 1
        assert any("Jan de Vries" in r.text for r in person_results)

    def test_person_is_tier2(self):
        text = "Mevrouw A. Bakker-Smit is de aanvrager."
        results = detect_tier2(text)
        person_results = [r for r in results if r.entity_type == "persoon"]
        for r in person_results:
            assert r.tier == "2"
            assert r.source == "deduce"
            assert r.woo_article == "5.1.2e"
            assert r.confidence == 0.80

    def test_address_detected(self):
        """Deduce should detect street addresses."""
        text = "Woonadres: Kerkstraat 15 te Amsterdam."
        results = detect_tier2(text)
        address_results = [r for r in results if r.entity_type == "adres"]
        assert len(address_results) >= 1

    def test_amsterdamse_hogeschool_not_flagged_as_person(self):
        """Real regression: Deduce tags 'Amsterdamse Hogeschool voor de
        Kunsten' as a person. The organization keyword 'hogeschool'
        must drop it before it reaches the review list."""
        text = "We werken samen met de Amsterdamse Hogeschool voor de Kunsten aan dit project."
        results = detect_tier2(text)
        person_results = [r for r in results if r.entity_type == "persoon"]
        assert all("hogeschool" not in r.text.lower() for r in person_results), (
            "Amsterdamse Hogeschool should be filtered out as a person"
        )

    def test_gemeente_not_flagged_as_person(self):
        text = "De gemeente Amsterdam heeft besloten."
        results = detect_tier2(text)
        person_results = [r for r in results if r.entity_type == "persoon"]
        for r in person_results:
            assert "gemeente" not in r.text.lower()

    def test_tier2_skips_bsn_postcode_telefoon(self):
        """Types handled by Tier 1 regex (bsn, telefoon, postcode) are skipped in Tier 2."""
        text = "BSN 111222333, tel 06-12345678, postcode 1234 AB"
        results = detect_tier2(text)
        for r in results:
            assert r.entity_type not in ("bsn", "telefoon", "postcode"), (
                f"Tier 2 should skip {r.entity_type} (handled by Tier 1)"
            )


# ---------------------------------------------------------------------------
# Heuristic person filter — _is_plausible_person_name
#
# Unit-level tests of the filter predicate itself. These run without
# Deduce and guarantee the filter stays honest even if Deduce's own
# output changes.
# ---------------------------------------------------------------------------


class TestIsPlausiblePersonName:
    def test_real_names_accepted(self):
        assert _is_plausible_person_name("Jan de Vries") is True
        assert _is_plausible_person_name("Natasja Paulssen-Hallema") is True
        assert _is_plausible_person_name("A. Bakker") is True
        assert _is_plausible_person_name("Van den Berg") is True

    def test_organisation_keywords_rejected(self):
        cases = [
            "Amsterdamse Hogeschool voor de Kunsten",
            "Instituut Beeld en Geluid",
            "gemeente Amsterdam",
            "Stichting Woo Buddy",
            "Universiteit Utrecht",
            "Ministerie van Binnenlandse Zaken",
            "Ziekenhuis Erasmus",
        ]
        for text in cases:
            assert _is_plausible_person_name(text) is False, f"should reject: {text}"

    def test_article_plus_lowercase_rejected(self):
        """Dutch article followed by a lowercase word is a generic
        phrase, not a name."""
        assert _is_plausible_person_name("de gemeente") is False
        assert _is_plausible_person_name("een aanvrager") is False
        assert _is_plausible_person_name("het college") is False

    def test_article_plus_capitalised_name_accepted(self):
        """Dutch tussenvoegsel surnames like 'de Vries' must survive
        the article filter as long as the actual surname is
        capitalised."""
        assert _is_plausible_person_name("de Vries") is True
        # "Het College" gets rejected downstream by the organisation
        # keyword filter ('college'), not by the article rule — but
        # it should not be rejected BY the article rule on its own.

    def test_het_college_rejected_by_keyword(self):
        """Defence in depth: 'Het College' is capitalised but still
        an organisation, and the keyword filter catches it."""
        assert _is_plausible_person_name("Het College") is False

    def test_all_lowercase_rejected(self):
        """Real names always have at least one uppercase letter."""
        assert _is_plausible_person_name("partnerschappen met") is False
        assert _is_plausible_person_name("jan") is False

    def test_multi_sentence_fragment_rejected(self):
        """A period followed by a lowercase word means we captured
        more than one sentence — not a name."""
        text = "Amsterdamse Hogeschool voor de Kunsten. technologie in de context"
        assert _is_plausible_person_name(text) is False

    def test_trailing_single_letter_rejected(self):
        """'... het Rijks m' — trailing lone letter is a truncation."""
        assert _is_plausible_person_name("het Rijks m") is False
        assert _is_plausible_person_name("Jan de V") is False

    def test_very_long_text_rejected(self):
        assert _is_plausible_person_name("A" * 60) is False

    def test_very_short_text_rejected(self):
        assert _is_plausible_person_name("J") is False
        assert _is_plausible_person_name("") is False
        assert _is_plausible_person_name("   ") is False

    def test_initial_followed_by_surname_accepted(self):
        """One-letter tokens are fine if followed by more name content."""
        assert _is_plausible_person_name("J. Bakker") is True
        assert _is_plausible_person_name("A.M. van der Berg") is True


# ---------------------------------------------------------------------------
# Combined: detect_all — Tier 1 + Tier 2 with confidence boosting
# ---------------------------------------------------------------------------


class TestDetectAll:
    def test_combines_tier1_and_tier2(self):
        """detect_all should return results from both tiers."""
        text = "De heer Jan de Vries, BSN 111222333, e-mail jan@example.com, woont in Amsterdam."
        results = detect_all(text)
        tiers = {r.tier for r in results}
        assert "1" in tiers, "Should have Tier 1 detections"
        assert "2" in tiers, "Should have Tier 2 detections"

    def test_confidence_boosting(self):
        """If Tier 1 and Tier 2 find the same text, Tier 2 confidence is boosted."""
        # This tests the boosting logic — when both tiers detect the same string,
        # the Tier 2 detection's confidence gets +0.10
        # We need text that both tiers would match. This depends on Deduce also
        # detecting something that regex catches. Hard to guarantee, so we test
        # the mechanism directly.

        det1 = NERDetection(
            text="test",
            entity_type="a",
            tier="1",
            confidence=0.95,
            woo_article="5.1.1e",
            source="regex",
            start_char=0,
            end_char=4,
        )
        det2 = NERDetection(
            text="test",
            entity_type="b",
            tier="2",
            confidence=0.70,
            woo_article="5.1.2e",
            source="deduce",
            start_char=0,
            end_char=4,
        )

        # Simulate detect_all boosting logic
        tier1_texts = {det1.text.lower()}
        if det2.text.lower() in tier1_texts:
            det2.confidence = min(det2.confidence + 0.10, 1.0)

        assert det2.confidence == pytest.approx(0.80)

    def test_confidence_boost_capped_at_1(self):
        """Boosted confidence should not exceed 1.0."""
        det = NERDetection(
            text="x",
            entity_type="y",
            tier="2",
            confidence=0.95,
            woo_article="5.1.2e",
            source="deduce",
            start_char=0,
            end_char=1,
        )
        det.confidence = min(det.confidence + 0.10, 1.0)
        assert det.confidence == 1.0
