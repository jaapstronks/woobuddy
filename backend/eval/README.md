# Detection evaluation harness

Measures how well WOO Buddy's detection pipeline does on real Dutch Woo
documents: what it finds, what it half-finds, what it finds and then throws
away, what it misses, and what it flags that nobody asked it to flag.

Nothing in here is a test. `evaluate.py` always exits 0 — it is an instrument,
and instruments do not fail builds. Detector code is never touched from here.

## The corpus

The documents live **outside this repository**, at
`~/Github NW/woobuddy-eval-corpus` by default (override with `--corpus` or the
`WOOBUDDY_EVAL_CORPUS` environment variable). They are public, but they are
also a few hundred MB of PDFs, which does not belong in a source tree.

```
woobuddy-eval-corpus/
  woo-besluiten/     29 published Woo decisions (Drenthe, Nationale ombudsman,
                     Stadskanaal, rijksoverheid) — all with a text layer
  zienswijzen/       4 notas van zienswijzen
  ontlakt/           the same documents, refilled — see below
  reports/           evaluation output, one .json + .md per run
  fetch-more.sh      pull more PDFs from the Drenthe DiWoo sitemap
```

### Why published documents

A published Woo document is real in every respect except that the personal
data has been removed. Layout, fonts, boilerplate, tables and civil-service
prose are exactly what a reviewer meets in the wild. Two things follow:

1. **As published**, they measure *false positives*. Everything the redactor
   left in was left in on purpose, so a detector that lights up here is
   reacting to case numbers, cadastral references, job titles and
   organisation names.
2. **Refilled by `ontlak.py`**, they measure *recall*, with exact ground truth,
   because we know precisely what we put where.

25 of the 33 documents get no fills at all — they are the false-positive-only
half of the corpus and are scored too.

## Step 1 — regenerate `ontlakt/`

`ontlak.py` finds the holes the redactor left, infers from context what kind
of value used to sit there, and writes a fictional but realistic Dutch value
into the gap. No real personal data is ever recovered or reused: only the
*type* is inferred, the value itself is generated.

```sh
cd ~/Github\ NW/woobuddy-eval-corpus
~/Github\ NW/woobuddy/backend/eval/ontlak.py \
    woo-besluiten/*.pdf zienswijzen/*.pdf --out-dir ontlakt
```

The seed defaults to `20260907`; keep it, or every recall number in every
existing report becomes incomparable. Per input it writes
`<stem>-ontlakt.pdf` and `<stem>-ontlakt.json`:

```jsonc
{
  "bron": "...pdf", "seed": 20260907, "off_list_ratio": 0.4, "aantal": 38,
  "detections": [{
    "page": 12, "bbox": [x0, y0, x1, y1],
    "type": "volledige_naam",       // what we planted
    "value": "Oumaima Bouzambou",   // the exact string
    "slot_kind": "empty_label",     // empty_label | gap | blackbox
    "slot_type": "volledige_naam",  // type before any narrow-slot fallback
    "context": "Behandeld door",    // the text that gave away the type
    "in_wordlist": false            // is this name in Meertens/CBS?
  }],
  "unknown_zones": [{ "page": 12, "bbox": [...], "reason": "no_context" }]
}
```

Three ways a hole is recognised:

| kind | example | how it is typed |
|---|---|---|
| `empty_label` | the line is only `Aan:` / `Geachte` / `Behandeld door` | the label |
| `gap` | an unusually wide gap mid-line | the text left of the gap |
| `blackbox` | a loose black or grey bar | text to its left, or position (NAW block, top-left) |

**Unknown zones** are the honest half of that. When the context says nothing
(`werkdagen: ███` is not a name), when the slot is too narrow for a realistic
value, or when the page is a scan, no value is planted — and the rectangle is
recorded as an unknown zone with a reason (`no_context`, `too_narrow`,
`scanned_page`). The evaluator treats a detection landing there as neither a
hit nor a false positive. A smaller ground truth beats one that lies.

### Not testing in a circle

40% of generated names deliberately come from **outside** the Meertens/CBS
wordlists the detector itself ships (`--off-list-ratio`). Otherwise the test
only measures whether a list can find itself. Every planted name carries
`in_wordlist`, so both scores can be read separately — and the gap between
them is currently the most interesting number in the report.

## Step 2 — run an evaluation

```sh
cd ~/Github\ NW/woobuddy/backend
source .venv/bin/activate
LOG_LEVEL=ERROR ./eval/evaluate.py
```

Run it from `backend/` so `app.*` resolves to the checkout under test — that
is the whole point of the exercise. Deduce takes a couple of seconds to load
on the first document; the full corpus takes a few minutes.

```
--corpus DIR      corpus root (default: $WOOBUDDY_EVAL_CORPUS, else
                  ~/Github NW/woobuddy-eval-corpus)
--only GLOB       glob over document stems, e.g. --only '5_*'
--baseline PATH   diff this run against an earlier report's .json
--save-baseline   also copy this run to <corpus>/reports/baseline.json
--out STEM        write <STEM>.json and <STEM>.md instead of a timestamped
                  pair in <corpus>/reports/
--quiet           no per-document progress
```

Output lands in `<corpus>/reports/<YYYY-MM-DD-HHMM>-<gitsha7>.json` and `.md`,
with a summary on stdout.

## Step 3 — read the report

### Recall

Every planted value gets exactly one of four verdicts:

| outcome | meaning |
|---|---|
| `found` | a live detection covers ≥ 90% of the value |
| `partial` | a live detection covers some of it — the report says which words were left uncovered |
| `rejected` | the pipeline found the span and then *suppressed* it (`review_status == "rejected"`: a whitelist or the publiek-functionaris rule engine). The reviewer never sees it. A separate failure class, with the source and reasoning printed. |
| `missed` | nothing at all |

"Live" means `review_status` in `auto_accepted` / `pending` / `accepted` /
`edited` — everything that reaches the reviewer as a redaction suggestion.

Recall is broken down three ways: by planted type, by wordlist membership
(name in the Meertens/CBS lists vs outside them), and by slot kind. The
report also lists every miss, partial and rejection in full, with ±60
characters of context, so each one can be diagnosed rather than counted.

### False positives

Every detection not matched to a planted value and not sitting on an unknown
zone. Two severities:

- **hard** — `auto_accepted`: Tier 1, redacted without anyone looking at it.
  This is the expensive kind: it removes text from a published document.
- **soft** — `pending`: a Tier 2 suggestion, one click to reject.

`rejected` detections are listed separately as *suppressed*, counted by
source. They are informational: they show the whitelist and rule engine doing
their job.

> **The caveat, which the report repeats:** a published Woo document
> legitimately contains names the redactor left in — public officials,
> organisations, sometimes the requester's own lawyer. Those show up here as
> false positives, and that is exactly what we want, because the redactor's
> decision is our ground truth for "not to be redacted". But redactors also
> miss things. **A false positive is a candidate, never a verdict.** Read the
> grouped table (sorted hard-first, then by frequency) before believing any
> single row.

Two categories are counted but not charged: detections that land on an
unknown zone, and detections the pipeline produced without a bounding box
(nothing is drawn on the page, so there is nothing to check).

### Matching, and how it can lie

A planted value and a detection are the same finding when their boxes
overlap — intersection ≥ 30% of the truth box, **or** ≥ 50% of the detection
box. Two thresholds because the failure modes differ: a detector that finds
only the surname of a full name fails the first test, and one that flags the
whole line containing the name fails the second.

Bounding boxes drift (span resolution, rotated pages, inserted text that does
not land exactly where the ground truth says), so there is a text fallback:
same page, and one normalised string contains the other, minimum length 4.
The report prints how many matches came from each route — if the text
fallback ever carries most of the matches, distrust the geometry before you
distrust the detector.

All thresholds sit together at the top of `evaluate.py` under "Tunables".

## Step 4 — compare against a baseline

```sh
./eval/evaluate.py --save-baseline                              # set the mark
# ... change a detector ...
./eval/evaluate.py --baseline ~/Github\ NW/woobuddy-eval-corpus/reports/baseline.json
```

The diff section, printed and appended to the markdown, lists truth items
newly found / newly missed / newly rejected (keyed by document + page +
value) and false-positive candidates new / gone (keyed by document + page +
normalised text), plus totals. A `--only` run compares only the documents
both runs actually scored, so a one-document check does not read as a
thousand disappeared false positives.

## Files

| file | what it is |
|---|---|
| `ontlak.py` | fills the holes in published documents; writes ground truth + unknown zones |
| `evaluate.py` | runs the pipeline over `ontlakt/` and reports |
| `pdfio.py` | shared: scanned-page detection and the pdf.js-shaped page payload |

`pdfio.py` exists so the generator and the evaluator can never disagree about
what counts as a scanned page. If they did, the evaluator would score
detections on pages the generator never filled.

CI lints and type-checks `app/` only, and the Docker image copies `app/` only,
so nothing here reaches production. Lint this directory by hand:

```sh
cd backend && ruff check eval/ && ruff format --check eval/
```

## Limitations

- Only pages with a real text layer are used. Scans are skipped by both
  scripts (their OCR layer reads `imaae002.pna`); that costs roughly half of
  the Drenthe corpus, and shows up in the report as skipped pages.
- Type inference is a heuristic. `slot_kind` and `context` are in the JSON so
  a sample can be checked by hand.
- Inserted values are rendered in Helvetica/Times, not the original's
  embedded font. Visually close enough; not identical.
- Precision cannot be measured exactly — see the caveat above.
