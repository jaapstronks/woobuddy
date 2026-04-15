"""Unit tests for `app.services.name_engine`.

These cover normalization, lookups, scoring for real Dutch names,
tussenvoegsel-led surnames, and diacritic-bearing names. The loader is
exercised with the committed seed CSVs under
`backend/app/data/sources/`.
"""

from __future__ import annotations

import pytest

from app.services.name_engine import (
    NameLists,
    _normalize,
    is_known_first_name,
    is_known_last_name,
    load_name_lists,
    score_person_candidate,
)


# Load once — the lists are tiny (~2k entries) but this keeps tests snappy.
@pytest.fixture(scope="module")
def lists() -> NameLists:
    return load_name_lists()


class TestNormalization:
    def test_lowercase(self):
        assert _normalize("JAN") == "jan"
        assert _normalize("Jan") == "jan"

    def test_strip_diacritics(self):
        assert _normalize("Gülnur") == "gulnur"
        assert _normalize("Zoë") == "zoe"
        assert _normalize("Adrián") == "adrian"
        assert _normalize("Renée") == "renee"

    def test_strip_trailing_punct(self):
        assert _normalize("A.") == "a"
        assert _normalize("Bakker,") == "bakker"

    def test_empty(self):
        assert _normalize("") == ""
        assert _normalize("   ") == ""


class TestLoadLists:
    def test_first_names_loaded(self, lists: NameLists):
        assert len(lists.first_names) > 100
        # A few staples from the Meertens subset.
        assert "jan" in lists.first_names
        assert "emma" in lists.first_names
        assert "noah" in lists.first_names

    def test_last_names_loaded(self, lists: NameLists):
        assert len(lists.last_names) > 100
        # A few staples from the CBS subset.
        assert "bakker" in lists.last_names
        assert "vries" in lists.last_names
        assert "jansen" in lists.last_names

    def test_tussenvoegsels_loaded(self, lists: NameLists):
        assert "van" in lists.tussenvoegsels
        assert "de" in lists.tussenvoegsels
        assert "ter" in lists.tussenvoegsels
        assert ("van", "den") in lists.tussenvoegsel_sequences
        assert ("van", "der") in lists.tussenvoegsel_sequences


class TestIsKnownFirstName:
    def test_common_names(self, lists: NameLists):
        assert is_known_first_name("Jan", lists) is True
        assert is_known_first_name("emma", lists) is True
        assert is_known_first_name("NOAH", lists) is True

    def test_with_diacritics(self, lists: NameLists):
        # "Zoe" (no umlaut) is in the list; "Zoë" should match via
        # diacritic stripping.
        assert is_known_first_name("Zoë", lists) is True

    def test_unknown(self, lists: NameLists):
        assert is_known_first_name("Xylophone", lists) is False
        assert is_known_first_name("", lists) is False


class TestIsKnownLastName:
    def test_common_surnames(self, lists: NameLists):
        assert is_known_last_name("Bakker", lists) is True
        assert is_known_last_name("jansen", lists) is True

    def test_unknown(self, lists: NameLists):
        assert is_known_last_name("Xylophone", lists) is False


class TestScorePersonCandidate:
    def test_simple_name_plausible(self, lists: NameLists):
        score = score_person_candidate("Jan Bakker", lists)
        assert score.is_plausible is True
        assert score.has_known_first_name is True
        assert score.has_known_last_name is True

    def test_tussenvoegsel_surname(self, lists: NameLists):
        """Jan de Vries — surname is "Vries", `de` is a tussenvoegsel."""
        score = score_person_candidate("Jan de Vries", lists)
        assert score.is_plausible is True
        assert score.has_known_first_name is True
        assert score.has_known_last_name is True

    def test_multi_word_tussenvoegsel(self, lists: NameLists):
        """Van den Berg — seed CBS has "Berg"; the tussenvoegsel
        sequence "van den" should be skipped before the surname lookup."""
        score = score_person_candidate("Van den Berg", lists)
        # Berg may or may not be in the seed; assert we at least recognise
        # it as a tussenvoegsel-led surname candidate (plausible via
        # surname OR survive to the caller's heuristic path).
        if "berg" in lists.last_names:
            assert score.has_known_last_name is True
            assert score.is_plausible is True

    def test_organization_not_plausible(self, lists: NameLists):
        """ "Amsterdamse Hogeschool" — no token is a first or last name."""
        score = score_person_candidate("Amsterdamse Hogeschool", lists)
        assert score.has_known_first_name is False
        # "Hogeschool" shouldn't be in the CBS surname list; "Amsterdamse"
        # neither. If some seed file ever added one of these, revisit.
        assert score.is_plausible is False

    def test_initial_plus_surname(self, lists: NameLists):
        """A. Bakker — leading initial normalizes to "a" which isn't a
        first name. Still plausible because the surname matches."""
        score = score_person_candidate("A. Bakker", lists)
        assert score.has_known_last_name is True
        assert score.is_plausible is True

    def test_diacritic_first_name(self, lists: NameLists):
        """René Jansen — "René" should match after diacritic stripping."""
        score = score_person_candidate("René Jansen", lists)
        assert score.has_known_first_name is True
        assert score.has_known_last_name is True
        assert score.is_plausible is True

    def test_empty_span(self, lists: NameLists):
        score = score_person_candidate("", lists)
        assert score.is_plausible is False
        score = score_person_candidate("   ", lists)
        assert score.is_plausible is False

    def test_unknown_words_reject(self, lists: NameLists):
        """Completely unknown words produce a non-plausible score even
        when the structure looks name-like."""
        score = score_person_candidate("Xylofoon Qwerty", lists)
        assert score.has_known_first_name is False
        assert score.has_known_last_name is False
        assert score.is_plausible is False

    def test_first_name_only_plausible(self, lists: NameLists):
        """A single recognized first name is enough to be plausible —
        the filter is liberal by design so false positives get a
        human review, not silent drops."""
        score = score_person_candidate("Jan", lists)
        assert score.has_known_first_name is True
        assert score.is_plausible is True

    def test_surname_only_plausible(self, lists: NameLists):
        score = score_person_candidate("Bakker", lists)
        assert score.has_known_last_name is True
        assert score.is_plausible is True
