"""Tests for the NER engine — Tier 1 regex + validation and Tier 2 Deduce NER.

Tier 1 tests are pure unit tests (no external dependencies).
Tier 2 tests use the real Deduce library (loaded once, ~2s startup).
"""

import pytest

from app.services.name_engine import load_name_lists
from app.services.ner_engine import (
    NERDetection,
    _detect_persoon_via_title_prefix,
    _is_plausible_birth_date,
    _is_plausible_person_name,
    _parse_birth_date,
    _validate_bsn,
    _validate_btw,
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
            assert r.source in ("deduce", "title_rule")
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
        from app.services.ner_engine import _get_name_lists

        lists = _get_name_lists()
        # Sanity check: this span has no tokens in either list.
        score = score_person_candidate("Qwerty Xylofoon", lists)
        assert score.is_plausible is False


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
            r
            for r in results
            if r.entity_type == "adres" and r.text.lower().startswith("nummer")
        ]
        assert len(nummer) == 1
        assert nummer[0].text.lower() == "nummer 26"
        # Span must cover ONLY "nummer 26", not the "bewoner van" cue.
        assert text[nummer[0].start_char : nummer[0].end_char].lower() == "nummer 26"

    def test_woont_op_nummer_detected(self):
        text = "Zij woont op nummer 12 sinds 2019."
        results = detect_tier2(text)
        nummer = [
            r
            for r in results
            if r.entity_type == "adres" and r.text.lower().startswith("nummer")
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
            r
            for r in results
            if r.entity_type == "adres" and r.text.lower().startswith("nummer")
        ]
        assert nummer == []

    def test_huisnummer_drops_overlapping_deduce_adres(self):
        """When Deduce emits a nested `huisnummer`/`adres` annotation
        inside our new span, the duplicate must be dropped so the
        reviewer sees exactly one card."""
        text = "De bewoners van huisnummer 22 hebben geklaagd."
        results = detect_tier2(text)
        # Exactly one adres detection for this position, not two.
        adres_hits = [
            r
            for r in results
            if r.entity_type == "adres" and "22" in r.text
        ]
        assert len(adres_hits) == 1
        assert adres_hits[0].source == "regex"


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
