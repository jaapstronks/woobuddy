#!/usr/bin/env python3
"""Group an evaluation report's errors by suspected cause.

`evaluate.py` says *what* went wrong, 500 rows at a time. This says what the
rows have in common, and which brief in `docs/plans/` each cause belongs to,
so an executing session can pick one cause, build one rule and open one PR
instead of reading a report end to end first.

Every label is a hypothesis. Counts come with up to eight examples so a wrong
guess is visible at a glance, and anything no rule recognises lands under
`unclassified` — which is the section worth reading, because three items
sharing a cause there is the signal to add a rule to `triage_rules.py`.

    ./triage.py <report>.json          # writes <report>-triage.md
    ./triage.py                        # newest report in the corpus

`evaluate.py` calls `render_triage()` itself, so a normal run already carries
this as the last section of its markdown.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from triage_rules import ALL_RULES, TriageItem, classify  # noqa: E402, I001

DEFAULT_CORPUS = Path(
    os.environ.get("WOOBUDDY_EVAL_CORPUS") or Path.home() / "Github NW/woobuddy-eval-corpus"
)

#: How many examples to print per cause. Enough to see a pattern, few enough
#: that the table stays a table.
MAX_EXAMPLES = 8
CONTEXT_WIDTH = 100


# --------------------------------------------------------------------------
# Turning a report into items
# --------------------------------------------------------------------------


def _doc_facts(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per document: how often each text was flagged, and what had no bbox.

    Two rules need to look past a single row — "this address appears on every
    page" and "this planted value was found but never drawn" — and both are
    document-scoped, so compute them once here.
    """
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for fp in data.get("false_positives", []):
        counts[fp["doc"]][fp["entity_text"].lower()] += 1
    no_bbox: dict[str, set[str]] = defaultdict(set)
    for n in data.get("detections_without_bbox_items", []):
        no_bbox[n["doc"]].add(n["entity_text"])
    return {
        doc: {
            "text_counts": dict(counts.get(doc, {})),
            "no_bbox_texts": tuple(no_bbox.get(doc, ())),
        }
        for doc in {*counts, *no_bbox, *(d["name"] for d in data.get("documents", []))}
    }


def items_from_report(data: dict[str, Any]) -> tuple[list[TriageItem], list[TriageItem]]:
    """`(false positives, recall failures)` as triage items."""
    facts = _doc_facts(data)

    fps = [
        TriageItem(
            kind="fp",
            doc=f["doc"],
            page=f.get("page"),
            text=f["entity_text"],
            entity_type=f["entity_type"],
            source=f.get("source", ""),
            review_status=f.get("review_status", ""),
            context=f.get("context", ""),
            severity=f.get("severity", ""),
            doc_facts=facts.get(f["doc"], {}),
        )
        for f in data.get("false_positives", [])
    ]

    fns: list[TriageItem] = []
    for t in data.get("truth_results", []):
        if t["outcome"] == "found" and not t.get("lenient"):
            continue
        matched = t.get("matched") or []
        fns.append(
            TriageItem(
                kind="fn",
                doc=t["doc"],
                page=t.get("page"),
                text=t["value"],
                truth_type=t.get("type", ""),
                source=" ".join(m.get("source", "") for m in matched),
                reasoning=" ".join(m.get("reasoning", "") for m in matched),
                context=t.get("context", ""),
                slot_context=t.get("context", ""),
                outcome=t["outcome"],
                uncovered=t.get("uncovered", ""),
                in_wordlist=t.get("in_wordlist"),
                lenient=bool(t.get("lenient")),
                doc_facts=facts.get(t["doc"], {}),
            )
        )
    return fps, fns


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _section(title: str, items: list[TriageItem], kind: str) -> list[str]:
    by_cause: dict[str, list[TriageItem]] = defaultdict(list)
    unclassified: list[TriageItem] = []
    for item in items:
        rules = classify(item)
        if not rules:
            unclassified.append(item)
            continue
        for rule in rules:
            by_cause[rule.name].append(item)

    briefs = {r.name: r.brief for r in ALL_RULES}
    notes = {r.name: r.note for r in ALL_RULES}

    out = [f"### {title} ({len(items)})", ""]
    if not items:
        out += ["_none_", ""]
        return out
    out.append("| cause | brief | count | what it means |")
    out.append("|---|---|---:|---|")
    for name, rows in sorted(by_cause.items(), key=lambda kv: -len(kv[1])):
        out.append(f"| `{name}` | {briefs.get(name, '')} | {len(rows)} | {notes.get(name, '')} |")
    out.append(f"| _unclassified_ | | {len(unclassified)} | no rule recognises these yet |")
    out.append("")

    for name, rows in sorted(by_cause.items(), key=lambda kv: -len(kv[1])):
        out.append(f"<details><summary><code>{name}</code> — {len(rows)}</summary>")
        out.append("")
        for item in rows[:MAX_EXAMPLES]:
            ctx = item.context.replace("|", "\\|")[:CONTEXT_WIDTH]
            out.append(f"- `{item.text}` — {item.doc} p.{item.page} — {ctx}")
        if len(rows) > MAX_EXAMPLES:
            out.append(f"- … and {len(rows) - MAX_EXAMPLES} more")
        out.append("")
        out.append("</details>")
        out.append("")

    if unclassified:
        out.append(f"<details><summary><code>unclassified</code> — {len(unclassified)}</summary>")
        out.append("")
        out.append(
            "Three or more of these sharing a cause is the signal to add a rule "
            "to `triage_rules.py`, in the same PR that acts on it."
        )
        out.append("")
        for item in unclassified[: MAX_EXAMPLES * 3]:
            ctx = item.context.replace("|", "\\|")[:CONTEXT_WIDTH]
            extra = item.entity_type if kind == "fp" else f"{item.truth_type}/{item.outcome}"
            out.append(f"- [{extra}] `{item.text}` — {item.doc} p.{item.page} — {ctx}")
        if len(unclassified) > MAX_EXAMPLES * 3:
            out.append(f"- … and {len(unclassified) - MAX_EXAMPLES * 3} more")
        out.append("")
        out.append("</details>")
        out.append("")
    return out


def render_triage(data: dict[str, Any]) -> list[str]:
    """The triage section, as markdown lines. Used by `evaluate.py` too."""
    fps, fns = items_from_report(data)
    out = ["## Triage", ""]
    out.append(
        "Suspected cause per error, with the brief it belongs to. Labels are "
        "hypotheses — read the examples before acting on a count. One cause "
        "per pull request."
    )
    out.append("")
    out += _section("False-positive candidates", fps, "fp")
    out += _section("Recall failures (missed, partial, rejected)", fns, "fn")
    return out


def counts(data: dict[str, Any]) -> tuple[Counter[str], Counter[str], int, int]:
    """`(fp counts, fn counts, fp unclassified, fn unclassified)` for stdout."""
    fps, fns = items_from_report(data)
    out: list[Counter[str]] = []
    unclassified: list[int] = []
    for items in (fps, fns):
        c: Counter[str] = Counter()
        n = 0
        for item in items:
            rules = classify(item)
            if not rules:
                n += 1
            for rule in rules:
                c[rule.name] += 1
        out.append(c)
        unclassified.append(n)
    return out[0], out[1], unclassified[0], unclassified[1]


def print_triage(data: dict[str, Any]) -> None:
    fp_counts, fn_counts, fp_unc, fn_unc = counts(data)
    briefs = {r.name: r.brief for r in ALL_RULES}
    for label, c, unc in (
        ("false positives", fp_counts, fp_unc),
        ("recall failures", fn_counts, fn_unc),
    ):
        print()
        print(f"--- triage: {label} ---")
        for name, n in c.most_common():
            print(f"  {name:<28} {n:5d}  {briefs.get(name, '')}")
        print(f"  {'unclassified':<28} {unc:5d}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", nargs="?", type=Path, help="an evaluate.py report .json")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = ap.parse_args()

    path = args.report
    if path is None:
        reports = sorted(
            (p for p in (args.corpus / "reports").glob("*.json") if p.name != "baseline.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not reports:
            print(f"geen rapport gevonden in {args.corpus / 'reports'}", file=sys.stderr)
            return 0
        path = reports[-1]

    data = json.loads(path.read_text(encoding="utf-8"))
    md = "\n".join(render_triage(data))
    out = path.with_name(f"{path.stem}-triage.md")
    out.write_text(md + "\n", encoding="utf-8")
    print_triage(data)
    print()
    print(f"report: {path}")
    print(f"triage: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
