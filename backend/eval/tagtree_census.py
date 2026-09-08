"""How much logical structure does a real Woo corpus actually carry?

Two questions, both raised by Bos & Marx, *Why Reconstruct What Was Never
Lost?* (IRLab UvA, 2026). That paper argues structure should be preserved when
a PDF is authored rather than reconstructed afterwards, and lists corpus
expansion to government documents as future work. This is that corpus.

**Census.** Does a published Woo PDF carry a logical structure tree at all,
and if it does, is the tree worth reading? Those are different questions. A
`/StructTreeRoot` with nothing but `/P` under it satisfies every checker and
tells a consumer nothing beyond "this is a paragraph"; headings, lists and
table semantics are what make tag-based extraction beat layout inference.

**Redaction round-trip** (`--redaction`). Marx reported that redacting while
keeping the tag tree intact failed in two or three theses, on the grounds that
every PDF exporter tags differently. This measures our own pipeline against
that claim: take a tagged document, run `apply_redactions` over real text on
up to `--pages` pages, and compare the tree before and after.

Two caveats belong with any number this prints. An identical tree is not a
valid one - the redacted text leaves an empty marked-content span behind, and
nothing here runs veraPDF. And a node count is a coarse instrument: it catches
a tree that was dropped or truncated, not one whose MCIDs now point at content
that no longer exists. The marked-content counts per page are here for that
reason, but they are evidence, not proof.

Like `evaluate.py`, this is an instrument: it always exits 0 and never touches
detector code.

    python eval/tagtree_census.py                    # census only
    python eval/tagtree_census.py --redaction        # + round-trip check
    python eval/tagtree_census.py --out ~/census     # write .json and .md
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import fitz  # noqa: E402
import pikepdf  # noqa: E402

from app.services.pdf_engine import apply_redactions  # noqa: E402

DEFAULT_CORPUS = Path(
    os.environ.get("WOOBUDDY_EVAL_CORPUS") or Path.home() / "Github NW/woobuddy-eval-corpus"
)

#: Structure types that make a tree worth parsing. A tree of nothing but
#: paragraphs is formally present and practically empty, which is the
#: distinction the census exists to draw.
HEADING_RE = re.compile(r"^/H\d*$")
TABLE_TYPES = {"/Table", "/TR", "/TH", "/TD"}
LIST_TYPES = {"/L", "/LI", "/LBody"}

#: A tree this small is a stub - a `/Document` wrapper with a couple of nodes
#: under it - and says nothing about the document's structure either way.
MIN_MEANINGFUL_NODES = 5


@dataclass
class DocCensus:
    """One document's structural inventory."""

    name: str
    marked: bool
    has_tree: bool
    nodes: int = 0
    types: dict[str, int] = field(default_factory=dict)
    headings: int = 0
    tables: int = 0
    lists: int = 0
    error: str = ""

    @property
    def useful(self) -> bool:
        """A tree a consumer could navigate, rather than one that merely exists."""
        return self.headings > 0 or self.tables > 0


@dataclass
class RedactionCheck:
    """What a redaction pass did to one document's tree."""

    name: str
    nodes_before: int
    nodes_after: int
    mcids_before: int
    mcids_after: int
    rects: int
    text_removed: bool
    error: str = ""

    @property
    def verdict(self) -> str:
        if self.error:
            return "error"
        if self.nodes_after == 0:
            return "tree lost"
        if self.nodes_after != self.nodes_before:
            return "tree changed"
        return "tree intact"


def _walk_types(node: Any, seen: set[tuple[int, int]], out: Counter, depth: int = 0) -> None:
    """Count `/S` structure types under `node`.

    Guarded on object generation rather than `id()`: pikepdf hands out a fresh
    Python wrapper on every access, and CPython reuses the ids of freed ones,
    so an identity-based visited-set silently truncates the walk.
    """
    if depth > 60:
        return
    try:
        objgen = node.objgen
        if objgen != (0, 0):
            if objgen in seen:
                return
            seen.add(objgen)
    except AttributeError:
        pass
    if isinstance(node, pikepdf.Dictionary):
        struct_type = node.get("/S")
        if struct_type is not None:
            out[str(struct_type)] += 1
        kids = node.get("/K")
        if kids is not None:
            _walk_types(kids, seen, out, depth + 1)
    elif isinstance(node, pikepdf.Array):
        for kid in node:
            _walk_types(kid, seen, out, depth + 1)


def tag_types(pdf_bytes: bytes) -> Counter | None:
    """Structure types in a PDF's logical tree, or None if it has no tree."""
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        if "/StructTreeRoot" not in pdf.Root:
            return None
        types: Counter = Counter()
        _walk_types(pdf.Root.StructTreeRoot.get("/K"), set(), types)
        return types


def _marked(pdf_bytes: bytes) -> bool:
    """Whether the catalog claims the document is tagged.

    `/MarkInfo /Marked` is a claim, not a guarantee: documents assert it
    without carrying a tree, and carry a tree without asserting it. The census
    reports both so the gap is visible.
    """
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        mark_info = pdf.Root.get("/MarkInfo")
        return bool(mark_info.get("/Marked", False)) if mark_info is not None else False


def census_document(path: Path) -> DocCensus:
    pdf_bytes = path.read_bytes()
    try:
        types = tag_types(pdf_bytes)
        marked = _marked(pdf_bytes)
    except Exception as exc:  # a corrupt PDF is a finding, not a crash
        return DocCensus(path.name, False, False, error=str(exc)[:120])
    if types is None:
        return DocCensus(path.name, marked, False)
    return DocCensus(
        name=path.name,
        marked=marked,
        has_tree=True,
        nodes=sum(types.values()),
        types=dict(types),
        headings=sum(n for t, n in types.items() if HEADING_RE.match(t)),
        tables=sum(n for t, n in types.items() if t in TABLE_TYPES),
        lists=sum(n for t, n in types.items() if t in LIST_TYPES),
    )


def _mcid_count(pdf_bytes: bytes, page: int = 0) -> int:
    """Marked-content identifiers in one page's content stream.

    The tree can survive a redaction while the content it points at does not.
    Comparing this before and after catches the coarsest version of that:
    markers dropped along with the text.
    """
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        if page >= len(pdf.pages):
            return 0
        contents = pdf.pages[page].get("/Contents")
        if contents is None:
            return 0
        streams = [contents] if isinstance(contents, pikepdf.Stream) else contents
        raw = b"".join(bytes(s.read_bytes()) for s in streams)
        return len(re.findall(rb"/MCID", raw))


def _redaction_rects(pdf_bytes: bytes, max_pages: int) -> tuple[list[dict[str, Any]], str]:
    """Pick a run of real words per page, so the redaction hits tagged content.

    Returns the rects plus one word we expect to disappear, which is how the
    caller tells a redaction that landed from one that quietly missed.
    """
    rects: list[dict[str, Any]] = []
    probe = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_no in range(min(len(doc), max_pages)):
            words = doc[page_no].get_text("words")
            if len(words) < 20:
                continue
            run = words[len(words) // 3 : len(words) // 3 + 10]
            rects.append(
                {
                    "page": page_no,
                    "x0": min(w[0] for w in run),
                    "y0": min(w[1] for w in run),
                    "x1": max(w[2] for w in run),
                    "y1": max(w[3] for w in run),
                    "woo_article": "5.1.2e",
                }
            )
            if not probe:
                # A word that occurs once on the page, so its absence afterwards
                # means this redaction removed it rather than some other one.
                counts = Counter(w[4] for w in words)
                probe = next((w[4] for w in run if counts[w[4]] == 1 and len(w[4]) > 3), "")
    return rects, probe


def check_redaction(path: Path, max_pages: int) -> RedactionCheck | None:
    """Redact real text and report what survived of the structure tree."""
    pdf_bytes = path.read_bytes()
    before = tag_types(pdf_bytes)
    if before is None or sum(before.values()) < MIN_MEANINGFUL_NODES:
        return None
    try:
        rects, probe = _redaction_rects(pdf_bytes, max_pages)
        if not rects:
            return None
        outcome = apply_redactions(pdf_bytes, rects)
        redacted = getattr(outcome, "pdf_bytes", None) or outcome[0]
        after = tag_types(redacted)
        with fitz.open(stream=redacted, filetype="pdf") as doc:
            text_removed = bool(probe) and probe not in doc[rects[0]["page"]].get_text()
        return RedactionCheck(
            name=path.name,
            nodes_before=sum(before.values()),
            nodes_after=sum(after.values()) if after else 0,
            mcids_before=_mcid_count(pdf_bytes, rects[0]["page"]),
            mcids_after=_mcid_count(redacted, rects[0]["page"]),
            rects=len(rects),
            text_removed=text_removed,
        )
    except Exception as exc:
        return RedactionCheck(path.name, sum(before.values()), 0, 0, 0, 0, False, str(exc)[:120])


def corpus_documents(corpus: Path, pattern: str) -> list[Path]:
    """Every source PDF in the corpus, counted once.

    `ontlakt/` holds a refilled copy of each document with the same structure
    tree; including both would double every number in the census.
    """
    return sorted(
        p
        for p in corpus.glob(f"**/{pattern}.pdf")
        if not p.stem.endswith("-ontlakt") and "reports" not in p.parts
    )


def render_report(
    census: list[DocCensus], checks: list[RedactionCheck], corpus: Path, when: str
) -> str:
    tagged = [d for d in census if d.has_tree]
    meaningful = [d for d in tagged if d.nodes >= MIN_MEANINGFUL_NODES]
    useful = [d for d in meaningful if d.useful]
    totals: Counter = Counter()
    for doc in tagged:
        totals.update(doc.types)

    lines = [
        "# Structure-tree census of a Woo corpus",
        "",
        f"- **Run**: {when}",
        f"- **Corpus**: `{corpus}`",
        f"- **Documents**: {len(census)} (each counted once; `ontlakt/` copies excluded)",
        "",
        "> A `/StructTreeRoot` is not the same as usable structure. The last",
        "> column is the one that matters for tag-based extraction: a tree of",
        "> nothing but paragraphs cannot tell a consumer more than a layout",
        "> heuristic already would.",
        "",
        "## Headline",
        "",
        "| | count | share |",
        "|---|---:|---:|",
    ]
    total = len(census) or 1
    for label, count in [
        ("claims /MarkInfo /Marked", sum(1 for d in census if d.marked)),
        ("has a structure tree", len(tagged)),
        (f"tree with >= {MIN_MEANINGFUL_NODES} nodes", len(meaningful)),
        ("has headings or table semantics", len(useful)),
    ]:
        lines.append(f"| {label} | {count} | {100 * count / total:5.1f}% |")

    lines += [
        "",
        "## Tag census over the whole corpus",
        "",
        "| structure type | count |",
        "|---|---:|",
    ]
    lines += [f"| `{t}` | {n} |" for t, n in totals.most_common(20)]

    lines += [
        "",
        "## Per document",
        "",
        "| document | nodes | headings | tables | lists | usable |",
        "|---|---:|---:|---:|---:|:--:|",
    ]
    for doc in sorted(tagged, key=lambda d: -d.nodes):
        mark = "yes" if doc.useful else "no"
        lines.append(
            f"| {doc.name} | {doc.nodes} | {doc.headings} | {doc.tables} | {doc.lists} | {mark} |"
        )
    untagged = [d for d in census if not d.has_tree]
    if untagged:
        lines += ["", f"{len(untagged)} document(s) carry no structure tree at all."]

    if checks:
        intact = sum(1 for c in checks if c.verdict == "tree intact")
        lines += [
            "",
            "## Redaction round-trip",
            "",
            f"Redacted a run of real words on up to {max(c.rects for c in checks)} page(s) "
            f"per document, then compared the tree. {intact} of {len(checks)} kept it intact.",
            "",
            "> Intact is not valid. The redacted passage leaves an empty",
            "> marked-content span behind, and veraPDF has not been run over any",
            "> of this. What this rules out is the tree being dropped or",
            "> truncated by the redaction pass.",
            "",
            "| document | nodes before | after | MCIDs before | after | text gone | verdict |",
            "|---|---:|---:|---:|---:|:--:|---|",
        ]
        for check in checks:
            gone = "yes" if check.text_removed else "no"
            lines.append(
                f"| {check.name} | {check.nodes_before} | {check.nodes_after} | "
                f"{check.mcids_before} | {check.mcids_after} | {gone} | {check.verdict} |"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--only", default="*", help="glob over document stems, e.g. '5_*'")
    parser.add_argument(
        "--redaction",
        action="store_true",
        help="also redact each tagged document and compare the tree before and after",
    )
    parser.add_argument(
        "--pages", type=int, default=5, help="pages to redact per document (default 5)"
    )
    parser.add_argument("--out", type=Path, help="write <STEM>.json and <STEM>.md here")
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"corpus not found: {args.corpus}", file=sys.stderr)
        return 0

    pdfs = corpus_documents(args.corpus, args.only)
    if not pdfs:
        print(f"no documents matching '{args.only}' under {args.corpus}", file=sys.stderr)
        return 0

    census = [census_document(p) for p in pdfs]
    checks: list[RedactionCheck] = []
    if args.redaction:
        for path in pdfs:
            check = check_redaction(path, args.pages)
            if check is not None:
                checks.append(check)

    when = datetime.now().astimezone().isoformat(timespec="seconds")
    report = render_report(census, checks, args.corpus, when)
    print(report)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        stem = datetime.now().strftime("%Y-%m-%d-%H%M") + "-tagtree"
        (args.out / f"{stem}.md").write_text(report)
        (args.out / f"{stem}.json").write_text(
            json.dumps(
                {
                    "generated_at": when,
                    "corpus": str(args.corpus),
                    "documents": [asdict(d) for d in census],
                    "redaction_checks": [asdict(c) for c in checks],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"written: {args.out / stem}.md / .json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
