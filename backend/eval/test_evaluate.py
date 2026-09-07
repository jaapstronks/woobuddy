"""Tests for the judgement calls in `evaluate.py` that are easy to get wrong.

Lenient coverage is the one place where the harness deliberately grades a
partial match as a hit. That is a claim about redaction, not about string
similarity, so it needs to be pinned: too generous and a real leak reads as a
success.

Run from `backend/` (it imports `app.*` for the tussenvoegsel list):

    pytest eval/test_evaluate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate import _lenient_reason, _page_index  # noqa: E402


@pytest.mark.parametrize(
    "truth_type,uncovered,expected",
    [
        # A surname found without its particle leaves nothing identifying.
        ("achternaam", "de", "tussenvoegsel_only"),
        ("volledige_naam", "van der", "tussenvoegsel_only"),
        ("achternaam", "in 't", "tussenvoegsel_only"),
        ("volledige_naam", "de,", "tussenvoegsel_only"),  # punctuation is ignored
        # The postcode is the identifier; the town it sits in is not.
        ("postcode_plaats", "Assen", "place_only"),
        ("postcode_plaats", "Wijk en Aalburg", "place_only"),
        # A whole first name missing is a real partial, not a particle.
        ("volledige_naam", "Sigrid", None),
        ("achternaam", "Wegerif", None),
        # Half a postcode missing is a leak, place-only leniency must not fire.
        ("postcode_plaats", "9401 AC", None),
        # Leniency is scoped to the type that earns it.
        ("adres", "Assen", None),
    ],
)
def test_lenient_reason(truth_type: str, uncovered: str, expected: str | None) -> None:
    assert _lenient_reason(truth_type, uncovered) == expected


def test_lenient_reason_ignores_an_empty_remainder() -> None:
    """No remainder means low coverage came from somewhere else.

    Every word of the value was matched, yet the boxes did not cover it. That
    is a geometry problem worth looking at, so it stays `partial` rather than
    being waved through as a particle.
    """
    assert _lenient_reason("achternaam", "") is None
    assert _lenient_reason("postcode_plaats", "   ") is None


class _FakePayload:
    def __init__(self, texts: list[str]) -> None:
        self.pages = [{"page_number": i + 1, "full_text": t} for i, t in enumerate(texts)]


def test_page_index_matches_the_blank_line_join() -> None:
    """`extraction_from_client_data` joins pages with "\\n\\n"; so does this."""
    payload = _FakePayload(["abc", "de", "fghi"])
    index = _page_index(payload)
    joined = "\n\n".join(p["full_text"] for p in payload.pages)
    assert index == [(0, 3, 1), (5, 7, 2), (9, 13, 3)]
    for start, end, _page in index:
        assert joined[start:end] in ("abc", "de", "fghi")
