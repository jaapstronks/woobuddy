"""Function-title → detection rules (#13).

Extracted from `pipeline_engine.py` so the rule-engine mapping can be
tested and grown in isolation. The two public helpers are:

- `match_function_title`: run the role-engine title scan plus a
  leading-title-in-span fallback for cases where Deduce's persoon span
  swallowed the title itself.
- `title_match_to_detection`: map a `FunctionTitleMatch` onto a
  `PipelineDetection` with the correct review semantics (publiek →
  rejected, ambtenaar → pending with pre-filled role).
"""

from app.services.ner_engine import DEFAULT_WOO_ARTICLE, NERDetection
from app.services.pipeline_types import Bbox, PipelineDetection
from app.services.role_engine import (
    FunctionTitleMatch,
    find_function_title_near,
    get_function_title_lists,
)


def match_function_title(
    full_text: str,
    span_text: str,
    start_char: int,
    end_char: int,
) -> FunctionTitleMatch | None:
    """Look for a function title near — or inside — a Tier 2 persoon span.

    The normal case is a title in the surrounding text ("Wethouder Jan
    de Vries"), which `role_engine.find_function_title_near` handles
    via the character window. But Deduce's person span sometimes
    swallows the title itself (annotation covers "Wethouder Jan de
    Vries" as one "persoon"), in which case the character window before
    the span is empty and the normal path finds nothing. As a fallback
    we scan the span text for a leading title — that's the apposition
    case but folded into the detection.
    """
    lists = get_function_title_lists()
    match = find_function_title_near(full_text, start_char, end_char, lists)
    if match is not None:
        return match

    # Fallback: leading-title-in-span. We only accept a match at the
    # start of the span (so "Jan de Vries Wethouder" doesn't fire here —
    # that's an after-context case that already goes through the
    # character-window path). Same tie-breaking as before: publiek beats
    # ambtenaar if both happen to fit the prefix (extremely rare).
    stripped = (span_text or "").lstrip()
    best: FunctionTitleMatch | None = None
    for list_name, title, pattern in lists.iter_all():
        m = pattern.match(stripped)
        if m is None:
            continue
        # Require at least one token after the title inside the span,
        # otherwise the span is just the title with no name attached.
        remainder = stripped[m.end() :].strip()
        if not remainder:
            continue
        candidate = FunctionTitleMatch(
            title=title,
            list_name=list_name,
            position="before",
            tokens_between=0,
        )
        if best is None or (candidate.list_name == "publiek" and best.list_name == "ambtenaar"):
            best = candidate
    return best


def title_match_to_detection(
    det: NERDetection,
    bboxes: list[Bbox],
    match: FunctionTitleMatch,
) -> PipelineDetection | None:
    """Map a rule-engine hit onto a PipelineDetection.

    Publiek titles default to `review_status="rejected"` (the
    public-officials-do-not-redact rule). Ambtenaar titles stay
    `pending` but with a pre-filled role so the reviewer only confirms.
    """
    if match.list_name == "publiek":
        return PipelineDetection(
            entity_text=det.text,
            entity_type="persoon",
            tier="2",
            confidence=min(det.confidence + 0.05, 0.95),
            woo_article=None,
            review_status="rejected",
            bounding_boxes=bboxes,
            reasoning=(
                f"Publiek functionaris: voorafgegaan door '{match.title}' in de brontekst."
                if match.position == "before"
                else f"Publiek functionaris: gevolgd door '{match.title}' in de brontekst."
            ),
            source="rule",
            subject_role="publiek_functionaris",
            start_char=det.start_char,
            end_char=det.end_char,
        )

    # Ambtenaar — keep pending, pre-fill the role, reviewer confirms.
    return PipelineDetection(
        entity_text=det.text,
        entity_type="persoon",
        tier="2",
        confidence=det.confidence,
        woo_article=DEFAULT_WOO_ARTICLE,
        review_status="pending",
        bounding_boxes=bboxes,
        reasoning=(
            f"Vermoedelijk ambtenaar in functie: voorafgegaan door '{match.title}'."
            if match.position == "before"
            else f"Vermoedelijk ambtenaar in functie: gevolgd door '{match.title}'."
        ),
        source="rule",
        subject_role="ambtenaar",
        start_char=det.start_char,
        end_char=det.end_char,
    )
