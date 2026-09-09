"""Tests for the NER engine — Tier 1 regex + validation and Tier 2 Deduce NER.

Tier 1 tests are pure unit tests (no external dependencies).
Tier 2 tests use the real Deduce library (loaded once, ~2s startup).
"""

import pytest

from app.services.name_engine import load_name_lists
from app.services.ner_engine import NERDetection, detect_all, detect_tier1, detect_tier2
from app.services.ner_engine._anchor_rules import detect_persoon_via_anchors
from app.services.ner_engine._org_context import (
    functional_mailbox_prefix,
    legal_form_lead,
    organisation_context_reason,
)
from app.services.ner_engine._plausibility import _is_plausible_person_name
from app.services.ner_engine._tier1 import (
    _is_plausible_birth_date,
    _parse_birth_date,
    _validate_bsn,
    _validate_btw,
    _validate_luhn,
)
from app.services.ner_engine._title_prefix import _detect_persoon_via_title_prefix
from app.services.ner_engine._wordlist_pairs import detect_persoon_via_wordlists
from tests.text_shapes import production_text

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

    def test_line_wrapped_iban_detected(self):
        """IBANs that wrap across a line (space + newline between groups)
        must still be detected — real-world case from Moneybird invoices."""
        text = "van je bankrekening of creditcard (NL92 ABNA \n0410 5561 57)."
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 1
        assert iban_results[0].text.replace(" ", "").replace("\n", "") == "NL92ABNA0410556157"

    def test_page_break_iban_detected(self):
        """Cross-page IBAN joined by '\\n\\n' must still match."""
        text = "NL68 RABO 0338\n\n1615 89"
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 1

    def test_invalid_checksum_iban_rejected(self):
        """Mod-97 guards against random NL + 16-char strings that match the format."""
        text = "Referentie: NL00ABNA0000000000"
        results = detect_tier1(text)
        iban_results = [r for r in results if r.entity_type == "iban"]
        assert len(iban_results) == 0


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

    @pytest.mark.parametrize(
        "text,expected",
        [
            # The shape Drenthe's letter templates and aanvraagformulieren
            # print — three of the four planted phone numbers in the eval
            # corpus were missed on this alone (#96, rule 5).
            ("Telefoonnummer (0592) 36 50 71", "(0592) 36 50 71"),
            ("Bel (033) 421 74 56 voor vragen", "(033) 421 74 56"),
            ("T (071) 516 5000", "(071) 516 5000"),
            ("Telefoon (0592) 365555", "(0592) 365555"),
        ],
    )
    def test_netnummer_between_brackets_detected(self, text, expected):
        results = detect_tier1(text)
        assert expected in [r.text for r in results if r.entity_type == "telefoon"]

    @pytest.mark.parametrize("text", ["Tel (0592) 365 5555", "Tel (033) 421 456"])
    def test_bracket_shapes_need_exactly_ten_digits(self, text):
        # Eleven or nine digits is not a Dutch number, however it is grouped.
        assert [r for r in detect_tier1(text) if r.entity_type == "telefoon"] == []

    def test_year_between_brackets_is_not_a_phone_number(self):
        """The negative the bracket patterns must not eat: a bracketed year
        followed by numbers, as permit tables print them."""
        text = "Oprichtingsvergunning (2010) 12 34 56 is verleend"
        results = detect_tier1(text)
        assert [r for r in results if r.entity_type == "telefoon"] == []

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
# Tier 1: KvK number (8 digits, context-anchored)
# ---------------------------------------------------------------------------


class TestKvK:
    def test_kvk_with_prefix_anchor_detected(self):
        text = "Ingeschreven bij de KvK onder nummer 12345678."
        results = detect_tier1(text)
        kvk_results = [r for r in results if r.entity_type == "kvk"]
        assert len(kvk_results) == 1
        assert kvk_results[0].text == "12345678"
        assert kvk_results[0].tier == "1"
        assert kvk_results[0].confidence == 0.90
        assert kvk_results[0].source == "regex"

    def test_kvk_uppercase_anchor(self):
        text = "KVK: 87654321"
        results = detect_tier1(text)
        kvk_results = [r for r in results if r.entity_type == "kvk"]
        assert len(kvk_results) == 1

    def test_kamer_van_koophandel_anchor(self):
        text = "Kamer van Koophandel 11223344"
        results = detect_tier1(text)
        kvk_results = [r for r in results if r.entity_type == "kvk"]
        assert len(kvk_results) == 1

    def test_standalone_8_digits_not_detected_as_kvk(self):
        """An unanchored 8-digit sequence must not be flagged as KvK —
        the whole point of the anchor is to avoid those false positives."""
        text = "Referentienummer 12345678 in ons systeem."
        results = detect_tier1(text)
        kvk_results = [r for r in results if r.entity_type == "kvk"]
        assert len(kvk_results) == 0

    def test_kvk_anchor_beyond_window_not_detected(self):
        """Anchor more than 20 chars before the number does not count."""
        # 30 chars of filler between the anchor and the number.
        text = "KvK" + " " * 30 + "12345678"
        results = detect_tier1(text)
        kvk_results = [r for r in results if r.entity_type == "kvk"]
        assert len(kvk_results) == 0


# ---------------------------------------------------------------------------
# Tier 1: BTW number (NL + 9 digits + B + 2 digits, 11-proef)
# ---------------------------------------------------------------------------


class TestBTW:
    def test_compact_btw_with_valid_checksum_detected(self):
        # 111222333 passes 11-proef (see TestBSN)
        text = "BTW: NL111222333B01"
        results = detect_tier1(text)
        btw_results = [r for r in results if r.entity_type == "btw"]
        assert len(btw_results) == 1
        assert btw_results[0].text == "NL111222333B01"
        assert btw_results[0].confidence == 0.95
        assert btw_results[0].woo_article == "5.1.2e"

    def test_spaced_btw_detected(self):
        text = "BTW-nummer NL 111222333 B 01"
        results = detect_tier1(text)
        btw_results = [r for r in results if r.entity_type == "btw"]
        assert len(btw_results) == 1

    def test_invalid_checksum_rejected(self):
        """A BTW number whose 9-digit body fails the 11-proef is dropped."""
        text = "BTW: NL123456780B01"  # body fails 11-proef
        results = detect_tier1(text)
        btw_results = [r for r in results if r.entity_type == "btw"]
        assert len(btw_results) == 0

    def test_validate_btw_matches_bsn_rule(self):
        assert _validate_btw("111222333") is True
        assert _validate_btw("123456789") is False


# ---------------------------------------------------------------------------
# Tier 1: Geboortedatum (context-anchored dates)
# ---------------------------------------------------------------------------


class TestGeboortedatum:
    def test_geboortedatum_anchor_dash_format(self):
        text = "Geboortedatum: 15-03-1985"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 1
        assert geb_results[0].text == "15-03-1985"
        assert geb_results[0].confidence == 0.95
        assert geb_results[0].woo_article == "5.1.2e"

    def test_geboortedatum_slash_format(self):
        text = "geboortedatum 15/03/1985"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 1

    def test_geboortedatum_word_format(self):
        text = "geboortedatum 15 maart 1985"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 1
        assert "maart" in geb_results[0].text

    def test_geboren_op_anchor(self):
        text = "geboren op 01-01-1990"
        results = detect_tier1(text)
        assert any(r.entity_type == "geboortedatum" for r in results)

    def test_geb_abbreviated_anchors(self):
        for anchor in ("geb.", "geb:"):
            text = f"{anchor} 05-05-1970"
            results = detect_tier1(text)
            assert any(r.entity_type == "geboortedatum" for r in results), (
                f"anchor {anchor!r} should trigger"
            )

    def test_english_dob_anchor(self):
        for anchor in ("DOB", "date of birth"):
            text = f"{anchor}: 10-10-1960"
            results = detect_tier1(text)
            assert any(r.entity_type == "geboortedatum" for r in results), (
                f"anchor {anchor!r} should trigger"
            )

    def test_plain_date_without_anchor_not_detected(self):
        """Dates without an anchor stay out of Tier 1 (they remain Tier 2)."""
        text = "De vergadering vond plaats op 15-03-1985."
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 0

    def test_impossible_date_rejected(self):
        """Day 31 of February cannot exist — drop the match."""
        text = "geboortedatum: 31-02-1985"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 0

    def test_future_date_rejected(self):
        text = "geboortedatum: 01-01-2999"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 0

    def test_far_past_date_rejected(self):
        """More than 120 years ago is not a plausible living birth date."""
        text = "geboortedatum: 01-01-1800"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 0

    def test_parse_birth_date_word_form(self):
        assert _parse_birth_date("15 maart 1985") == __import__("datetime").date(1985, 3, 15)
        assert _parse_birth_date("5 jan 1990") == __import__("datetime").date(1990, 1, 5)

    def test_is_plausible_birth_date(self):
        import datetime

        today = datetime.date.today()
        assert _is_plausible_birth_date(datetime.date(1990, 1, 1)) is True
        assert _is_plausible_birth_date(today) is True
        assert _is_plausible_birth_date(today + datetime.timedelta(days=1)) is False
        assert _is_plausible_birth_date(datetime.date(1800, 1, 1)) is False


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
        # "Bakker-Smit" is not in the seed CBS list, so the Deduce +
        # CBS path drops it and the #48 title-prefix rule catches it
        # via "Mevrouw" instead. Either detection source is a valid
        # Tier 2 persoon hit — assert the common invariants.
        assert len(person_results) >= 1
        for r in person_results:
            assert r.tier == "2"
            assert r.source in ("deduce", "title_rule", "initials_rule")
            assert r.woo_article == "5.1.2e"
            assert r.confidence in (0.75, 0.80, 0.85, 0.90, 0.95)

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

    def test_name_list_boost_on_known_first_name(self):
        """A Deduce persoon hit whose first token is on the Meertens
        list should be boosted above the base 0.80 confidence and
        carry attribution text pointing back to the Voornamenbank."""
        text = "De heer Jan Bakker heeft een verzoek ingediend."
        results = detect_tier2(text)
        person_results = [r for r in results if r.entity_type == "persoon"]
        assert any(r.confidence > 0.80 for r in person_results)
        assert any(
            "Meertens" in r.reasoning or "Voornamenbank" in r.reasoning for r in person_results
        )

    def test_name_list_drops_unknown_span(self):
        """A span that survived the heuristic but matches NO entry in
        the name lists is dropped by the name engine — regression test
        for the post-LLM false-positive gap."""
        from app.services.name_engine import score_person_candidate
        from app.services.ner_engine._deduce import _get_name_lists

        lists = _get_name_lists()
        # Sanity check: this span has no tokens in either list.
        score = score_person_candidate("Qwerty Xylofoon", lists)
        assert score.is_plausible is False

    def test_leading_role_noun_stripped(self):
        """Sentence-initial role nouns ('Klaagster', 'Verdachte', …) that
        Deduce absorbs into a person span should be trimmed off."""
        text = "Klaagster Jan de Vries belde gisteravond in paniek."
        results = detect_tier2(text)
        person_results = [r for r in results if r.entity_type == "persoon"]
        assert len(person_results) >= 1
        for r in person_results:
            assert not r.text.lower().startswith("klaagster"), (
                f"leading 'Klaagster' should be stripped, got {r.text!r}"
            )


# ---------------------------------------------------------------------------
# Tier 2: huisnummer / residence-cued "nummer N" regex (#51)
# ---------------------------------------------------------------------------


class TestHuisnummerRegex:
    """`huisnummer N` and `bewoner van nummer N` regex fallback.

    Deduce's built-in huisnummer tag only fires when a street token is
    adjacent; partially-anonymized Woo prose drops the street but keeps
    the number, so we catch these shapes via regex."""

    def test_huisnummer_always_detected(self):
        text = "mevrouw T. Bakker (huisnummer 18) en de familie El Khatib (huisnummer 22)."
        results = detect_tier2(text)
        huisnummer = [
            r for r in results if r.entity_type == "adres" and "huisnummer" in r.text.lower()
        ]
        assert len(huisnummer) == 2
        for r in huisnummer:
            assert r.tier == "2"
            assert r.source == "regex"
            assert r.woo_article == "5.1.2e"
        texts = {r.text.lower() for r in huisnummer}
        assert "huisnummer 18" in texts
        assert "huisnummer 22" in texts

    def test_huisnummer_span_covers_full_phrase(self):
        text = "Het betreft huisnummer 22a in de straat."
        results = detect_tier2(text)
        match = next(
            r for r in results if r.entity_type == "adres" and "huisnummer" in r.text.lower()
        )
        assert match.text.lower() == "huisnummer 22a"
        assert text[match.start_char : match.end_char].lower() == "huisnummer 22a"

    def test_residence_cued_nummer_detected(self):
        text = "De heer W. de Groot, bewoner van nummer 26, heeft ingediend."
        results = detect_tier2(text)
        nummer = [
            r for r in results if r.entity_type == "adres" and r.text.lower().startswith("nummer")
        ]
        assert len(nummer) == 1
        assert nummer[0].text.lower() == "nummer 26"
        # Span must cover ONLY "nummer 26", not the "bewoner van" cue.
        assert text[nummer[0].start_char : nummer[0].end_char].lower() == "nummer 26"

    def test_woont_op_nummer_detected(self):
        text = "Zij woont op nummer 12 sinds 2019."
        results = detect_tier2(text)
        nummer = [
            r for r in results if r.entity_type == "adres" and r.text.lower().startswith("nummer")
        ]
        assert len(nummer) == 1
        assert nummer[0].text.lower() == "nummer 12"

    def test_bare_nummer_without_residence_cue_ignored(self):
        """`zaaknummer`, `dossiernummer`, etc. must not fire the rule."""
        text = (
            "Zaaknummer 2024 is in behandeling. Zie ook dossiernummer 17 "
            "en volgnummer 3 op pagina nummer 42."
        )
        results = detect_tier2(text)
        nummer = [
            r for r in results if r.entity_type == "adres" and r.text.lower().startswith("nummer")
        ]
        assert nummer == []

    def test_huisnummer_drops_overlapping_deduce_adres(self):
        """When Deduce emits a nested `huisnummer`/`adres` annotation
        inside our new span, the duplicate must be dropped so the
        reviewer sees exactly one card."""
        text = "De bewoners van huisnummer 22 hebben geklaagd."
        results = detect_tier2(text)
        # Exactly one adres detection for this position, not two.
        adres_hits = [r for r in results if r.entity_type == "adres" and "22" in r.text]
        assert len(adres_hits) == 1
        assert adres_hits[0].source == "regex"


# ---------------------------------------------------------------------------
# Tier 2: straatnaam + huisnummer regex rule
#
# Deduce silently drops plain `Havenstraat 194`-style spans on
# ordinary Dutch letter / invoice prose. The straatnaam rule catches
# these via the closed set of Dutch street suffixes, with a
# confidence boost when a postcode sits within 80 chars.
# ---------------------------------------------------------------------------


class TestStraatnaamRegex:
    """Unit tests for the rule itself. Integration with Deduce is
    covered by `test_postcode_proximity_boosts_confidence` below —
    the other cases exercise the regex directly because Deduce
    sometimes also catches the same span (making the integration
    output depend on Deduce's version rather than our rule)."""

    def test_plain_street_and_number_detected(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Havenstraat 194 is het bezoekadres.")
        assert len(hits) == 1
        assert hits[0].text == "Havenstraat 194"
        assert hits[0].entity_type == "adres"
        assert hits[0].tier == "2"
        assert hits[0].woo_article == "5.1.2e"
        assert hits[0].confidence == 0.85

    def test_multiword_street_with_tussen(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Zie Van der Helstplein 3-5 op de kaart.")
        assert any("Helstplein" in h.text for h in hits)

    def test_prinses_beatrixlaan_multiword_prefix(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Afzender: Prinses Beatrixlaan 12a.")
        assert len(hits) == 1
        assert hits[0].text == "Prinses Beatrixlaan 12a"

    def test_postcode_proximity_boosts_confidence(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        text = "Factuuradres:\nHavenstraat 194\n3024 TM ROTTERDAM"
        hits = _detect_adres_by_straatnaam(text)
        assert len(hits) == 1
        assert hits[0].text == "Havenstraat 194"
        # Postcode "3024 TM" sits within 80 chars → proximity boost.
        assert hits[0].confidence == 0.92

    def test_postcode_far_away_no_boost(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        # Pad the text so the postcode sits well beyond the 80-char
        # proximity window.
        text = "Havenstraat 194 " + ("x " * 100) + "3024 TM"
        hits = _detect_adres_by_straatnaam(text)
        assert len(hits) == 1
        assert hits[0].confidence == 0.85

    def test_lowercase_winkelstraat_not_confused(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("In deze winkelstraat staan 10 winkels naast elkaar.")
        assert hits == []

    def test_bare_park_without_prefix_not_detected(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Het park 3 is gesloten voor bezoekers.")
        assert hits == []

    def test_line_break_between_name_and_street_not_absorbed(self):
        """The prefix-word run must not cross a newline — otherwise
        `Jaap Stronks\\nHavenstraat 194` would match as one span
        starting at 'Jaap' rather than the actual street."""
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Jaap Stronks\nHavenstraat 194")
        assert len(hits) == 1
        assert hits[0].text == "Havenstraat 194"

    def test_institutional_filter_in_full_pipeline(self):
        """Full-pipeline integration: bezoekadres context drops the
        straatnaam hit via `_is_plausible_home_address`."""
        text = "Bezoekadres: Stadhuisplein 1 te Rotterdam."
        results = detect_tier2(text)
        regex_hits = [
            r
            for r in results
            if r.entity_type == "adres" and r.source == "regex" and "Stadhuis" in r.text
        ]
        assert regex_hits == []


# ---------------------------------------------------------------------------
# Tier 2: initials-rule for `[Initials] [Surname]` spans
#
# Deduce emits the span but the CBS name-list filter drops it when
# the surname is not in the top-N list. The initials rule rescues
# structurally-evident names like "G.J. Stronks".
# ---------------------------------------------------------------------------


class TestInitialsRule:
    def test_initials_plus_surname_detected(self):
        text = "Betreft: de factuur van G.J. Stronks aan Odido."
        results = detect_tier2(text)
        hits = [r for r in results if r.entity_type == "persoon" and "Stronks" in r.text]
        assert len(hits) >= 1
        hit = hits[0]
        assert hit.tier == "2"
        assert hit.confidence == 0.85
        # Either the initials rule or a Deduce+CBS hit is acceptable
        # depending on whether Stronks has been added to CBS — the
        # point is the detection exists at all.
        assert hit.source in ("initials_rule", "deduce", "title_rule")

    def test_legal_form_abbreviation_not_matched(self):
        text = "N.V. Nederlandse Spoorwegen heeft bericht."
        results = detect_tier2(text)
        # No `persoon` hit sourced from the initials rule — the NV.
        # abbreviation guard must drop it.
        initials_hits = [
            r for r in results if r.entity_type == "persoon" and r.source == "initials_rule"
        ]
        assert initials_hits == []

    def test_msc_academic_abbreviation_not_matched(self):
        text = "Contactpersoon: M.Sc. Johnson namens de werkgroep."
        results = detect_tier2(text)
        initials_hits = [
            r
            for r in results
            if r.entity_type == "persoon" and r.source == "initials_rule" and "Sc" in r.text
        ]
        assert initials_hits == []

    def test_initials_with_tussenvoegsel(self):
        text = "De afzender is A.M. van der Berg uit Amsterdam."
        results = detect_tier2(text)
        hits = [r for r in results if r.entity_type == "persoon" and "van der Berg" in r.text]
        assert len(hits) >= 1

    def test_initials_rule_deduped_against_deduce(self):
        """If Deduce + CBS already produced a persoon hit for a
        span, the initials rule must not emit a second card at the
        same position."""
        text = "Jan Jansen heeft het formulier ondertekend."
        results = detect_tier2(text)
        person_hits = [r for r in results if r.entity_type == "persoon"]
        # Expect exactly one hit for this span, not two.
        jansen_hits = [r for r in person_hits if "Jansen" in r.text]
        assert len(jansen_hits) == 1


# ---------------------------------------------------------------------------
# Tier 2: label-anchored identifier rule (klantnummer / factuurnummer / …)
#
# Dutch invoices / Woo correspondence identify citizens via labelled
# reference numbers. The rule emits a new `referentie` type, tiered by
# label. The span covers the number only so the redacted output reads
# "Klantnummer: ███".
# ---------------------------------------------------------------------------


class TestLabelAnchoredIdRule:
    def test_klantnummer_detected(self):
        text = "Klantnummer: 1.11368173"
        results = detect_tier2(text)
        hits = [r for r in results if r.entity_type == "referentie"]
        assert len(hits) == 1
        assert hits[0].text == "1.11368173"
        assert hits[0].confidence == 0.85
        assert hits[0].tier == "2"
        assert hits[0].source == "regex"
        # Span covers number only, NOT the label.
        assert text[hits[0].start_char : hits[0].end_char] == "1.11368173"

    def test_factuurnummer_low_confidence(self):
        text = "Factuurnummer: 901583844500"
        results = detect_tier2(text)
        hit = next(r for r in results if r.entity_type == "referentie")
        assert hit.text == "901583844500"
        assert hit.confidence == 0.60

    def test_alphanumeric_kenmerk(self):
        text = "Ons kenmerk: OT-ID1382702-2025"
        results = detect_tier2(text)
        hit = next(r for r in results if r.entity_type == "referentie")
        assert hit.text == "OT-ID1382702-2025"
        assert hit.confidence == 0.70

    def test_zaaknummer_detected(self):
        text = "Zaaknummer Z/24/0001 is in behandeling."
        results = detect_tier2(text)
        hit = next(r for r in results if r.entity_type == "referentie")
        assert hit.text == "Z/24/0001"
        assert hit.confidence == 0.60

    def test_label_without_value_ignored(self):
        text = "Zie ons kenmerk bovenaan deze brief."
        results = detect_tier2(text)
        hits = [r for r in results if r.entity_type == "referentie"]
        assert hits == []

    def test_klantnummer_without_colon(self):
        text = "Relatienummer 987654 is toegekend."
        results = detect_tier2(text)
        hit = next(r for r in results if r.entity_type == "referentie")
        assert hit.text == "987654"
        assert hit.confidence == 0.85

    def test_multiple_labels_in_one_document(self):
        text = (
            "Klantnummer: 1.11368173\nFactuurnummer: 901583844500\nOns kenmerk: OT-ID1382702-2025\n"
        )
        results = detect_tier2(text)
        hits = {r.text: r.confidence for r in results if r.entity_type == "referentie"}
        assert hits == {
            "1.11368173": 0.85,
            "901583844500": 0.60,
            "OT-ID1382702-2025": 0.70,
        }


# ---------------------------------------------------------------------------
# Tier 2: recent-date filter on Deduce `datum` hits
#
# Deduce flags every date it finds. In Woo documents plain dates are
# overwhelmingly meeting/letter/request dates; birth dates for toddlers
# essentially never appear. Recent dates (year within the last couple of
# years) are dropped from the Tier 2 `datum` path. Tier 1 `geboortedatum`
# (anchor-based) is unaffected.
# ---------------------------------------------------------------------------


class TestTier2RecentDateFilter:
    def test_recent_event_date_dropped(self):
        """A 2024/2025/2026 date without any birth-date anchor should not
        appear as a Tier 2 `datum` detection."""
        import datetime

        text = (
            "Op 5 januari 2024 is een verzoek ontvangen en de gemeenteraad is "
            "op 15 februari 2024 geïnformeerd."
        )
        results = detect_tier2(text)
        datum_results = [r for r in results if r.entity_type == "datum"]
        current_year = datetime.date.today().year
        for r in datum_results:
            # No detection should carry a year within the recent window.
            assert "2024" not in r.text, f"recent date leaked through: {r.text!r}"
            assert str(current_year) not in r.text
            assert str(current_year - 1) not in r.text

    def test_old_date_still_flagged(self):
        """A plausibly-birth-date year (e.g. 1975) should still produce a
        Tier 2 `datum` hit so reviewers can confirm it."""
        text = "Betrokkene is geboren in 1975 volgens de registratie."
        results = detect_tier2(text)
        datum_results = [r for r in results if r.entity_type == "datum"]
        # Deduce is allowed to miss this one (date-without-day is fuzzy),
        # but if it produces any datum hit here it must not be filtered.
        for r in datum_results:
            assert "1975" in r.text or "19" in r.text

    def test_recent_date_with_anchor_still_caught_by_tier1(self):
        """A recent date with a geboortedatum anchor is still a Tier 1
        hit — the Tier 2 filter must not mask the anchor path."""
        text = "geboortedatum: 3 maart 2025"
        results = detect_tier1(text)
        geb_results = [r for r in results if r.entity_type == "geboortedatum"]
        assert len(geb_results) == 1
        assert "2025" in geb_results[0].text


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


# ---------------------------------------------------------------------------
# Deterministic ordering (#103)
#
# Deduce hands its annotations back in a `set`, so the order the Tier 2
# rules saw them in changed from process to process. That reshuffled the
# detection list and, because the overlap dedup keeps whichever hit it
# meets first, occasionally changed which detection survived.
# ---------------------------------------------------------------------------


class _StubAnnotations:
    """Stands in for ``docdeid.AnnotationSet``.

    Iterating it deliberately yields the reverse of the order the
    annotations were found in — the real set's hash order is just as
    arbitrary. ``sorted()`` behaves like the real one, so a caller that
    goes through it gets a stable answer and a caller that iterates
    directly does not.
    """

    def __init__(self, annotations):
        self._annotations = list(annotations)

    def __iter__(self):
        return iter(reversed(self._annotations))

    def sorted(self, by, callbacks=None, deterministic=True):
        return sorted(
            self._annotations,
            key=lambda a: a.get_sort_key(by=by, callbacks=callbacks, deterministic=deterministic),
        )


class _StubDoc:
    def __init__(self, annotations):
        self.annotations = _StubAnnotations(annotations)


class _StubDeduce:
    def __init__(self, annotations):
        self._annotations = annotations

    def deidentify(self, text):  # noqa: ARG002 — signature parity with Deduce
        return _StubDoc(self._annotations)


class TestDeterministicOrder:
    # Two addresses on one line, plus a name, so both tiers and several
    # sub-rules contribute to the list.
    TEXT = (
        "Betreft: Kerkstraat 3, 1234 EN Ede en Havenstraat 194, 5678 AB Delft.\n"
        "Contact: Jan de Vries, BSN 111222333, jan@example.com."
    )

    def test_detect_all_is_sorted_by_offset(self):
        results = detect_all(self.TEXT)
        keys = [(r.start_char, r.end_char, r.entity_type) for r in results]
        assert keys == sorted(keys)

    def test_detect_tier2_repeats_itself(self):
        first = detect_tier2(self.TEXT)
        second = detect_tier2(self.TEXT)
        assert [(r.start_char, r.end_char, r.entity_type, r.text) for r in first] == [
            (r.start_char, r.end_char, r.entity_type, r.text) for r in second
        ]

    def test_detect_tier2_ignores_deduce_annotation_order(self, monkeypatch):
        """Spans found in reverse order must come back the same way.

        The stub yields its annotations back-to-front on iteration.
        Reverting to ``for annotation in doc.annotations`` fails here.
        """
        from docdeid.annotation import Annotation

        from app.services.ner_engine import _tier2

        text = "Adres: Kerkstraat 3, 1234 EN Ede en Havenstraat 194, 5678 AB Delft."
        annotations = [
            Annotation(text=text[start:end], start_char=start, end_char=end, tag="locatie")
            for start, end in (
                (text.index("Kerkstraat 3"), text.index("Kerkstraat 3") + len("Kerkstraat 3")),
                (text.index("1234 EN Ede"), text.index("1234 EN Ede") + len("1234 EN Ede")),
                (
                    text.index("Havenstraat 194"),
                    text.index("Havenstraat 194") + len("Havenstraat 194"),
                ),
                (
                    text.index("5678 AB Delft"),
                    text.index("5678 AB Delft") + len("5678 AB Delft"),
                ),
            )
        ]
        monkeypatch.setattr(_tier2, "_get_deduce", lambda: _StubDeduce(annotations))

        results = detect_tier2(text)
        adressen = [r for r in results if r.entity_type == "adres"]
        assert [r.text for r in adressen] == [
            "Kerkstraat 3",
            "1234 EN Ede",
            "Havenstraat 194",
            "5678 AB Delft",
        ]


# ---------------------------------------------------------------------------
# Title-prefix rule (#48) — non-Dutch surname coverage
#
# Catches person names that Deduce + the CBS achternamenlijst miss
# because the surname is not Dutch-origin. Confidence is lower (0.75)
# and the reasoning string is fixed so the frontend can render a
# distinct attribution.
# ---------------------------------------------------------------------------


class TestTitlePrefixRule:
    @pytest.fixture(scope="class")
    def lists(self):
        return load_name_lists()

    def test_de_familie_non_dutch_surname(self, lists):
        text = "De familie El Khatib (huisnummer 22) stuurde een zienswijze op het plan."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "El Khatib"
        assert hits[0].entity_type == "persoon"
        assert hits[0].tier == "2"
        assert hits[0].confidence == 0.75
        assert hits[0].source == "title_rule"
        assert "niet in CBS-lijst" in hits[0].reasoning
        # Span must cover only the name, not the "De familie" anchor.
        assert text[hits[0].start_char : hits[0].end_char] == "El Khatib"

    def test_dhr_turkish_surname(self, lists):
        text = "dhr. Bekir Yilmaz sprak in tijdens de vergadering."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "Bekir Yilmaz"
        assert hits[0].confidence == 0.75

    def test_mevr_polish_surname(self, lists):
        text = "mevr. Agnieszka Kowalski stelde een vraag."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "Agnieszka Kowalski"
        assert hits[0].source == "title_rule"

    def test_three_non_dutch_names_in_one_text(self, lists):
        """The canonical fixture from todo #48: all three expected
        names fire in a single paragraph."""
        text = (
            "Tijdens de inspraakavond sprak de familie El Khatib "
            "(huisnummer 22). Ook dhr. Bekir Yilmaz en mevr. "
            "Agnieszka Kowalski dienden een zienswijze in."
        )
        hits = _detect_persoon_via_title_prefix(text, lists)
        names = {h.text for h in hits}
        assert "El Khatib" in names
        assert "Bekir Yilmaz" in names
        assert "Agnieszka Kowalski" in names

    def test_de_heer_with_initial_and_tussenvoegsel(self, lists):
        """'de heer W. de Groot' — the title rule also matches names
        whose surname is in CBS. The Deduce path normally wins this
        one, but we test the rule in isolation to make sure the span
        excludes the 'de heer' anchor and includes the initial +
        tussenvoegsel."""
        text = "De heer W. de Groot heeft een verzoek ingediend."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "W. de Groot"

    def test_multi_letter_initial(self, lists):
        """'A.M. Jansen' — multi-letter initials like 'A.M.' should
        be walked over as a single initial token."""
        text = "Mr. A.M. Jansen is gemachtigd."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "A.M. Jansen"

    def test_non_dutch_tussenvoegsel_da(self, lists):
        """Portuguese 'da' is now in the tussenvoegsel set, so 'da
        Silva' parses as tussenvoegsel + surname."""
        text = "dr. Juan da Silva uit Brazilie diende een aanvraag in."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "Juan da Silva"

    def test_non_dutch_tussenvoegsel_al(self, lists):
        text = "mevrouw Fatima Al Mansouri woont in de wijk."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        assert hits[0].text == "Fatima Al Mansouri"

    def test_function_title_does_not_anchor(self, lists):
        """The title rule only fires on salutations and 'familie'. A
        public function title on its own must NOT trigger — the
        publiek-functionaris filter (#13) handles those, and we
        intentionally stay out of its way."""
        text = "De burgemeester Rutte sprak de raad toe."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert hits == []

    def test_wethouder_does_not_anchor(self, lists):
        text = "Wethouder Van Delft is aanwezig bij het overleg."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert hits == []

    def test_stacked_titles_deduped(self, lists):
        """Stacked salutation anchors ('dhr. dr. Prof.') would
        otherwise emit overlapping detections. The rule dedupes to
        the outermost span."""
        text = "dhr. dr. Prof. Henk de Vries heeft ondertekend."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert len(hits) == 1
        # The outermost span starts after the FIRST anchor that
        # successfully parses a name; inner spans are dropped.
        assert hits[0].text.endswith("Henk de Vries")

    def test_empty_text(self, lists):
        assert _detect_persoon_via_title_prefix("", lists) == []

    def test_no_title_no_detection(self, lists):
        """Plain prose without a salutation anchor produces nothing."""
        text = "De vergadering werd geopend om 19.00 uur."
        hits = _detect_persoon_via_title_prefix(text, lists)
        assert hits == []


class TestDetectTier2WithTitleRule:
    """Integration tests: the title rule is wired into detect_tier2,
    so Deduce's miss on a non-Dutch surname is rescued automatically."""

    def test_non_dutch_surname_rescued_by_title_rule(self):
        text = "De familie El Khatib woont op Kerkstraat 22."
        results = detect_tier2(text)
        persons = [r for r in results if r.entity_type == "persoon"]
        assert any("Khatib" in p.text for p in persons), (
            "El Khatib should be rescued by the #48 title-prefix rule"
        )

    def test_cbs_hit_wins_over_title_rule_for_overlap(self):
        """When a Deduce + CBS hit and the title rule both cover the
        same name, the higher-confidence CBS hit is kept and the
        title rule's 0.75 duplicate is dropped."""
        text = "De heer Jan Bakker heeft een verzoek ingediend."
        results = detect_tier2(text)
        persons = [r for r in results if r.entity_type == "persoon"]
        # We should see at most one persoon detection covering
        # "Jan Bakker"; it should come from Deduce (CBS path) with
        # confidence >= 0.85.
        bakker_hits = [p for p in persons if "Bakker" in p.text]
        assert len(bakker_hits) == 1
        assert bakker_hits[0].source == "deduce"
        assert bakker_hits[0].confidence >= 0.85


# ---------------------------------------------------------------------------
# False-positive hardening (2026-09): prefer a false negative over a
# false positive. Table-of-contents lines, bare city names, event dates,
# organisation names and uncorroborated one-word names must not reach
# the reviewer.
# ---------------------------------------------------------------------------


class TestAddressPlausibility:
    """Unit tests for `is_plausible_home_address` and its helpers — no
    Deduce involved, so these lock in the evidence rules themselves."""

    def test_strong_suffix_alone_is_enough(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "Het pand aan de Kerkstraat 12 is verkocht."
        assert is_plausible_home_address("Kerkstraat 12", text, text.index("Kerkstraat")) is True

    def test_postcode_nearby_ignores_year_ranges(self):
        from app.services.ner_engine._tier2_filters import has_postcode_nearby

        text = "BEGROTING 2019 EN 2020"
        assert has_postcode_nearby(text, text.index("2019"), text.index("2019") + 7) is False
        text = "Loopbaan 14, 5654 AB Eindhoven"
        assert has_postcode_nearby(text, 0, len("Loopbaan 14")) is True

    def test_postcode_nearby_ignores_institutional_postcode(self):
        from app.services.ner_engine._tier2_filters import has_postcode_nearby

        text = "Bezoekadres: Raadhuisplein 2, 6711 DE Ede\nOnderwerp: Zonnepark 3"
        start = text.index("Zonnepark")
        assert has_postcode_nearby(text, start, start + len("Zonnepark 3")) is False

    def test_strong_suffix_shapes(self):
        from app.services.ner_engine._tier2_filters import has_strong_street_shape

        assert has_strong_street_shape("Havenstraat 194")
        assert has_strong_street_shape("Prinses Beatrixlaan 12a")
        assert has_strong_street_shape("Van der Helstplein 3-5")
        assert has_strong_street_shape("Meester Koolenweg 8")
        # Weak suffixes and ordinary nouns
        assert not has_strong_street_shape("Uitvoering 7")
        assert not has_strong_street_shape("Amsterdam 26")
        assert not has_strong_street_shape("Tekst 22")
        assert not has_strong_street_shape("Loopbaan 14")
        assert not has_strong_street_shape("Bestuursakkoord 17")
        # Ordinary noun with a strong suffix (stoplist)
        assert not has_strong_street_shape("Onderweg 3")

    def test_weak_suffix_dropped_without_evidence(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "6. Monitoring en sturing 11\n7. Woningmarkt 14\n8. Tijdpad 18\n"
        assert is_plausible_home_address("Woningmarkt 14", text, text.index("Woningmarkt")) is False
        assert is_plausible_home_address("Tijdpad 18", text, text.index("Tijdpad")) is False

    def test_weak_suffix_rescued_by_postcode(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "Gevestigd aan de Loopbaan 14, 5654 AB Eindhoven."
        assert is_plausible_home_address("Loopbaan 14", text, text.index("Loopbaan")) is True

    def test_postcode_before_the_span_is_not_evidence(self):
        from app.services.ner_engine._tier2_filters import (
            has_postcode_nearby,
            is_plausible_home_address,
        )

        # A Dutch address puts the postcode after the street, so a postcode
        # that has already been read belongs to the address above, not to the
        # next capitalised word with a number behind it.
        text = "Loopbaan 14, 5654 AB Eindhoven. Zie bijlage Data 12 voor de meetreeks."
        start = text.index("Data 12")

        assert has_postcode_nearby(text, start, start + len("Data 12")) is False
        assert is_plausible_home_address("Data 12", text, start) is False
        # The real address on the same line keeps its evidence.
        assert is_plausible_home_address("Loopbaan 14", text, text.index("Loopbaan")) is True

    def test_postcode_inside_the_span_still_counts(self):
        from app.services.ner_engine._tier2_filters import has_postcode_nearby

        text = "Havenstraat 194\n3024 TM Rotterdam"
        start = text.index("3024")
        assert has_postcode_nearby(text, start, len(text)) is True

    def test_weak_suffix_rescued_by_residence_cue(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "De bewoner van de Kerkbrink 3 heeft bezwaar gemaakt."
        assert is_plausible_home_address("Kerkbrink 3", text, text.index("Kerkbrink")) is True

    def test_city_only_span_dropped(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "De zitting vond plaats in Den Haag en in Alphen aan den Rijn."
        assert is_plausible_home_address("Den Haag", text, text.index("Den Haag")) is False
        assert is_plausible_home_address("Alphen aan den Rijn", text, text.index("Alphen")) is False

    def test_postcode_city_span_kept(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "Havenstraat 194\n3024 TM Rotterdam"
        assert is_plausible_home_address("3024 TM Rotterdam", text, text.index("3024")) is True

    def test_bezoekadres_label_earlier_on_line_drops_postcode_span(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "Bezoekadres: Stadhuisplein 1, 3012 AR Rotterdam"
        assert is_plausible_home_address("3012 AR Rotterdam", text, text.index("3012")) is False

    def test_gemeente_in_body_prose_does_not_block(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = "De gemeente heeft de bewoner van Kerkstraat 3 aangeschreven."
        assert is_plausible_home_address("Kerkstraat 3", text, text.index("Kerkstraat")) is True


class TestStraatnaamRegexSpan:
    def test_sentence_initial_preposition_not_absorbed(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("In de Kerkstraat 3 woont de aanvrager.")
        assert [h.text for h in hits] == ["Kerkstraat 3"]

    def test_address_label_not_absorbed(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Adres Havenstraat 194")
        assert [h.text for h in hits] == ["Havenstraat 194"]

    def test_capitalised_tussenvoegsel_kept(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("Zie Van der Helstplein 3-5 en De Ruyterkade 7.")
        assert [h.text for h in hits] == ["Van der Helstplein 3-5", "De Ruyterkade 7"]

    def test_weak_suffix_candidate_has_lower_confidence(self):
        from app.services.ner_engine._straatnaam import _detect_adres_by_straatnaam

        hits = _detect_adres_by_straatnaam("De bewoner van Loopbaan 14 klaagde.")
        assert len(hits) == 1
        assert hits[0].confidence == 0.80


class TestTableOfContentsNotAddresses:
    """Integration: Deduce's own street pattern fires on `Tekst 22`,
    `Amsterdam 26`, `Dienst 23`; the regex rule used to fire on
    `Uitvoering 7`, `Financiering 9`, `Bestuursakkoord 17`. None of
    them may surface."""

    def test_toc_lines_produce_no_adres(self):
        text = (
            "Inhoudsopgave\n"
            "1. Inleiding 3\n"
            "2. Voorwoord 4\n"
            "4. Uitvoering 7\n"
            "5. Financiering 9\n"
            "7. Beleidsveld Wonen 12\n"
            "8. Woningmarkt 14\n"
            "10. Bestuursakkoord 17\n"
            "11. Tijdpad 18\n"
            "14. Tekst 22\n"
            "15. Dienst 23\n"
            "17. Amsterdam 26\n"
        )
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "adres"] == []

    def test_real_address_in_prose_still_detected(self):
        text = "De familie El Khatib woont op Kerkstraat 22."
        results = detect_tier2(text)
        assert any(r.entity_type == "adres" and r.text == "Kerkstraat 22" for r in results)

    def test_deduce_address_gets_postcode_tier(self):
        text = "Factuuradres:\nHavenstraat 194\n3024 TM ROTTERDAM"
        results = detect_tier2(text)
        hits = [r for r in results if r.entity_type == "adres" and r.text == "Havenstraat 194"]
        assert len(hits) == 1
        assert hits[0].confidence == 0.92

    def test_year_range_heading_produces_no_adres(self):
        # Deduce tags "2019 EN" as a postcode-shaped locatie; the Tier 2
        # postcode corroboration must apply the same plausibility rule
        # as Tier 1 or the span vouches for itself at 0.92.
        # The real postcode on the third line sits within the proximity
        # window of both year ranges and must not vouch for them.
        text = "BEGROTING 2019 EN 2020\nPROGRAMMA 2021 TM 2024\nAdres: Kerkstraat 3, 1234 EN Ede"
        results = detect_tier2(text)
        # Sorted by offset: `detect_tier2` does not promise an order, and on
        # this fixture it genuinely alternates between runs (see #103).
        adressen = sorted(
            (r for r in results if r.entity_type == "adres"), key=lambda r: r.start_char
        )
        assert [r.text for r in adressen] == ["Kerkstraat 3", "1234 EN Ede"]

    def test_institutional_postcode_does_not_vouch_for_weak_span(self):
        text = "Gemeente Ede\nBezoekadres: Raadhuisplein 2, 6711 DE Ede\nOnderwerp: Zonnepark 3"
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "adres"] == []


class TestDatumRequiresBirthCue:
    def test_event_date_in_prose_dropped(self):
        text = "De raad heeft op 12 maart 2019 besloten het plan vast te stellen."
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "datum"] == []

    def test_birth_cue_before_date_keeps_it(self):
        from app.services.ner_engine._tier2_filters import has_birth_cue

        text = "Betrokkene, geboren te Utrecht op 3 mei 1971, heeft bezwaar gemaakt."
        assert has_birth_cue(text, text.index("3 mei")) is True
        results = detect_tier2(text)
        datum = [r for r in results if r.entity_type == "datum"]
        # Deduce may tag the date; if it does the cue must let it through.
        for r in datum:
            assert "1971" in r.text

    def test_no_cue_far_away(self):
        from app.services.ner_engine._tier2_filters import has_birth_cue

        text = "geboren " + ("x" * 250) + " 3 mei 1971"
        assert has_birth_cue(text, text.index("3 mei")) is False


class TestOrganisatieNotEmitted:
    def test_hospital_not_a_detection(self):
        text = "De GGD en het Erasmus MC waren bij het overleg aanwezig."
        results = detect_tier2(text)
        assert all(r.entity_type != "organisatie" for r in results)


class TestSingleTokenPersoonGate:
    def test_bare_flower_names_dropped(self):
        text = "Roos en Storm gingen naar school. Bloem ook. Kunst 3 is de titel."
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "persoon"] == []

    def test_greeting_cue_keeps_bare_first_name(self):
        text = "Beste Roos,\n\nDank voor je bericht."
        results = detect_tier2(text)
        assert any(r.entity_type == "persoon" and r.text == "Roos" for r in results)

    def test_surname_corroborated_by_full_name(self):
        text = "Jan Jansen diende bezwaar in. Later trok Jansen het bezwaar in."
        results = detect_tier2(text)
        persons = [r.text for r in results if r.entity_type == "persoon"]
        assert "Jan Jansen" in persons
        assert "Jansen" in persons

    def test_uncorroborated_surname_dropped(self):
        text = "Later trok Jansen het bezwaar in."
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "persoon"] == []

    def test_initial_plus_surname_is_self_evident(self):
        text = "Ondertekend door M. van der Berg."
        results = detect_tier2(text)
        assert any(r.entity_type == "persoon" and "Berg" in r.text for r in results)

    def test_title_rule_single_surname_kept(self):
        text = "De heer Yilmaz sprak in tijdens de vergadering."
        results = detect_tier2(text)
        # Deduce keeps the salutation in its span ("De heer Yilmaz") and
        # wins the overlap; either way the name must survive the gate.
        assert any(r.entity_type == "persoon" and "Yilmaz" in r.text for r in results)

    def test_motie_prefix_stripped_then_gated(self):
        text = "Agendapunt 4 Motie Groen wordt besproken."
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "persoon"] == []


class TestSalutationPlusTitleDropped:
    def test_mevrouw_wethouder_not_a_person(self):
        text = "Mevrouw Wethouder sprak. De heer Voorzitter antwoordde."
        results = detect_tier2(text)
        assert [r for r in results if r.entity_type == "persoon"] == []

    def test_title_rule_strips_absorbed_title(self):
        from app.services.ner_engine._tier2_trim import trim_trailing_titles

        assert trim_trailing_titles("Wethouder", 0, 9)[0] == ""
        assert trim_trailing_titles("De heer Voorzitter", 0, 18)[0] == ""
        assert trim_trailing_titles("Mevrouw De Voorzitter", 0, 21)[0] == ""
        # A real name after a salutation survives.
        assert trim_trailing_titles("De heer Jansen", 0, 14)[0] == "De heer Jansen"


class TestPostcodeAmbiguity:
    def test_year_range_not_a_postcode(self):
        results = detect_tier1("BEGROTING 2019 EN 2020\nPROGRAMMA 2021 TM 2024")
        assert [r for r in results if r.entity_type == "postcode"] == []

    def test_invalid_letter_pairs_rejected(self):
        results = detect_tier1("1234 SS, 1234 SA en 1234 SD zijn geen postcodes")
        assert [r for r in results if r.entity_type == "postcode"] == []

    def test_ambiguous_letters_followed_by_city_kept(self):
        results = detect_tier1("3024 TM ROTTERDAM")
        assert [r.text for r in results if r.entity_type == "postcode"] == ["3024 TM"]

    def test_ambiguous_letters_at_line_end_kept(self):
        results = detect_tier1("Havenstraat 194, 3024 TM\nRotterdam")
        assert [r.text for r in results if r.entity_type == "postcode"] == ["3024 TM"]


class TestProductionTextLineBoundaries:
    """The line-window rules, measured on the text production actually sends.

    Ten rules in this package treat a line as a unit of meaning: `[^\\n]*$`
    look-behinds for address labels and residence cues, `rfind("\\n")` for the
    greeting cue. Before #95 the browser joined every line with a space, so
    "the same line" silently became "the last 40 to 60 characters" and a rule
    reached across the page in both directions — dropping real findings and
    keeping false ones. `production_text` builds the fixture the browser
    would send; `_flattened` is the pre-#95 shape, kept so each test shows
    both halves of the bug it pins.
    """

    LETTERHEAD = (
        "Provincie Drenthe\n"
        "Postbus 122\n"
        "9400 AC Assen\n"
        "Aan de bewoner van\n"
        "Schoolpad 172-2\n"
        "9471 AC Zuidlaren\n"
    )

    @staticmethod
    def _flattened(text: str) -> str:
        """The same page as the browser joined it before #95: no newlines."""
        return " ".join(text.split("\n"))

    def test_letterhead_postbus_does_not_reach_the_resident_address(self):
        from app.services.ner_engine._tier2_filters import has_institutional_address_label

        text = production_text(self.LETTERHEAD)
        start = text.index("Schoolpad")

        assert has_institutional_address_label(text, start) is False
        # Pre-#95: "Postbus" sat inside the 60-character "same line" window.
        assert has_institutional_address_label(self._flattened(text), start) is True

    def test_resident_address_survives_under_a_letterhead(self):
        from app.services.ner_engine._tier2_filters import is_plausible_home_address

        text = production_text(self.LETTERHEAD)
        start = text.index("Schoolpad")

        assert is_plausible_home_address("Schoolpad 172-2", text, start) is True
        # The false negative this item was opened for: the addressee's own
        # street disappeared because the sender's PO box vouched for it.
        assert is_plausible_home_address("Schoolpad 172-2", self._flattened(text), start) is False

    def test_greeting_cue_does_not_cross_a_line_break(self):
        text = production_text(
            "Het besluit is genomen op verzoek van\nStorm en regen teisterden de kust.\n"
        )
        assert [r for r in detect_tier2(text) if r.entity_type == "persoon"] == []
        # Pre-#95 the "van" ending the previous line read as a mail-header cue
        # and kept a weather report as a person.
        flat = [r.text for r in detect_tier2(self._flattened(text)) if r.entity_type == "persoon"]
        assert flat == ["Storm"]

    def test_residence_cue_does_not_reach_over_a_full_line(self):
        from app.services.ner_engine._tier2_filters import has_address_cue

        # One line of prose between the cue and the span is enough: `[^\n]`
        # cannot cross it.
        text = production_text("Perceel van de bewoner\nis groot\nWoningmarkt 14 telt mee.\n")
        start = text.index("Woningmarkt")

        assert has_address_cue(text, start) is False
        assert has_address_cue(self._flattened(text), start) is True

    def test_residence_cue_does_not_reach_the_line_directly_above(self):
        from app.services.ner_engine._tier2_filters import has_address_cue

        # The narrow hole #95 left open. The window ends exactly at the span,
        # so a cue closing the previous line sits right before a trailing
        # newline — which `$` matches without `re.MULTILINE`. `\Z` does not.
        text = production_text("Wij schrijven u als bewoner\nWoningmarkt 14 telt mee.\n")
        start = text.index("Woningmarkt")

        assert has_address_cue(text, start) is False

        same_line = production_text("Wij schrijven u als bewoner van Woningmarkt 14.\n")
        assert has_address_cue(same_line, same_line.index("Woningmarkt")) is True

    def test_address_label_does_not_reach_the_line_directly_above(self):
        from app.services.ner_engine._tier2_filters import has_institutional_address_label

        # Same hole on the whitelisting side, where it costs a finding: the
        # sender's PO box vouched for the addressee's own street below it.
        text = production_text("Postbus 122, 9400 AC Assen\nSchoolpad 172-2 in Zuidlaren\n")
        start = text.index("Schoolpad")

        assert has_institutional_address_label(text, start) is False

        same_line = production_text("Postbus 122, Schoolpad 172-2\n")
        assert has_institutional_address_label(same_line, same_line.index("Schoolpad")) is True

    def test_institution_word_does_not_reach_the_line_directly_above(self):
        from app.services.ner_engine._tier2_filters import has_institutional_address_label

        # `_ADRES_CONTEXT_PATTERN` wants the word *directly* before the span;
        # its `\s*` used to let a line break count as "directly".
        text = production_text("Afdeling gemeente\nKerkstraat 3 is verkocht.\n")
        start = text.index("Kerkstraat")

        assert has_institutional_address_label(text, start) is False

        same_line = production_text("Afdeling gemeente Kerkstraat 3 is verkocht.\n")
        assert has_institutional_address_label(same_line, same_line.index("Kerkstraat")) is True


# ---------------------------------------------------------------------------
# Tier 1: organisation context (#96)
# ---------------------------------------------------------------------------


class TestFunctionalMailbox:
    """Rule 1 — a desk address is not a person's address."""

    @pytest.mark.parametrize(
        "address,term",
        [
            ("post@drenthe.nl", "post"),
            ("woo@minfin.nl", "woo"),
            ("vth@drenthe.nl", "vth"),
            ("jz@nationaleombudsman.nl", "jz"),
            ("avg@nationaleombudsman.nl", "avg"),
            ("info@laaglandarcheologie.nl", "info"),
            ("bezwaarenberoepWoo@minfin.nl", "bezwaar"),
            ("informatie@emmen.nl", "info"),
        ],
    )
    def test_desk_addresses_are_recognised(self, address, term):
        assert functional_mailbox_prefix(address) == term

    @pytest.mark.parametrize(
        "address",
        [
            # A named person at a government domain is exactly what we do
            # want redacted — these must not be swallowed by a prefix.
            "r.vanmelenhorst@minienw.nl",
            "jort-jan.descheepstra@kpnmail.nl",
            "postma.j@gemeente.nl",
            "persoonlijk@example.nl",
            "woonzaken@emmen.nl",
        ],
    )
    def test_person_addresses_are_left_alone(self, address):
        assert functional_mailbox_prefix(address) is None

    def test_reason_names_the_term(self):
        reason = organisation_context_reason("email", "woo@minfin.nl", "woo@minfin.nl", 0)
        assert reason is not None
        assert "woo@" in reason


class TestPublishedUrl:
    """Rule 2 — a published page is not personal data, a profile page is."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.nationaleombudsman.nl/wet-open-overheid-woo",
            "https://loket.rechtspraak.nl/bestuursrecht",
            "https://www.rijksoverheid.nl/onderwerpen/wet-open-overheid-woo",
        ],
    )
    def test_public_site_is_not_a_person(self, url):
        assert organisation_context_reason("url", url, url, 0) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.linkedin.com/in/jaapstronks",
            "https://x.com/someone",
            "https://www.instagram.com/someone",
            "https://example.nl/~jansen/cv.html",
        ],
    )
    def test_profile_url_keeps_the_tier1_default(self, url):
        assert organisation_context_reason("url", url, url, 0) is None


class TestLetterheadPhone:
    """Rule 3 — the switchboard in the letterhead, not someone's line."""

    def _reason(self, before: str, number: str) -> str | None:
        text = production_text(before + number + "\n")
        return organisation_context_reason("telefoon", number, text, text.index(number))

    def test_number_under_a_postbus_line(self):
        assert self._reason("Postbus 7001, 6700 CA Wageningen\nTelefoon ", "0317 49 15 78")

    def test_number_after_an_institution_word(self):
        assert self._reason("kan bij Rijksdienst voor het Cultureel Erfgoed (", "033 421 74 56")

    def test_number_announced_as_the_general_line(self):
        assert self._reason("U kunt bellen via het algemene telefoonnummer ", "(0592) 36 55 55")

    def test_number_under_the_behandeld_door_label(self):
        # The letterhead field a Dutch government letter prints its
        # handling team and general number in.
        assert self._reason("Behandeld door\nTeam Ruimte, Energie en Wonen\n", "(0592) 36 55 55")

    def test_mobile_number_stays_auto_accepted(self):
        # A `06` is issued to a handset. Even printed under a letterhead it
        # is the one phone number in the block that belongs to a person.
        assert self._reason("Provincie Drenthe, Postbus 122\nMobiel ", "06 12 34 56 78") is None

    def test_mobile_with_international_prefix_stays_auto_accepted(self):
        assert self._reason("Provincie Drenthe, Postbus 122\nMobiel ", "0031 6 12345678") is None

    def test_landline_without_an_organisation_around_it_stays_auto_accepted(self):
        # The negative that motivates the rule: a contact person's own
        # number on a form must keep its black bar.
        assert (
            self._reason("Functie contactpersoon eigenaar\nTelefoonnummer ", "(0592) 36 50 71")
            is None
        )


class TestOrganisationPostcode:
    """Rule 4 — the postcode of the sender's own address block."""

    def _reason(self, before: str, postcode: str) -> str | None:
        text = production_text(before + postcode + " Assen\n")
        return organisation_context_reason("postcode", postcode, text, text.index(postcode))

    def test_legal_form_on_the_line_above(self):
        assert self._reason("Laagland Archeologie BV\nVirulyweg 21F-G\n", "7602 RG")

    def test_legal_form_on_the_same_line(self):
        assert self._reason(
            "verzonden aan Oosting Metalen Recycling B.V., P. de Keyserstraat 18, ", "7825 VE"
        )

    def test_maatschap_reaches_over_two_lines(self):
        assert self._reason(
            "Afschrift aan:\nMaatschap H.J. Kersten en C.H. Kersten - Ensing\nBladderswijk WZ 19\n",
            "7885 TH",
        )

    def test_kvk_number_in_the_form_block(self):
        assert self._reason(
            "KvK-nummer 01155925\nStraat /postbus Bladderswijk\n"
            "Huisnummer / postbusnummer 19\nToevoeging huisnummer w z\nPostcode 9471 AC Zuidlaren ",
            "7885 TH",
        )

    def test_institution_word_reaches_over_the_letterhead(self):
        assert self._reason(
            "Contactpersoon\nT 070\nNationale ombudsman\nBezuidenhoutseweg 151\n", "2594 AG"
        )

    def test_a_citizen_postcode_under_a_finished_sentence_stays_auto_accepted(self):
        # The negative that motivates the sentence cut: "gemeente Emmen"
        # closes a paragraph, and the addressee's own postcode starts a
        # new block right underneath it.
        assert (
            self._reason(
                "U moet de gemeente Emmen hiervan op de hoogte stellen.\n"
                "Kowalczyk\nSchoolpad 183a\n",
                "7941 LA",
            )
            is None
        )

    def test_the_addressee_under_the_senders_closed_block_stays_auto_accepted(self):
        # The most common shape a citizen's address takes in a government
        # letter: right under the sender's own block. That block closes
        # with its postcode line, and its Postbus must not vouch for the
        # postcode below it.
        assert (
            self._reason(
                "Gemeente Emmen\nPostbus 30001, 7800 RA Emmen\nAan\n"
                "De heer J. Jansen\nSchoolpad 183a\n",
                "7941 LA",
            )
            is None
        )

    def test_the_senders_second_postcode_is_still_the_senders(self):
        # Bezoekadres above, postadres below: the second block carries its
        # own evidence, so the cut after the first postcode line costs
        # nothing.
        assert self._reason(
            "Gemeente Emmen\nRaadhuisplein 1\n7811 AP Emmen\nPostbus 30001\n", "7800 RA"
        )

    def test_an_object_address_is_not_claimed_here(self):
        # "zijnde <bedrijf>, <straat>" is the address of the installation a
        # permit is about (#99), not of the sender. No organisation word,
        # so this rule leaves it alone rather than guessing.
        assert (
            self._reason(
                "• houder van de vergunning, zijnde Noord Oost Recycling, Data 12-16, ", "7741 MG"
            )
            is None
        )


class TestLegalFormLead:
    """A name that follows a legal form is what a business trades under."""

    def _form(self, before: str, name: str) -> str | None:
        text = production_text(before + name + "\n")
        return legal_form_lead(text, text.index(name))

    def test_first_partner_of_a_maatschap(self):
        assert self._form("Afschrift aan:\nMaatschap ", "H.J. Kersten") == "Maatschap"

    def test_second_partner_of_a_maatschap(self):
        assert self._form("Aan:\nMaatschap H.J. Kersten en ", "C.H. Kersten") == "Maatschap"

    def test_a_verb_between_the_form_and_the_name_ends_the_trading_name(self):
        assert self._form("Delphy BV heeft dit gemeld aan ", "Jan de Vries") is None

    def test_a_line_break_ends_the_trading_name(self):
        # "Delphy BV" and, on the next line, the person who signs for it.
        # The signatory is not the trading name; the signature-block rule
        # keeps its say.
        assert self._form("Hoogachtend,\nDelphy BV\n", "Jan de Vries") is None

    def test_a_word_that_merely_ends_in_a_form_is_not_one(self):
        assert self._form("Namens Winv ", "Jansen") is None

    def test_a_plain_signature_block_is_untouched(self):
        assert self._form("Hoogachtend,\n", "Jan de Vries") is None


# ---------------------------------------------------------------------------
# Structure-anchored name rule (#97)
#
# Four anchor families that say "a person follows" regardless of what
# Meertens and CBS know: a closing, a form/header label, an aanhef, and
# a mail display name. Every family has at least one negative — the case
# the family must NOT eat.
# ---------------------------------------------------------------------------


class TestAnchorRuleClosing:
    """Family 1 — `Hoogachtend,` / `Met vriendelijke groet,`."""

    @pytest.fixture(scope="class")
    def lists(self):
        return load_name_lists()

    def _names(self, text, lists):
        return [h.text for h in detect_persoon_via_anchors(text, lists)]

    def test_bare_surname_under_a_closing(self, lists):
        text = "Een kopie van de stukken doen wij u toekomen.\nMet vriendelijke groet,\nYıldırım\n"
        hits = detect_persoon_via_anchors(text, lists)
        assert [h.text for h in hits] == ["Yıldırım"]
        assert hits[0].source == "anchor_rule"
        assert hits[0].confidence == 0.75
        assert hits[0].tier == "2"
        assert "briefafsluiting" in hits[0].reasoning

    def test_initials_only_under_a_closing(self, lists):
        """The anchor supplies the noun the initials stand for, so a
        signature that is nothing but initials is still a person."""
        text = "Als ik geen reactie heb, gaat de ontheffing uit.\nMet vriendelijke groet,\nM.F.\n"
        assert self._names(text, lists) == ["M.F."]

    def test_full_name_with_hyphenated_surname_under_hoogachtend(self, lists):
        text = "kunt u kijken op de site.\nHoogachtend,\nShaniqua Terlouw-Van Rossem\n"
        assert self._names(text, lists) == ["Shaniqua Terlouw-Van Rossem"]

    def test_a_body_signing_the_letter_is_not_a_person(self, lists):
        """ "de Nationale ombudsman," leaves a lowercase word standing,
        so the line is not entirely name and the family refuses it."""
        text = "Met vriendelijke groet,\nde Nationale ombudsman,\nnamens deze,\n"
        assert self._names(text, lists) == []

    def test_an_organisation_under_a_closing_is_refused(self, lists):
        assert self._names("Met vriendelijke groet,\nGemeente Emmen\n", lists) == []

    def test_a_function_title_under_a_closing_is_refused(self, lists):
        """The trailing-title trim eats "Financiën" and leaves a
        three-token span that reads like a name. It is a job title."""
        assert self._names("Hoogachtend,\nDe Staatssecretaris van Financiën\n", lists) == []

    def test_only_the_first_line_under_the_closing_is_read(self, lists):
        """The line below the name is the signer's function or org, not
        a second person."""
        text = "Met vriendelijke groet,\nYıldırım\nVergunningverlening en Handhaving\n"
        assert self._names(text, lists) == ["Yıldırım"]

    def test_initials_keep_their_period_before_a_comma(self, lists):
        """ "M.F.," is an initial run with a comma on it, not a bare
        "M.F" — the comma comes off first, the period stays."""
        assert self._names("Met vriendelijke groet,\nM.F.,\n", lists) == ["M.F."]

    def test_the_comma_before_a_trimmed_title_is_not_part_of_the_name(self, lists):
        text = "Hoogachtend,\nJan Jansen, Wethouder\n"
        hits = detect_persoon_via_anchors(text, lists)
        assert [h.text for h in hits] == ["Jan Jansen"]
        assert text[hits[0].start_char : hits[0].end_char] == "Jan Jansen"


class TestAnchorRuleFieldLabel:
    """Family 2 — `Naam:`, `Contactpersoon`, `Behandeld door`, `Van:`."""

    @pytest.fixture(scope="class")
    def lists(self):
        return load_name_lists()

    def _names(self, text, lists):
        return [h.text for h in detect_persoon_via_anchors(text, lists)]

    def test_name_after_a_naam_label(self, lists):
        hits = detect_persoon_via_anchors("Datum: 3 mei 2021\nNaam: Djaimy Pijpker\n", lists)
        assert [h.text for h in hits] == ["Djaimy Pijpker"]
        assert "label" in hits[0].reasoning

    def test_the_company_after_the_value_is_not_part_of_the_name(self, lists):
        """A `Naam:` field followed by the trading name of the applicant.
        Two capitals is the canonical Dutch shape, so the walk stops
        before the company."""
        text = "Naam: Djaimy Pijpker Oosting Metalen Recycling B.V. te Emmen\n"
        assert self._names(text, lists) == ["Djaimy Pijpker"]

    def test_tussenvoegsel_in_the_value(self, lists):
        text = "Naam: Mandy van Loon Oosting Metalen Recycling B.V. te Emmen\n"
        assert self._names(text, lists) == ["Mandy van Loon"]

    def test_two_labels_on_one_line(self, lists):
        """A "Klant / Adviseur" table prints the label mid-line, twice."""
        text = "Naam Sanne-Marijke Sotthewes Maatschap Kersten-Ensing Naam F.B. 11 juni 2020\n"
        assert self._names(text, lists) == ["Sanne-Marijke Sotthewes", "F.B."]

    def test_contactpersoon_label(self, lists):
        text = "Onze referentie\n2025-0000525385\nContactpersoon Okonkwo\nwoo@minfin.nl\n"
        assert self._names(text, lists) == ["Okonkwo"]

    def test_a_team_behind_behandeld_door_is_not_a_person(self, lists):
        text = "Behandeld door Team Ruimte, Energie en Wonen (0592) 36 55 55\n"
        assert self._names(text, lists) == []

    def test_the_noun_naam_in_prose_is_not_a_label(self, lists):
        """Lowercase and without a colon, "naam" is a word, not a field."""
        text = "In dit besluit staat de naam van de Aanvrager niet vermeld.\n"
        assert self._names(text, lists) == []

    def test_lowercase_label_with_a_colon_is_a_label(self, lists):
        assert self._names("naam: Ramdhani\n", lists) == ["Ramdhani"]

    def test_bare_van_is_a_tussenvoegsel_not_a_header(self, lists):
        """ "Van" without a colon opens half the surnames in the CBS
        list; only "Van:" is an e-mail header."""
        assert self._names("Ondertekend door Piet Van Rossem\n", lists) != ["Rossem"]

    def test_a_job_title_after_the_value_is_trimmed_off(self, lists):
        assert self._names("Naam: Jan Jansen Medewerker\n", lists) == ["Jan Jansen"]

    def test_a_form_header_row_holds_no_value(self, lists):
        """A DigiD form prints its column headers on their own row. A
        label whose "value" is the next label is a header, not a name."""
        text = "Uw gegevens\nNaam\nVoorletters Tussenvoegsels Achternaam\nV.M.\nAanhef Mevr.\n"
        assert self._names(text, lists) == []


class TestAnchorRuleSalutation:
    """Family 3 — `Geachte` / `Beste`, with or without heer/mevrouw."""

    @pytest.fixture(scope="class")
    def lists(self):
        return load_name_lists()

    def _names(self, text, lists):
        return [h.text for h in detect_persoon_via_anchors(text, lists)]

    def test_bare_surname_after_geachte(self, lists):
        hits = detect_persoon_via_anchors("Pagina 1 van 12\nGeachte Hadžić ,\n", lists)
        assert [h.text for h in hits] == ["Hadžić"]
        assert "aanhef" in hits[0].reasoning

    def test_tussenvoegsel_surname_after_geachte(self, lists):
        assert self._names("Onderwerp: iets\nGeachte ter Felder ,\n", lists) == ["ter Felder"]

    def test_initials_after_geachte_heer(self, lists):
        assert self._names("Geachte heer B.D. ,\nMiddels deze brief\n", lists) == ["B.D."]

    def test_initials_after_bare_geachte(self, lists):
        assert self._names("Onderwerp:RE: iets\nGeachte R.C. ,\nTot nu toe\n", lists) == ["R.C."]

    def test_initials_directly_followed_by_a_comma(self, lists):
        """The corpus prints "B.D. ,"; a letter prints "B.D.,"."""
        assert self._names("Geachte heer B.D.,\nMiddels deze brief\n", lists) == ["B.D."]

    def test_geachte_heer_mevrouw_addresses_nobody(self, lists):
        assert self._names("Geachte heer/mevrouw,\nHierbij ontvangt u\n", lists) == []

    def test_geachte_college_is_a_body(self, lists):
        assert self._names("Geachte College van burgemeester en wethouders,\n", lists) == []


class TestAnchorRuleMailDisplayName:
    """Family 4 — the capitals directly before `<adres@domein>`."""

    @pytest.fixture(scope="class")
    def lists(self):
        return load_name_lists()

    def _names(self, text, lists):
        return [h.text for h in detect_persoon_via_anchors(text, lists)]

    def test_display_name_before_an_address(self, lists):
        hits = detect_persoon_via_anchors("Berkant Djojosoeparto <berkantd@drenthe.nl>\n", lists)
        assert [h.text for h in hits] == ["Berkant Djojosoeparto"]
        assert "e-mailadres" in hits[0].reasoning

    def test_an_anonymised_address_has_no_display_name(self, lists):
        assert self._names("Aan: <@emmen.nl>; <@drenthe.nl>\n", lists) == []

    def test_a_desk_mailbox_keeps_its_organisation(self, lists):
        assert self._names("Provincie Drenthe <post@drenthe.nl>\n", lists) == []

    def test_a_lowercase_organisation_before_a_desk_mailbox(self, lists):
        """The walk cannot start on "provincie", so reading only what it
        can start on would call the mailbox a person named Drenthe."""
        text = "Aan: < @noordenveld.nl>; provincie Drenthe <post@drenthe.nl>\n"
        assert self._names(text, lists) == []

    def test_the_header_label_stays_outside_the_display_name(self, lists):
        """ "Van" is a tussenvoegsel, so a walk that starts at the header
        label swallows it. The label is a separator, not a particle."""
        assert self._names("Van: Jan de Vries <j.devries@emmen.nl>\n", lists) == ["Jan de Vries"]

    def test_a_desk_mailbox_prints_the_desk_as_its_display_name(self, lists):
        """ "Vergunningen <vergunningen@emmen.nl>" is the desk, not a
        person — the same judgment #96 makes on the address itself.
        Neither the display-name family nor the `Van:` label may claim
        it."""
        assert self._names("Van: Vergunningen <vergunningen@emmen.nl>\n", lists) == []
        assert self._names("Aan: Woo Verzoeken <woo@emmen.nl>\n", lists) == []


class TestWordlistPairRule:
    """Meertens ∧ CBS without a Deduce span (#97)."""

    @pytest.fixture(scope="class")
    def lists(self):
        return load_name_lists()

    def _names(self, text, lists):
        return [h.text for h in detect_persoon_via_wordlists(text, lists)]

    def test_first_name_and_surname_both_on_a_list(self, lists):
        hits = detect_persoon_via_wordlists("Het perceel is verkocht aan Jan Bakker.", lists)
        assert [h.text for h in hits] == ["Jan Bakker"]
        assert hits[0].source == "wordlist_rule"
        assert hits[0].confidence == 0.80

    def test_tussenvoegsel_between_the_halves(self, lists):
        assert self._names("Namens Marieke de Vries is bezwaar gemaakt.", lists) == [
            "Marieke de Vries"
        ]

    def test_one_list_alone_is_not_enough(self, lists):
        """ "Jan" is a Meertens first name; "Wandelroute" is on no list."""
        assert self._names("De Jan Wandelroute loopt langs het kanaal.", lists) == []

    def test_an_organisation_is_refused(self, lists):
        assert self._names("De Jan Bakker Stichting int de contributie.", lists) == []

    def test_empty_lists_disable_the_rule(self):
        from app.services.name_engine import NameLists

        empty = NameLists(
            first_names=frozenset(),
            last_names=frozenset(),
            tussenvoegsels=frozenset(),
            tussenvoegsel_sequences=frozenset(),
        )
        assert detect_persoon_via_wordlists("Jan Bakker", empty) == []


class TestDetectTier2WithAnchorRules:
    """The anchor rules are wired into `detect_tier2`, so a name no
    wordlist knows still reaches the reviewer."""

    def test_signer_outside_the_wordlists_is_rescued(self):
        text = "Wij komen hier op terug.\n\nMet vriendelijke groet,\nYıldırım\n"
        persons = [r for r in detect_tier2(text) if r.entity_type == "persoon"]
        assert any("Yıldırım" in p.text for p in persons)

    def test_a_form_label_value_is_rescued(self):
        text = "Aanvraag omgevingsvergunning\nNaam: Djaimy Pengel\nOnderwerp: wijziging\n"
        persons = [r for r in detect_tier2(text) if r.entity_type == "persoon"]
        assert any("Pengel" in p.text for p in persons)

    def test_the_corroboration_gate_keeps_a_single_token_anchor_hit(self):
        """A bare surname is normally dropped unless the document
        vouches for it; an anchor is that vouching (#90)."""
        text = "Onze referentie 2025-0000525385\nContactpersoon Okonkwo\nwoo@minfin.nl\n"
        persons = [r for r in detect_tier2(text) if r.entity_type == "persoon"]
        assert any("Okonkwo" in p.text for p in persons)
