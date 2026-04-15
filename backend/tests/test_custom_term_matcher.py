"""Tests for the per-document custom-term matcher (#21).

Covers the pure matcher at the service level. End-to-end pipeline
behavior (how matches become `PipelineDetection` rows and how they
merge with overlapping Tier 1/2 detections) is covered in
`test_pipeline_engine.py`; HTTP CRUD round-trips live in their own test
file.
"""

from dataclasses import dataclass

from app.services.custom_term_matcher import (
    TermMatch,
    match_custom_terms,
    normalize_term,
)


@dataclass
class _Term:
    """Minimal stand-in for `DocumentCustomTerm` / `CustomTermPayload`.

    The matcher only requires `term`, `match_mode`, and `woo_article`,
    so using a lightweight dataclass keeps the tests free of DB setup.
    """

    term: str
    match_mode: str = "exact"
    woo_article: str = "5.1.2e"


class TestNormalizeTerm:
    def test_lowercases(self):
        assert normalize_term("Project Apollo") == "project apollo"

    def test_collapses_whitespace(self):
        assert normalize_term("Project    Apollo") == "project apollo"
        assert normalize_term("  Project Apollo  ") == "project apollo"

    def test_preserves_diacritics(self):
        # Unlike `normalize_reference_name` in the name engine (#17),
        # custom terms keep diacritics — a reviewer typing "Café Zuid"
        # expects a literal match, not "Cafe Zuid".
        assert normalize_term("Café Zuid") == "café zuid"

    def test_empty_and_whitespace(self):
        assert normalize_term("") == ""
        assert normalize_term("   ") == ""


class TestMatchCustomTerms:
    def test_exact_match_single_occurrence(self):
        matches = match_custom_terms(
            "Het dossier Project Apollo is vrijgegeven.",
            [_Term("Project Apollo")],
        )
        assert len(matches) == 1
        m = matches[0]
        assert isinstance(m, TermMatch)
        assert m.term == "Project Apollo"
        assert m.woo_article == "5.1.2e"
        assert m.match_mode == "exact"
        assert m.start_char == 12
        assert m.end_char == 12 + len("Project Apollo")

    def test_case_insensitive(self):
        text = "project apollo was PROJECT APOLLO vanaf dag 1."
        matches = match_custom_terms(text, [_Term("Project Apollo")])
        assert len(matches) == 2
        # Offsets must line up with the haystack, not the term.
        assert text.lower()[matches[0].start_char : matches[0].end_char] == "project apollo"
        assert text.lower()[matches[1].start_char : matches[1].end_char] == "project apollo"

    def test_multi_word_term(self):
        matches = match_custom_terms(
            "Over de klokkenluider NL-Alert is een klacht binnengekomen.",
            [_Term("klokkenluider NL-Alert")],
        )
        assert len(matches) == 1

    def test_substring_inside_longer_word(self):
        # Per the spec: a term that happens to be a substring of a
        # longer word must still match in exact mode. Reviewers aren't
        # engineers — they shouldn't need to think about `\b`.
        matches = match_custom_terms(
            "Het woord klokkenluider is gevoelig.",
            [_Term("luider")],
        )
        assert len(matches) == 1
        assert matches[0].start_char == len("Het woord klokken")

    def test_multiple_non_overlapping_occurrences(self):
        text = "Project Apollo startte in 1961. Project Apollo eindigde in 1972."
        matches = match_custom_terms(text, [_Term("Project Apollo")])
        assert len(matches) == 2
        assert matches[0].start_char < matches[1].start_char

    def test_non_overlapping_advance_for_repeating_chars(self):
        # "aaaa" with term "aa" yields two non-overlapping matches
        # (indices 0 and 2), not three (0, 1, 2). Overlapping hits
        # would double-count the middle character and confuse the
        # undo stack.
        matches = match_custom_terms("aaaa", [_Term("aa")])
        assert [(m.start_char, m.end_char) for m in matches] == [(0, 2), (2, 4)]

    def test_multiple_terms(self):
        matches = match_custom_terms(
            "Het rapport over Project Apollo en codenaam Zephyr is openbaar.",
            [_Term("Project Apollo"), _Term("Zephyr")],
        )
        assert len(matches) == 2
        terms = {m.term for m in matches}
        assert terms == {"Project Apollo", "Zephyr"}

    def test_empty_inputs(self):
        assert match_custom_terms("", [_Term("Project Apollo")]) == []
        assert match_custom_terms("Some text", []) == []

    def test_empty_term_is_skipped(self):
        matches = match_custom_terms("Some text", [_Term("   "), _Term("text")])
        assert len(matches) == 1
        assert matches[0].term == "text"

    def test_unimplemented_modes_are_skipped(self):
        # `prefix` and `whole_word` are reserved in the schema but not
        # implemented in v1 — a forward-compatible matcher silently
        # skips them rather than erroring out.
        matches = match_custom_terms(
            "Project Apollo is een codenaam.",
            [_Term("Project Apollo", match_mode="prefix")],
        )
        assert matches == []

    def test_custom_woo_article_is_carried_through(self):
        matches = match_custom_terms(
            "Het bedrijfsgeheim staat in het rapport.",
            [_Term("bedrijfsgeheim", woo_article="5.1.2b")],
        )
        assert len(matches) == 1
        assert matches[0].woo_article == "5.1.2b"
