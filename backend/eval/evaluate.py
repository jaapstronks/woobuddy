#!/usr/bin/env python3
"""Score WOO Buddy's detection pipeline against the `ontlakt` corpus.

`ontlak.py` refilled 33 published (already-redacted) Woo documents with
fictional Dutch values and wrote down exactly what it put where. This script
runs the real pipeline over those documents and reports two things:

  * **recall** — of every value we planted, did the pipeline find it, find
    half of it, find it and then suppress it, or miss it entirely;
  * **false-positive candidates** — everything the pipeline flagged that we
    did not plant and that does not sit on a zone we deliberately left blank.

The second number needs a caveat, and it is repeated in every report: a
published Woo document legitimately contains names the redactor chose to
leave in — public officials, organisations, the requester's own lawyer. Those
show up here as false positives, and that is the point: the redactor's
decision is our ground truth for "not to be redacted". But redactors miss
things too, so a false positive is a *candidate*, never a verdict.

    ./evaluate.py                       # whole corpus, report into reports/
    ./evaluate.py --only '5_*'          # one document
    ./evaluate.py --baseline reports/baseline.json
    ./evaluate.py --save-baseline

Run it from `backend/` so `app.*` resolves to the checkout under test.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

# Both the sibling helper and the backend package have to be importable
# regardless of where this script is invoked from.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import fitz  # noqa: E402
from pdfio import pages_payload  # noqa: E402, I001
from triage import print_triage, render_triage  # noqa: E402, I001

from app.logging_config import configure_logging  # noqa: E402
from app.services.name_engine import _normalize as _name_token  # noqa: E402
from app.services.name_engine import load_name_lists  # noqa: E402
from app.services.pdf_engine import extraction_from_client_data  # noqa: E402
from app.services.pipeline_engine import _run_pipeline_sync  # noqa: E402

# --------------------------------------------------------------------------
# Tunables — every judgement call in this file lives here
# --------------------------------------------------------------------------

#: A detection counts as covering a truth item when it eats 30% of the truth
#: box, or when half of the detection box sits inside it. Two thresholds
#: because the two failure modes differ: a detector that finds only the
#: surname of a full name fails the first test, and a detector that flags a
#: whole line containing the name fails the second.
TRUTH_OVERLAP_MIN = 0.30
DET_OVERLAP_MIN = 0.50

#: Bounding boxes drift (span resolution, rotated pages, inserted text that
#: does not sit exactly where the ground truth says). Text containment is the
#: fallback; below this length it matches noise.
MIN_TEXT_LEN = 4

#: Fraction of the truth box's width that must be covered to call it `found`
#: rather than `partial`.
FULL_COVERAGE = 0.90

#: How much of a detection has to sit on an unknown zone before we stop
#: holding it against the detector.
UNKNOWN_OVERLAP_MIN = 0.30

#: Statuses that reach the reviewer as a redaction suggestion. `rejected`
#: means the pipeline found the span and then a whitelist or the
#: publiek-functionaris rule engine suppressed it — a separate failure class.
ACTIVE_STATUSES = frozenset({"auto_accepted", "pending", "accepted", "edited"})

#: Which pipeline `entity_type` is a defensible answer for a ground-truth
#: type. Deliberately generous: `email_met_naam` is satisfied by either half,
#: and a postcode found as part of an address still redacts the postcode.
TYPE_COMPAT: dict[str, frozenset[str]] = {
    "volledige_naam": frozenset({"persoon"}),
    "achternaam": frozenset({"persoon"}),
    "voornaam": frozenset({"persoon"}),
    "initialen": frozenset({"persoon"}),
    "functie": frozenset({"persoon"}),
    "email": frozenset({"email"}),
    "email_met_naam": frozenset({"email", "persoon"}),
    "adres": frozenset({"adres"}),
    "postcode": frozenset({"postcode", "adres"}),
    "postcode_plaats": frozenset({"postcode", "adres"}),
    "woonplaats": frozenset({"adres"}),
    "telefoon": frozenset({"telefoon"}),
    "mobiel": frozenset({"telefoon"}),
    "iban": frozenset({"iban"}),
    "bsn": frozenset({"bsn"}),
    "kvk": frozenset({"kvk"}),
    "kenteken": frozenset({"kenteken"}),
    "geboortedatum": frozenset({"geboortedatum"}),
}

#: A `partial` whose uncovered remainder is only these is promoted to `found`
#: and flagged `lenient`. "de Wegerif" found as "Wegerif" leaves nothing
#: identifying on the page, and neither does "9401 AC Assen" found as
#: "9401 AC" — the postcode is the identifier, the place is not. The count is
#: reported separately so nobody reads it as exact coverage.
LENIENT_PLACE_TYPES = frozenset({"postcode_plaats"})


@lru_cache(maxsize=1)
def _tussenvoegsel_tokens() -> frozenset[str]:
    """Every token that can appear inside a Dutch name particle.

    Taken from the detector's own list rather than a copy here, so the harness
    cannot be lenient about a particle the pipeline does not know.
    """
    lists = load_name_lists()
    tokens = set(lists.tussenvoegsels)
    for seq in lists.tussenvoegsel_sequences:
        tokens.update(seq)
    return frozenset(tokens)


def _lenient_reason(truth_type: str, uncovered: str) -> str | None:
    """Why an incomplete match is a full hit for redaction purposes, or None."""
    words = [w for w in re.split(r"[\s<>,;.'\u2019]+", uncovered) if w]
    if not words:
        return None
    if all(_name_token(w) in _tussenvoegsel_tokens() for w in words):
        return "tussenvoegsel_only"
    if truth_type in LENIENT_PLACE_TYPES and not any(c.isdigit() for c in uncovered):
        return "place_only"
    return None


DEFAULT_CORPUS = Path(
    os.environ.get("WOOBUDDY_EVAL_CORPUS") or Path.home() / "Github NW/woobuddy-eval-corpus"
)

FP_CAVEAT = (
    "False positives are **candidates**, not verdicts. A published Woo "
    "document legitimately contains names the redactor left in (public "
    "officials, organisations, the requester's lawyer). Those are exactly "
    "what we want to see here, because the redactor's decision is our ground "
    "truth for 'not to be redacted' — but redactors also miss things, so read "
    "each candidate before believing it."
)

#: Optional file at the corpus root listing documents whose redaction is too
#: poor to serve as a "do not redact" reference. Recall is still scored on
#: them — a planted value is ground truth wherever it sits — but their FP
#: candidates are counted apart and kept out of the tables, the totals and the
#: baseline diff. See "Corpus hygiene" in the README.
CORPUS_CONFIG = "corpus.json"


# --------------------------------------------------------------------------
# Geometry and text helpers
# --------------------------------------------------------------------------


def norm(s: str) -> str:
    """Lowercase, strip diacritics, keep only [a-z0-9@.]."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9@.]+", "", stripped)


def _rect(bbox: Any) -> tuple[float, float, float, float]:
    if isinstance(bbox, dict):
        return (float(bbox["x0"]), float(bbox["y0"]), float(bbox["x1"]), float(bbox["y1"]))
    x0, y0, x1, y1 = bbox
    return (float(x0), float(y0), float(x1), float(y1))


def _area(r: tuple[float, float, float, float]) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _intersection(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def _union_width(intervals: list[tuple[float, float]], lo: float, hi: float) -> float:
    """Total width covered by `intervals`, clipped to [lo, hi]."""
    clipped = sorted((max(lo, a), min(hi, b)) for a, b in intervals if min(hi, b) > max(lo, a))
    total, cur_end = 0.0, lo
    for a, b in clipped:
        if a > cur_end:
            total += b - a
            cur_end = b
        elif b > cur_end:
            total += b - cur_end
            cur_end = b
    return total


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass
class DetectionRecord:
    """One pipeline detection, flattened for reporting."""

    index: int
    entity_text: str
    entity_type: str
    tier: str
    confidence: float
    review_status: str
    source: str
    reasoning: str
    woo_article: str | None
    start_char: int | None
    end_char: int | None
    bboxes: list[dict[str, Any]]
    context: str

    @property
    def pages(self) -> set[int]:
        return {int(b["page"]) for b in self.bboxes}


@dataclass
class TruthResult:
    """Verdict on one planted value."""

    doc: str
    page: int
    type: str
    value: str
    slot_kind: str
    slot_type: str | None
    in_wordlist: bool | None
    outcome: str  # found | partial | rejected | missed
    #: `found` only because the uncovered remainder was a tussenvoegsel or a
    #: place name; `lenient_reason` says which. Coverage below still reports
    #: what was actually covered.
    lenient: bool
    lenient_reason: str
    coverage: float
    match_mode: str | None  # bbox | text | None
    type_ok: bool | None
    matched: list[dict[str, Any]] = field(default_factory=list)
    uncovered: str = ""
    context: str = ""


@dataclass
class FalsePositive:
    """A detection we did not plant and cannot excuse."""

    doc: str
    page: int | None
    entity_text: str
    entity_type: str
    tier: str
    source: str
    review_status: str
    confidence: float
    severity: str  # hard | soft
    context: str


def _page_index(payload: Any) -> list[tuple[int, int, int]]:
    """`(start, end, page_number)` of each page inside the joined full_text.

    `extraction_from_client_data` joins page texts with a blank line, so the
    same arithmetic here turns a detection's `start_char` back into a page and
    lets a planted character range be compared against it.
    """
    index: list[tuple[int, int, int]] = []
    cursor = 0
    for page in payload.pages:
        length = len(page["full_text"])
        index.append((cursor, cursor + length, int(page["page_number"])))
        cursor += length + 2  # "\n\n"
    return index


@dataclass
class NoBBox:
    """A detection the pipeline produced without a bounding box.

    Nothing is drawn on the page for these, so the reviewer sees a suggestion
    they cannot place. `region` says whether the span sits on text this fixture
    planted — where a span-resolution failure is partly our own doing — or on
    the document's own text, where it is a plain bug.
    """

    doc: str
    page: int | None
    entity_text: str
    entity_type: str
    tier: str
    source: str
    review_status: str
    start_char: int | None
    end_char: int | None
    region: str  # planted | original | unknown
    context: str


@dataclass
class Suppressed:
    """A detection the rule engine found and then threw away."""

    doc: str
    entity_text: str
    entity_type: str
    source: str
    reasoning: str


@dataclass
class DocReport:
    name: str
    pages: int
    pages_scored: int
    scanned_pages: list[int]
    truth: int = 0
    found: int = 0
    partial: int = 0
    rejected: int = 0
    missed: int = 0
    fp_hard: int = 0
    fp_soft: int = 0
    suppressed: int = 0
    unknown_zones: int = 0
    on_unknown_zone: int = 0
    detections: int = 0
    detections_without_bbox: int = 0
    detections_without_bbox_planted: int = 0
    detections_without_bbox_original: int = 0
    detections_without_bbox_items: list[dict[str, Any]] = field(default_factory=list)
    lenient: int = 0
    #: Text items moved out of the tail of the content stream and back into
    #: reading order. Should track the number of planted values.
    relocated: int = 0
    #: False, and `fp_excluded` carries the count, when this document is not a
    #: usable "do not redact" reference (see CORPUS_CONFIG).
    fp_scored: bool = True
    fp_excluded: int = 0
    fp_excluded_reason: str = ""


# --------------------------------------------------------------------------
# Running one document
# --------------------------------------------------------------------------


def _detection_context(full_text: str, det: Any, width: int = 60) -> str:
    if det.start_char is None or det.end_char is None:
        return ""
    lo = max(0, det.start_char - width)
    hi = min(len(full_text), det.end_char + width)
    return _collapse(full_text[lo:hi])


def _truth_context(doc: Any, page_no: int, bbox: tuple[float, float, float, float]) -> str:
    """The line(s) around a planted value, read straight off the page.

    A missed value needs its surroundings to be diagnosable — "Geachte
    <surname>," fails for a different reason than a surname in a table cell.
    """
    try:
        page = doc[page_no - 1]
    except IndexError:  # pragma: no cover - malformed ground truth
        return ""
    clip = fitz.Rect(bbox[0] - 150, bbox[1] - 4, bbox[2] + 150, bbox[3] + 4)
    clip = clip & page.rect
    if clip.is_empty:
        return ""
    return _collapse(page.get_text("text", clip=clip))


def _match_truth(
    item: dict[str, Any], records: list[DetectionRecord]
) -> list[tuple[DetectionRecord, str]]:
    """Every detection that plausibly covers this planted value."""
    page = int(item["page"])
    truth_box = _rect(item["bbox"])
    truth_area = _area(truth_box)
    tv = norm(item["value"])
    out: list[tuple[DetectionRecord, str]] = []

    for rec in records:
        mode: str | None = None
        for b in rec.bboxes:
            if int(b["page"]) != page:
                continue
            det_box = _rect(b)
            inter = _intersection(truth_box, det_box)
            if inter <= 0:
                continue
            det_area = _area(det_box)
            if (truth_area and inter / truth_area >= TRUTH_OVERLAP_MIN) or (
                det_area and inter / det_area >= DET_OVERLAP_MIN
            ):
                mode = "bbox"
                break
        if mode is None:
            # Bounding boxes drift. A detection sitting on the same page whose
            # text is contained in the planted value (or contains it) is the
            # same finding by another route.
            on_page = page in rec.pages or not rec.bboxes
            nt = norm(rec.entity_text)
            if (
                on_page
                and len(nt) >= MIN_TEXT_LEN
                and len(tv) >= MIN_TEXT_LEN
                and (nt in tv or tv in nt)
            ):
                mode = "text"
        if mode is not None:
            out.append((rec, mode))
    return out


def _coverage(item: dict[str, Any], matches: list[tuple[DetectionRecord, str]]) -> float:
    """Fraction of the planted value the matching detections actually cover."""
    truth_box = _rect(item["bbox"])
    page = int(item["page"])
    intervals: list[tuple[float, float]] = []
    for rec, _mode in matches:
        for b in rec.bboxes:
            if int(b["page"]) != page:
                continue
            det_box = _rect(b)
            # Ignore boxes on other lines: they cover width without covering
            # the value.
            if min(truth_box[3], det_box[3]) - max(truth_box[1], det_box[1]) <= 0:
                continue
            intervals.append((det_box[0], det_box[2]))
    width = truth_box[2] - truth_box[0]
    bbox_cov = _union_width(intervals, truth_box[0], truth_box[2]) / width if width > 0 else 0.0

    tv = norm(item["value"])
    text_cov = 0.0
    if tv:
        mark = bytearray(len(tv))
        for rec, _mode in matches:
            nt = norm(rec.entity_text)
            if len(nt) < MIN_TEXT_LEN:
                continue
            if tv in nt:
                text_cov = 1.0
                break
            start = tv.find(nt)
            while start >= 0:
                for k in range(start, start + len(nt)):
                    mark[k] = 1
                start = tv.find(nt, start + 1)
        text_cov = max(text_cov, sum(mark) / len(tv))

    return max(bbox_cov, text_cov)


def _uncovered_parts(value: str, matches: list[tuple[DetectionRecord, str]]) -> str:
    """Which words of the planted value no detection touched."""
    seen = " ".join(norm(rec.entity_text) for rec, _ in matches)
    missing = [w for w in re.split(r"[\s<>,;]+", value) if w and norm(w) not in seen]
    return " ".join(missing)


def _on_unknown_zone(rec: DetectionRecord, zones: list[dict[str, Any]]) -> bool:
    for b in rec.bboxes:
        det_box = _rect(b)
        det_area = _area(det_box)
        if det_area <= 0:
            continue
        for z in zones:
            if int(z["page"]) != int(b["page"]):
                continue
            if _intersection(det_box, _rect(z["bbox"])) / det_area >= UNKNOWN_OVERLAP_MIN:
                return True
    return False


@dataclass
class DocOutcome:
    report: DocReport
    truth_results: list[TruthResult]
    false_positives: list[FalsePositive]
    suppressed: list[Suppressed]
    no_bbox: list[NoBBox] = field(default_factory=list)


def evaluate_document(
    pdf: Path,
    truth_path: Path,
    *,
    extractor: str = "pdfjs",
    fp_excluded_reason: str = "",
) -> DocOutcome:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = truth.get("detections", [])
    zones: list[dict[str, Any]] = truth.get("unknown_zones", [])

    # `planted` is what lets `pages_payload` undo the overlay ordering: without
    # it every value sits at the end of its page and every context rule in the
    # pipeline is scored against a document that does not exist.
    payload = pages_payload(pdf, extractor=extractor, planted=items)
    extraction = extraction_from_client_data(payload.pages)
    result = _run_pipeline_sync(extraction, None, None)

    records = [
        DetectionRecord(
            index=i,
            entity_text=d.entity_text,
            entity_type=d.entity_type,
            tier=d.tier,
            confidence=d.confidence,
            review_status=d.review_status,
            source=d.source,
            reasoning=d.reasoning,
            woo_article=d.woo_article,
            start_char=d.start_char,
            end_char=d.end_char,
            bboxes=[dict(b) for b in d.bounding_boxes],
            context=_detection_context(extraction.full_text, d),
        )
        for i, d in enumerate(result.detections)
    ]

    report = DocReport(
        name=pdf.name,
        pages=payload.page_count,
        pages_scored=len(payload.pages),
        scanned_pages=payload.scanned_pages,
        truth=len(items),
        unknown_zones=len(zones),
        detections=len(records),
        detections_without_bbox=sum(1 for r in records if not r.bboxes),
        relocated=payload.relocated,
        fp_scored=not fp_excluded_reason,
        fp_excluded_reason=fp_excluded_reason,
    )

    doc = fitz.open(pdf)
    try:
        truth_results: list[TruthResult] = []
        claimed: set[int] = set()

        for item in items:
            matches = _match_truth(item, records)
            claimed.update(rec.index for rec, _ in matches)
            active = [(r, m) for r, m in matches if r.review_status in ACTIVE_STATUSES]
            used = active or matches
            coverage = _coverage(item, used) if used else 0.0

            uncovered = _uncovered_parts(item["value"], used)
            lenient, lenient_reason = False, ""
            if not matches:
                outcome = "missed"
            elif not active:
                outcome = "rejected"
            elif coverage >= FULL_COVERAGE:
                outcome = "found"
            else:
                outcome = "partial"
                reason = _lenient_reason(item["type"], uncovered)
                if reason:
                    # Not a leak: what is left uncovered identifies nobody.
                    outcome, lenient, lenient_reason = "found", True, reason

            compat = TYPE_COMPAT.get(item["type"], frozenset())
            type_ok = any(r.entity_type in compat for r, _ in used) if used else None
            mode = None
            if used:
                mode = "bbox" if any(m == "bbox" for _, m in used) else "text"

            context = ""
            if outcome != "found":
                context = _truth_context(doc, int(item["page"]), _rect(item["bbox"]))
                extra = _collapse(item.get("context") or "")
                if extra:
                    context = f"{context}   [slot: {extra}]" if context else f"[slot: {extra}]"

            truth_results.append(
                TruthResult(
                    doc=pdf.name,
                    page=int(item["page"]),
                    type=item["type"],
                    value=item["value"],
                    slot_kind=item.get("slot_kind", ""),
                    slot_type=item.get("slot_type"),
                    in_wordlist=item.get("in_wordlist"),
                    outcome=outcome,
                    lenient=lenient,
                    lenient_reason=lenient_reason,
                    coverage=round(coverage, 3),
                    match_mode=mode,
                    type_ok=type_ok,
                    matched=[
                        {
                            "entity_text": r.entity_text,
                            "entity_type": r.entity_type,
                            "review_status": r.review_status,
                            "source": r.source,
                            "reasoning": r.reasoning,
                            "match_mode": m,
                        }
                        for r, m in matches
                    ],
                    uncovered=uncovered,
                    context=context,
                )
            )
            setattr(report, outcome, getattr(report, outcome) + 1)
            report.lenient += lenient
    finally:
        doc.close()

    # Where each page's text sits in the joined document text, and which of
    # those characters we planted ourselves.
    page_index = _page_index(payload)
    page_base = {pno: start for start, _end, pno in page_index}
    planted_spans = [
        (page_base[pno] + a, page_base[pno] + b)
        for pno, ranges in payload.relocated_ranges.items()
        if pno in page_base
        for a, b in ranges
    ]

    def _page_of(pos: int | None) -> int | None:
        if pos is None:
            return None
        return next((pno for start, end, pno in page_index if start <= pos <= end), None)

    def _region(rec: DetectionRecord) -> str:
        if rec.start_char is None or rec.end_char is None:
            return "unknown"
        return (
            "planted"
            if any(rec.start_char < b and a < rec.end_char for a, b in planted_spans)
            else "original"
        )

    # Every bbox-less detection, including ones that matched a truth item by
    # text: the reviewer cannot place any of them.
    no_bbox = [
        NoBBox(
            doc=pdf.name,
            page=_page_of(rec.start_char),
            entity_text=rec.entity_text,
            entity_type=rec.entity_type,
            tier=rec.tier,
            source=rec.source,
            review_status=rec.review_status,
            # The pipeline hands back numpy ints from some detectors, which
            # `json.dumps` refuses. Nothing downstream needs the subclass.
            start_char=None if rec.start_char is None else int(rec.start_char),
            end_char=None if rec.end_char is None else int(rec.end_char),
            region=_region(rec),
            context=rec.context,
        )
        for rec in records
        if not rec.bboxes
    ]

    false_positives: list[FalsePositive] = []
    suppressed: list[Suppressed] = []
    for rec in records:
        if rec.index in claimed:
            continue
        if rec.review_status == "rejected":
            suppressed.append(
                Suppressed(
                    doc=pdf.name,
                    entity_text=rec.entity_text,
                    entity_type=rec.entity_type,
                    source=rec.source,
                    reasoning=rec.reasoning,
                )
            )
            continue
        if not rec.bboxes:
            # No box means nothing is drawn on the page; it cannot be checked
            # against an unknown zone either. Counted and listed above, but not
            # charged as a false positive.
            continue
        if _on_unknown_zone(rec, zones):
            report.on_unknown_zone += 1
            continue
        severity = "hard" if rec.review_status == "auto_accepted" else "soft"
        false_positives.append(
            FalsePositive(
                doc=pdf.name,
                page=min(rec.pages) if rec.bboxes else None,
                entity_text=rec.entity_text,
                entity_type=rec.entity_type,
                tier=rec.tier,
                source=rec.source,
                review_status=rec.review_status,
                confidence=rec.confidence,
                severity=severity,
                context=rec.context,
            )
        )

    report.suppressed = len(suppressed)
    report.detections_without_bbox_items = [asdict(n) for n in no_bbox]
    report.detections_without_bbox_planted = sum(1 for n in no_bbox if n.region == "planted")
    report.detections_without_bbox_original = sum(1 for n in no_bbox if n.region != "planted")
    if not report.fp_scored:
        # The redactor left personal data standing here, so "not redacted" is
        # not a decision we can score against. Recall above still counts: a
        # planted value is ground truth wherever it sits.
        report.fp_excluded = len(false_positives)
        false_positives = []
    report.fp_hard = sum(1 for f in false_positives if f.severity == "hard")
    report.fp_soft = sum(1 for f in false_positives if f.severity == "soft")
    return DocOutcome(report, truth_results, false_positives, suppressed, no_bbox)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _git_info(repo: Path) -> dict[str, str]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    return {
        "sha": run("rev-parse", "--short=7", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": "yes" if run("status", "--porcelain") else "no",
    }


def _rate(part: int, total: int) -> str:
    return f"{100 * part / total:5.1f}%" if total else "    - "


def _bucket_table(title: str, buckets: dict[str, Counter[str]], key_label: str) -> list[str]:
    lines = [
        f"### {title}",
        "",
        f"| {key_label} | truth | found | (lenient) | partial | rejected | missed | recall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in sorted(buckets, key=lambda k: -buckets[k]["truth"]):
        c = buckets[key]
        lines.append(
            f"| {key} | {c['truth']} | {c['found']} | {c['lenient']} | {c['partial']} | "
            f"{c['rejected']} | {c['missed']} | {_rate(c['found'], c['truth'])} |"
        )
    lines.append("")
    return lines


def build_report(
    outcomes: list[DocOutcome],
    corpus: Path,
    repo: Path,
    extractor: str = "pdfjs",
) -> dict[str, Any]:
    truth_results = [t for o in outcomes for t in o.truth_results]
    fps = [f for o in outcomes for f in o.false_positives]
    supp = [s for o in outcomes for s in o.suppressed]
    nobox = [n for o in outcomes for n in o.no_bbox]
    reports = [o.report for o in outcomes]

    per_type: dict[str, Counter[str]] = defaultdict(Counter)
    per_wordlist: dict[str, Counter[str]] = defaultdict(Counter)
    per_slot_kind: dict[str, Counter[str]] = defaultdict(Counter)
    for t in truth_results:
        for bucket, key in (
            (per_type, t.type),
            (per_slot_kind, t.slot_kind or "onbekend"),
        ):
            bucket[key]["truth"] += 1
            bucket[key][t.outcome] += 1
            bucket[key]["lenient"] += t.lenient
        if t.in_wordlist is not None:
            key = "in wordlist" if t.in_wordlist else "outside wordlist"
            per_wordlist[key]["truth"] += 1
            per_wordlist[key][t.outcome] += 1
            per_wordlist[key]["lenient"] += t.lenient

    summary = {
        "documents": len(reports),
        "pages": sum(r.pages for r in reports),
        "pages_scored": sum(r.pages_scored for r in reports),
        "scanned_pages_skipped": sum(len(r.scanned_pages) for r in reports),
        "truth_items": len(truth_results),
        "unknown_zones": sum(r.unknown_zones for r in reports),
        "found": sum(1 for t in truth_results if t.outcome == "found"),
        "lenient": sum(1 for t in truth_results if t.lenient),
        "partial": sum(1 for t in truth_results if t.outcome == "partial"),
        "rejected": sum(1 for t in truth_results if t.outcome == "rejected"),
        "missed": sum(1 for t in truth_results if t.outcome == "missed"),
        "type_mismatches": sum(1 for t in truth_results if t.type_ok is False),
        "matches_by_bbox": sum(1 for t in truth_results if t.match_mode == "bbox"),
        "matches_by_text": sum(1 for t in truth_results if t.match_mode == "text"),
        "detections_total": sum(r.detections for r in reports),
        "detections_without_bbox": sum(r.detections_without_bbox for r in reports),
        "detections_without_bbox_planted": sum(r.detections_without_bbox_planted for r in reports),
        "detections_without_bbox_original": sum(
            r.detections_without_bbox_original for r in reports
        ),
        "detections_on_unknown_zone": sum(r.on_unknown_zone for r in reports),
        "fp_hard": sum(r.fp_hard for r in reports),
        "fp_soft": sum(r.fp_soft for r in reports),
        "fp_excluded": sum(r.fp_excluded for r in reports),
        "fp_excluded_documents": sum(1 for r in reports if not r.fp_scored),
        "suppressed": len(supp),
        "relocated": sum(r.relocated for r in reports),
    }

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "corpus": str(corpus),
        "extractor": extractor,
        "backend": _git_info(repo),
        "thresholds": {
            "truth_overlap_min": TRUTH_OVERLAP_MIN,
            "det_overlap_min": DET_OVERLAP_MIN,
            "full_coverage": FULL_COVERAGE,
            "min_text_len": MIN_TEXT_LEN,
            "unknown_overlap_min": UNKNOWN_OVERLAP_MIN,
        },
        "summary": summary,
        "per_type": {k: dict(v) for k, v in per_type.items()},
        "per_wordlist": {k: dict(v) for k, v in per_wordlist.items()},
        "per_slot_kind": {k: dict(v) for k, v in per_slot_kind.items()},
        "documents": [asdict(r) for r in reports],
        "truth_results": [asdict(t) for t in truth_results],
        "false_positives": [asdict(f) for f in fps],
        "suppressed": [asdict(s) for s in supp],
        "detections_without_bbox_items": [asdict(n) for n in nobox],
    }


def _fp_groups(fps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for f in fps:
        key = norm(f["entity_text"]) or f["entity_text"].lower()
        g = groups.setdefault(
            key,
            {
                "text": f["entity_text"],
                "count": 0,
                "hard": 0,
                "types": Counter(),
                "sources": Counter(),
                "statuses": Counter(),
                "docs": set(),
                "context": f["context"],
            },
        )
        g["count"] += 1
        g["hard"] += f["severity"] == "hard"
        g["types"][f["entity_type"]] += 1
        g["sources"][f["source"]] += 1
        g["statuses"][f["review_status"]] += 1
        g["docs"].add(f["doc"])
        if not g["context"]:
            g["context"] = f["context"]
    ordered = sorted(groups.values(), key=lambda g: (0 if g["hard"] else 1, -g["count"], g["text"]))
    return ordered


def render_markdown(data: dict[str, Any]) -> str:
    s = data["summary"]
    g = data["backend"]
    out: list[str] = []
    out.append("# WOO Buddy detection evaluation")
    out.append("")
    out.append(f"- **Run**: {data['generated_at']}")
    out.append(
        f"- **Backend under test**: `{g['branch']}` @ `{g['sha']}`"
        f" (working tree dirty: {g['dirty']})"
    )
    out.append(f"- **Corpus**: `{data['corpus']}`")
    out.append(
        f"- **Corpus stats**: {s['documents']} documents, {s['pages']} pages "
        f"({s['pages_scored']} scored, {s['scanned_pages_skipped']} scanned pages "
        f"skipped), {s['truth_items']} planted values, {s['unknown_zones']} unknown zones"
    )
    out.append(
        f"- **Extraction**: `{data.get('extractor', '?')}`, "
        f"{s.get('relocated', 0)} text items relocated into reading order"
    )
    out.append(
        f"- **Matching**: {s['matches_by_bbox']} truth items matched by bounding box, "
        f"{s['matches_by_text']} by text fallback"
    )
    if s.get("fp_excluded_documents"):
        out.append(
            f"- **FP scoring**: {s['fp_excluded_documents']} document(s) excluded, "
            f"hiding {s['fp_excluded']} candidate(s) — see below"
        )
    out.append("")
    out.append(f"> {FP_CAVEAT}")
    out.append("")
    out.append("## Headline")
    out.append("")
    out.append("| | count | share |")
    out.append("|---|---:|---:|")
    for label, key in (
        ("found", "found"),
        ("of which lenient (particle / place only)", "lenient"),
        ("partial", "partial"),
        ("rejected (found, then suppressed)", "rejected"),
        ("missed", "missed"),
    ):
        out.append(f"| {label} | {s[key]} | {_rate(s[key], s['truth_items'])} |")
    out.append(f"| **truth items** | **{s['truth_items']}** | |")
    out.append("")
    out.append(
        f"Detections: {s['detections_total']} total, "
        f"{s['detections_on_unknown_zone']} on an unknown zone (excused), "
        f"{s['detections_without_bbox']} without a bounding box (not charged), "
        f"{s['fp_hard']} hard FP candidates, {s['fp_soft']} soft, "
        f"{s['suppressed']} suppressed by a rule. "
        f"Type mismatches among matched items: {s['type_mismatches']}."
    )
    out.append("")

    out.append("## Recall")
    out.append("")
    out += _bucket_table(
        "Per truth type", {k: Counter(v) for k, v in data["per_type"].items()}, "type"
    )
    out += _bucket_table(
        "Per wordlist membership",
        {k: Counter(v) for k, v in data["per_wordlist"].items()},
        "names",
    )
    out += _bucket_table(
        "Per slot kind",
        {k: Counter(v) for k, v in data["per_slot_kind"].items()},
        "slot kind",
    )

    out.append("## False positives")
    out.append("")
    out.append(f"{FP_CAVEAT}")
    out.append("")
    excluded = [d for d in data["documents"] if not d.get("fp_scored", True)]
    if excluded:
        out.append("### Excluded from FP scoring")
        out.append("")
        out.append(
            "A document is only a false-positive reference if it was actually "
            "redacted to current Woo practice. These were not, so their "
            "candidates are counted here and left out of every table, total "
            "and baseline diff below. Recall is still scored on them."
        )
        out.append("")
        out.append("| document | candidates | why |")
        out.append("|---|---:|---|")
        for d in sorted(excluded, key=lambda d: -d["fp_excluded"]):
            out.append(f"| {d['name']} | {d['fp_excluded']} | {d['fp_excluded_reason']} |")
        out.append("")
    fps = data["false_positives"]
    combo: Counter[tuple[str, str, str]] = Counter(
        (f["severity"], f["entity_type"], f["source"]) for f in fps
    )
    out.append("### By severity, entity type and source")
    out.append("")
    out.append("| severity | entity_type | source | count |")
    out.append("|---|---|---|---:|")
    for (sev, typ, src), n in sorted(combo.items(), key=lambda kv: (kv[0][0], -kv[1])):
        out.append(f"| {sev} | {typ} | {src} | {n} |")
    out.append("")

    out.append("### Per document")
    out.append("")
    out.append("| document | hard | soft |")
    out.append("|---|---:|---:|")
    for d in sorted(data["documents"], key=lambda d: -(d["fp_hard"] + d["fp_soft"])):
        if d["fp_hard"] or d["fp_soft"]:
            out.append(f"| {d['name']} | {d['fp_hard']} | {d['fp_soft']} |")
    out.append("")

    out.append("### Candidates, grouped by text")
    out.append("")
    out.append("| count | hard | text | entity_type | source | status | docs | example context |")
    out.append("|---:|---:|---|---|---|---|---:|---|")
    for grp in _fp_groups(fps):
        types = ", ".join(sorted(grp["types"]))
        sources = ", ".join(sorted(grp["sources"]))
        statuses = ", ".join(sorted(grp["statuses"]))
        ctx = grp["context"].replace("|", "\\|")[:160]
        text = grp["text"].replace("|", "\\|")
        out.append(
            f"| {grp['count']} | {grp['hard']} | `{text}` | {types} | {sources} | "
            f"{statuses} | {len(grp['docs'])} | {ctx} |"
        )
    out.append("")

    out.append("### Detections without a bounding box")
    out.append("")
    nobox = data.get("detections_without_bbox_items") or []
    if not nobox:
        out.append("_none_")
        out.append("")
    else:
        planted = sum(1 for n in nobox if n["region"] == "planted")
        out.append(
            f"{len(nobox)} detections came back with no bounding box, so nothing "
            f"is drawn on the page and the reviewer gets a suggestion they "
            f"cannot place. {len(nobox) - planted} sit on the document's own "
            f"text — a span-resolution bug — and {planted} on text this fixture "
            f"planted, where the fixture shares the blame."
        )
        out.append("")
        out.append("| count | region | text | entity_type | source | docs | example context |")
        out.append("|---:|---|---|---|---|---:|---|")
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for n in nobox:
            key = (norm(n["entity_text"]) or n["entity_text"].lower(), n["region"])
            g = groups.setdefault(
                key,
                {
                    "text": n["entity_text"],
                    "region": n["region"],
                    "count": 0,
                    "types": Counter(),
                    "sources": Counter(),
                    "docs": set(),
                    "context": n["context"],
                },
            )
            g["count"] += 1
            g["types"][n["entity_type"]] += 1
            g["sources"][n["source"]] += 1
            g["docs"].add(n["doc"])
            if not g["context"]:
                g["context"] = n["context"]
        for g in sorted(
            groups.values(), key=lambda g: (g["region"] != "original", -g["count"], g["text"])
        ):
            ctx = g["context"].replace("|", "\\|")[:120]
            text = g["text"].replace("|", "\\|")[:60]
            out.append(
                f"| {g['count']} | {g['region']} | `{text}` | "
                f"{', '.join(sorted(g['types']))} | {', '.join(sorted(g['sources']))} | "
                f"{len(g['docs'])} | {ctx} |"
            )
        out.append("")

    out.append("### Suppressed by a rule (informational)")
    out.append("")
    supp_by_source: Counter[str] = Counter(x["source"] for x in data["suppressed"])
    out.append("| source | count |")
    out.append("|---|---:|")
    for src, n in supp_by_source.most_common():
        out.append(f"| {src} | {n} |")
    out.append("")

    for label, outcome in (
        ("Missed", "missed"),
        ("Partial", "partial"),
        ("Rejected (found, then suppressed)", "rejected"),
    ):
        rows = [t for t in data["truth_results"] if t["outcome"] == outcome]
        out.append(f"## {label} ({len(rows)})")
        out.append("")
        if not rows:
            out.append("_none_")
            out.append("")
            continue
        for t in rows:
            out.append(
                f"- **{t['type']}** `{t['value']}` — {t['doc']} p.{t['page']} "
                f"(slot: {t['slot_kind']}, wordlist: {t['in_wordlist']}, "
                f"coverage {t['coverage']:.2f})"
            )
            if t["uncovered"]:
                out.append(f"  - uncovered: `{t['uncovered']}`")
            for m in t["matched"]:
                out.append(
                    f"  - matched by: `{m['entity_text']}` ({m['entity_type']}, "
                    f"{m['review_status']}, source={m['source']}, via {m['match_mode']}) "
                    f"— {m['reasoning']}"
                )
            if t["context"]:
                out.append(f"  - context: {t['context'][:300]}")
        out.append("")

    out.append("## Per document")
    out.append("")
    out.append(
        "| document | truth | found | partial | rejected | missed | FP hard | FP soft "
        "| suppressed | pages | skipped |"
    )
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for d in data["documents"]:
        fp_hard = str(d["fp_hard"])
        fp_soft = str(d["fp_soft"])
        if not d.get("fp_scored", True):
            fp_hard, fp_soft = "-", f"_{d['fp_excluded']} excl._"
        out.append(
            f"| {d['name']} | {d['truth']} | {d['found']} | {d['partial']} | "
            f"{d['rejected']} | {d['missed']} | {fp_hard} | {fp_soft} | "
            f"{d['suppressed']} | {d['pages']} | {len(d['scanned_pages'])} |"
        )
    out.append("")
    # Last, because it is the section you read after the numbers: what the
    # errors have in common and which brief each cause belongs to.
    out += render_triage(data)
    return "\n".join(out)


# --------------------------------------------------------------------------
# Baseline comparison
# --------------------------------------------------------------------------


def _truth_key(t: dict[str, Any]) -> tuple[str, int, str]:
    return (t["doc"], int(t["page"]), t["value"])


def _fp_key(f: dict[str, Any]) -> tuple[str, int | None, str]:
    return (f["doc"], f["page"], norm(f["entity_text"]))


def compare_to_baseline(data: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    # A `--only` run must not read as "1200 false positives disappeared".
    # Restrict the comparison to documents both runs actually looked at.
    shared = {d["name"] for d in data["documents"]} & {
        d["name"] for d in baseline.get("documents", [])
    }

    def keep(row: dict[str, Any]) -> bool:
        return row["doc"] in shared

    old_truth = {_truth_key(t): t for t in baseline.get("truth_results", []) if keep(t)}
    new_truth = {_truth_key(t): t for t in data["truth_results"] if keep(t)}
    old_fp = {_fp_key(f): f for f in baseline.get("false_positives", []) if keep(f)}
    new_fp = {_fp_key(f): f for f in data["false_positives"] if keep(f)}

    def moved(to: str) -> list[dict[str, Any]]:
        return [
            t
            for k, t in new_truth.items()
            if t["outcome"] == to and k in old_truth and old_truth[k]["outcome"] != to
        ]

    newly_found = moved("found")
    newly_missed = moved("missed")
    newly_rejected = moved("rejected")
    gone_fp = [f for k, f in old_fp.items() if k not in new_fp]
    new_fps = [f for k, f in new_fp.items() if k not in old_fp]

    ob, nb = baseline.get("summary", {}), data["summary"]
    lines = ["## Compared to baseline", ""]
    lines.append(
        f"Baseline: `{baseline.get('backend', {}).get('branch', '?')}` @ "
        f"`{baseline.get('backend', {}).get('sha', '?')}` "
        f"({baseline.get('generated_at', '?')})"
    )
    lines.append("")
    lines.append(
        f"Totals below are whole-run figures; the item lists cover the "
        f"{len(shared)} document(s) both runs scored."
    )
    lines.append("")
    lines.append("| metric | baseline | now | delta |")
    lines.append("|---|---:|---:|---:|")
    for key in ("found", "partial", "rejected", "missed", "fp_hard", "fp_soft", "suppressed"):
        a, b = ob.get(key, 0), nb.get(key, 0)
        lines.append(f"| {key} | {a} | {b} | {b - a:+d} |")
    lines.append("")
    lines.append(
        f"Truth items newly found: {len(newly_found)}; newly missed: "
        f"{len(newly_missed)}; newly rejected: {len(newly_rejected)}. "
        f"FP candidates new: {len(new_fps)}; gone: {len(gone_fp)}."
    )
    lines.append("")
    for label, rows in (
        ("Newly found", newly_found),
        ("Newly missed", newly_missed),
        ("Newly rejected", newly_rejected),
    ):
        if rows:
            lines.append(f"### {label} ({len(rows)})")
            lines.append("")
            for t in rows:
                lines.append(f"- **{t['type']}** `{t['value']}` — {t['doc']} p.{t['page']}")
            lines.append("")
    for label, rows in (("New FP candidates", new_fps), ("FP candidates gone", gone_fp)):
        if rows:
            lines.append(f"### {label} ({len(rows)})")
            lines.append("")
            for f in rows[:200]:
                lines.append(
                    f"- [{f['severity']}] `{f['entity_text']}` ({f['entity_type']}, "
                    f"{f['source']}) — {f['doc']} p.{f['page']}"
                )
            if len(rows) > 200:
                lines.append(f"- … and {len(rows) - 200} more (see the JSON)")
            lines.append("")
    return lines


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def print_summary(data: dict[str, Any]) -> None:
    s = data["summary"]
    g = data["backend"]
    print()
    print(f"backend {g['branch']} @ {g['sha']} (dirty: {g['dirty']})")
    print(
        f"corpus  {s['documents']} docs, {s['pages']} pages "
        f"({s['scanned_pages_skipped']} scanned skipped), "
        f"{s['truth_items']} planted values, {s['unknown_zones']} unknown zones"
    )
    print(
        f"extract {data.get('extractor', '?')}, "
        f"{s.get('relocated', 0)} items relocated into reading order"
    )
    print()
    print("--- recall ---")
    for label in ("found", "partial", "rejected", "missed"):
        print(f"  {label:<10} {s[label]:4d}  {_rate(s[label], s['truth_items'])}")
    print(f"  {'(lenient)':<10} {s.get('lenient', 0):4d}  particle- or place-only remainder")
    print()
    print("--- recall per type ---")
    for typ, c in sorted(data["per_type"].items(), key=lambda kv: -kv[1]["truth"]):
        print(
            f"  {typ:<18} {c.get('found', 0):3d}/{c['truth']:<3d} "
            f"{_rate(c.get('found', 0), c['truth'])}  "
            f"(partial {c.get('partial', 0)}, rejected {c.get('rejected', 0)}, "
            f"missed {c.get('missed', 0)})"
        )
    if data["per_wordlist"]:
        print()
        print("--- names: wordlist vs outside ---")
        for key, c in sorted(data["per_wordlist"].items()):
            print(
                f"  {key:<20} {c.get('found', 0):3d}/{c['truth']:<3d} "
                f"{_rate(c.get('found', 0), c['truth'])}"
            )
    print()
    print("--- false positives (candidates, not verdicts) ---")
    print(f"  hard (auto-redacted)  {s['fp_hard']}")
    print(f"  soft (suggested)      {s['fp_soft']}")
    print(f"  suppressed by a rule  {s['suppressed']}")
    print(f"  on an unknown zone    {s['detections_on_unknown_zone']} (excused)")
    print(
        f"  without a bounding box {s['detections_without_bbox']} "
        f"({s.get('detections_without_bbox_original', 0)} on original text, "
        f"{s.get('detections_without_bbox_planted', 0)} on planted text)"
    )
    if s.get("fp_excluded_documents"):
        print(
            f"  excluded from scoring {s['fp_excluded']} "
            f"in {s['fp_excluded_documents']} unusable document(s)"
        )
    print()
    print(f"matching: {s['matches_by_bbox']} by bbox, {s['matches_by_text']} by text fallback")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--only", default="*", help="glob over the ontlakt stems, e.g. '5_*'")
    ap.add_argument("--baseline", type=Path, help="report JSON to diff against")
    ap.add_argument(
        "--save-baseline",
        action="store_true",
        help="also copy this run to <corpus>/reports/baseline.json",
    )
    ap.add_argument("--out", type=Path, help="write <STEM>.json and <STEM>.md here")
    ap.add_argument(
        "--extractor",
        choices=("pdfjs", "pymupdf"),
        default="pdfjs",
        help=(
            "how to get the page text. 'pdfjs' runs the real library through "
            "eval/pdfjs_extract.mjs and is what production sends; 'pymupdf' is "
            "a lower-fidelity fallback for machines without node — different "
            "tokenisation, so its numbers are not comparable with a pdfjs "
            "baseline"
        ),
    )
    ap.add_argument("--quiet", action="store_true", help="no per-document progress")
    args = ap.parse_args()

    # `app.main` (which normally does this) is never imported here, so the
    # pipeline's structlog loggers would otherwise run at their default level
    # and bury the report under per-detection debug lines.
    configure_logging(os.environ.get("LOG_LEVEL", "ERROR"))

    ontlakt = args.corpus / "ontlakt"
    if not ontlakt.is_dir():
        print(f"geen ontlakt/ in {args.corpus} — draai eerst ontlak.py", file=sys.stderr)
        return 0

    pdfs = sorted(p for p in ontlakt.glob(f"{args.only}-ontlakt.pdf"))
    if not pdfs and args.only != "*":
        pdfs = sorted(p for p in ontlakt.glob(f"{args.only}.pdf"))
    if not pdfs:
        print(f"geen documenten gevonden voor --only {args.only!r}", file=sys.stderr)
        return 0

    fp_excluded: dict[str, str] = {}
    config_path = args.corpus / CORPUS_CONFIG
    if config_path.exists():
        fp_excluded = json.loads(config_path.read_text(encoding="utf-8")).get("fp_excluded", {})

    outcomes: list[DocOutcome] = []
    for pdf in pdfs:
        truth_path = pdf.with_suffix(".json")
        if not truth_path.exists():
            if not args.quiet:
                print(f"overgeslagen (geen ground truth): {pdf.name}")
            continue
        outcome = evaluate_document(
            pdf,
            truth_path,
            extractor=args.extractor,
            fp_excluded_reason=fp_excluded.get(pdf.stem.removesuffix("-ontlakt"), ""),
        )
        outcomes.append(outcome)
        if not args.quiet:
            r = outcome.report
            fp = f"FP {r.fp_hard}h/{r.fp_soft}s" if r.fp_scored else f"FP {r.fp_excluded} excl"
            print(
                f"{r.name[:58]:58s} truth {r.found:3d}/{r.truth:<3d} "
                f"(part {r.partial}, rej {r.rejected}, mis {r.missed})  "
                f"{fp}  supp {r.suppressed}"
            )

    repo = Path(__file__).resolve().parents[2]
    data = build_report(outcomes, args.corpus, repo, args.extractor)
    md = render_markdown(data)

    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        diff = compare_to_baseline(data, baseline)
        md = md + "\n" + "\n".join(diff)
        print("\n".join(diff))

    if args.out:
        stem = args.out
        stem.parent.mkdir(parents=True, exist_ok=True)
    else:
        reports = args.corpus / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        stem = reports / f"{stamp}-{data['backend']['sha']}"

    json_path = stem.with_suffix(".json")
    md_path = stem.with_suffix(".md")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")

    if args.save_baseline:
        baseline_path = args.corpus / "reports" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print_summary(data)
    print_triage(data)
    print()
    print(f"report: {md_path}")
    print(f"json:   {json_path}")
    if args.save_baseline:
        print(f"baseline saved: {args.corpus / 'reports' / 'baseline.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
