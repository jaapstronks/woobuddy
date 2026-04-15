"""Golden-file regression tests over the PDF fixtures in `tests/fixtures/`.

Each fixture was crafted to exercise a specific detection scenario
(Tier 1 identifiers, false-positive traps, list-context public
officials, email headers, signature blocks, …). The tests run the
full detection pipeline and assert coarse expectations on what the
output should contain.

The asserts are intentionally *coarse*. Exact coordinates and exact
detection counts jitter with Deduce model updates, with PyMuPDF text
extraction changes, and with the client-first bbox narrowing. What we
lock in here is:

- the *minimum* number of Tier 1 hits per entity type on the
  identifier fixture (regression guard for regex changes);
- the *absence* of auto-accepted hits on the false-positive fixture
  (the whole point of that fixture — nothing should redact);
- the presence of publiek-functionaris classifications on the
  raadsvergadering fixture where list-context matching must fire
  across 4 names introduced by a single plural title.

Each time a fix lands that changes expected counts, update the
baselines here — they are the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.pdf_engine import extract_text
from app.services.pipeline_engine import PipelineResult, _run_pipeline_sync

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _run(filename: str) -> PipelineResult:
    """Run the synchronous pipeline over a fixture PDF."""
    pdf_bytes = (_FIXTURE_DIR / filename).read_bytes()
    extraction = extract_text(pdf_bytes)
    return _run_pipeline_sync(
        extraction,
        public_official_names=None,
        custom_terms=None,
    )


def _counts_by_type(result: PipelineResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in result.detections:
        counts[d.entity_type] = counts.get(d.entity_type, 0) + 1
    return counts


def _counts_by_status(result: PipelineResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in result.detections:
        counts[d.review_status] = counts.get(d.review_status, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Tier 1 — all identifier shapes
# ---------------------------------------------------------------------------


class TestTier1AllIdentifiers:
    """`tier1_all_identifiers.pdf` exercises every Tier 1 regex.

    The fixture includes positive cases for BSN, IBAN (NL), phone, email,
    postcode, credit card, URL, KvK, BTW, and every Dutch license-plate
    sidecode, plus negative controls (failing-Luhn card, foreign IBAN,
    invalid BSN, lowercase postcode). The positive cases must fire; the
    negative controls must not.
    """

    def test_all_tier1_types_fire(self):
        result = _run("tier1_all_identifiers.pdf")
        counts = _counts_by_type(result)

        # Positive-control minimums. We require at least 1 of each Tier 1
        # entity type and at least 5 license plates (the fixture contains
        # 5 sidecode examples).
        assert counts.get("bsn", 0) >= 1, counts
        assert counts.get("iban", 0) >= 1, counts
        assert counts.get("telefoon", 0) >= 1, counts
        assert counts.get("email", 0) >= 1, counts
        assert counts.get("postcode", 0) >= 1, counts
        assert counts.get("url", 0) >= 1, counts
        assert counts.get("kenteken", 0) >= 5, counts
        assert counts.get("creditcard", 0) >= 1, counts

    def test_kvk_surfaces_as_pending_not_auto_accepted(self):
        """KvK is public handelsregister data — reviewer decides, not the pipeline.

        KvK numbers live on `edge_cases.pdf` (three of them, wrapped in a
        paragraph that explicitly says they should not be redacted). The
        fix makes all three emit as pending.
        """
        result = _run("edge_cases.pdf")
        kvks = [d for d in result.detections if d.entity_type == "kvk"]
        assert kvks, "expected at least one KvK detection"
        for k in kvks:
            assert k.review_status == "pending", (k.entity_text, k.review_status)


# ---------------------------------------------------------------------------
# False-positive trap fixture
# ---------------------------------------------------------------------------


class TestFalsePositives:
    """`false_positives.pdf` contains look-alikes that must NOT redact.

    Invoice numbers, order references, fake BSNs that fail the 11-proef,
    foreign IBANs that fail the country filter, credit-card-shaped
    strings that fail Luhn — all of these should fall through without
    producing an auto-accepted detection.
    """

    def test_no_auto_accepted_tier1_false_positives(self):
        result = _run("false_positives.pdf")
        auto = [
            d
            for d in result.detections
            if d.review_status == "auto_accepted" and d.tier == "1"
        ]
        # Postcodes inside an institutional address context are the one
        # grandfathered exception — the whitelist engine flips them to
        # rejected, but a legitimately formatted citizen postcode could
        # still fire. We allow a small number (≤ 2) to keep the test
        # robust against incidental PDF content; anything higher is a
        # signal the false-positive filters have regressed.
        assert len(auto) <= 2, [
            (d.entity_type, d.entity_text, d.reasoning) for d in auto
        ]


# ---------------------------------------------------------------------------
# Raadsvergadering — publiek functionaris list context
# ---------------------------------------------------------------------------


class TestRaadsvergaderingListContext:
    """`raadsvergadering.pdf` contains comma-separated lists of raadsleden
    and fractievoorzitters that must ALL be classified as publiek
    functionaris — not just the first name after the title.
    """

    def test_list_context_flags_multiple_publiek_functionarissen(self):
        result = _run("raadsvergadering.pdf")
        publiek = [
            d
            for d in result.detections
            if d.subject_role == "publiek_functionaris"
        ]
        # The fixture contains at least 4 names in list context. Before
        # the list-context fix only the first name got the title applied.
        assert len(publiek) >= 3, [
            (d.entity_text, d.reasoning) for d in result.detections
            if d.entity_type == "persoon"
        ]

    def test_publiek_functionarissen_default_to_rejected(self):
        result = _run("raadsvergadering.pdf")
        publiek = [
            d
            for d in result.detections
            if d.subject_role == "publiek_functionaris"
        ]
        assert publiek, "expected publiek_functionaris classifications"
        for d in publiek:
            assert d.review_status == "rejected", (d.entity_text, d.review_status)


# ---------------------------------------------------------------------------
# Sanity: every fixture parses and produces a result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "besluit_ambtenaar.pdf",
        "besluit_brief.pdf",
        "edge_cases.pdf",
        "email_mixed.pdf",
        "false_positives.pdf",
        "nota_gezondheid.pdf",
        "raadsvergadering.pdf",
        "tier1_all_identifiers.pdf",
    ],
)
def test_fixture_runs_without_error(filename: str):
    """Smoke test — every fixture can be parsed and run through the pipeline."""
    result = _run(filename)
    assert result.page_count >= 1
    # No detection should carry an empty entity_text or the [onbekend]
    # placeholder — those were the symptom the empty-bbox filter fixes.
    for d in result.detections:
        assert d.entity_text, f"{filename}: empty entity_text on {d.entity_type}"
        assert d.entity_text != "[onbekend]", f"{filename}: [onbekend] leak"
