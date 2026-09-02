# 67 — Export chain: Ghostscript undoes `/Lang`, blocking I/O, disk write

- **Priority:** P1 (test suite is red on any machine with Ghostscript; a11y promise from #48 not kept)
- **Size:** S–M
- **Source:** tighten-scan 2026-09-02; `/Lang` finding reproduced empirically by Fable
- **Notion:** _not tracked yet_

> Line numbers verified on `origin/main` @ `83fecbb`; re-verify before editing.

## Why

`backend/tests/test_export_api.py::test_empty_redactions_returns_unmodified`
fails on a dev machine with Ghostscript installed (`gs 10.07.1`), and passes in
CI and production only because neither has Ghostscript. That means:

- **Production never produces PDF/A** (`backend/Dockerfile:6-9` installs only
  `libmupdf-dev`; `.github/workflows/test.yml` installs nothing) and logs
  `export.pdfa.ghostscript_missing` on every export.
- **Where Ghostscript *is* present it strips `/Lang`.** Reproduced with
  `post_process_for_accessibility(..., enable_pdfa=True)`: `Lang=None`,
  `pdfaid:part=2`; with `enable_pdfa=False`: `Lang=nl-NL`. The chain in
  `pdf_accessibility.py:324-348` sets `/Lang` *before* Ghostscript rewrites the
  catalog, so the "single highest-impact accessibility win" (`:176-178`) is undone
  by the last step. XMP `dc:title` and the annotations survive.

## Findings

1. `/Lang` lost after PDF/A conversion (above). Fix: set `/Lang` after
   `convert_to_pdfa`, or pass it via a pdfmark `-c` block so Ghostscript keeps it.
2. **Accessible annotation `/Rect` is in the wrong coordinate space — plausible, strong.**
   `pdf_accessibility.py:135-142` writes PyMuPDF top-left-origin coordinates
   (the same values `pdf_engine.py:319` hands to `fitz.Rect`) straight into a
   pikepdf `/Rect`, which is bottom-left-origin user space. Every screen-reader
   annotation is vertically mirrored. `tests/test_pdf_accessibility.py` asserts
   only `/Contents` and `/Alt`, never position.
3. **Blocking CPU + subprocess inside `async def` — confirmed.**
   `backend/app/api/export.py:166-176` runs `apply_redactions` (PyMuPDF), three
   pikepdf open→save round-trips (`pdf_accessibility.py:123,180,211`) and
   `subprocess.run(gs, timeout=60)` (`:297-302`) inline. One export can stall the
   event loop, health checks included, for up to a minute. `run_pipeline` does it
   right with `asyncio.to_thread` (`pipeline_engine.py:520`).
4. **Document bytes written to disk — contradicts the module's own contract.**
   `pdf_accessibility.py:280-283` writes the (redacted, still sensitive) PDF to a
   tempdir for Ghostscript, while `export.py:5-7` states "Nothing is written to
   disk". Ghostscript runs without `-dSAFER` on untrusted input.
5. `pdf_engine.py:133/183, 312/326, 332/334` — `doc.close()` without
   `try/finally` (3 leaky sites vs 3 correct ones in `pdf_accessibility.py`).
6. `export.py:138-142` checks `MAX_PDF_SIZE` *after* `await pdf.read()`; only
   `deploy/Caddyfile:36-38` bounds the body. `api/analyze.py` has no size or
   length limits at all (`schemas.py:96-108`).

## Jaap decides (before the session starts)

**Is PDF/A-2b wanted at all?** It was promised in #48 but has never run in
production. Two honest options:

- **Yes**: add `ghostscript` to `backend/Dockerfile` and to the CI job, move
  `/Lang` after the conversion, run the whole chain in `asyncio.to_thread`,
  pass `-dSAFER`, and accept the tempfile (document it in `export.py`'s header).
- **No**: delete `convert_to_pdfa` and the tempfile path, keep `/Lang` + XMP +
  annotations (all in-memory), and update `done/48-accessible-pdf-export.md`.

Either way the test stops being environment-dependent.

## Gate

- CI installs Ghostscript (or the code path is gone), so the export test means
  the same thing on every machine.
- A test that asserts `/Lang == nl-NL` **and** an annotation `/Rect` position
  against a known page height.

## Acceptance criteria

- [ ] `pytest` green with and without Ghostscript on PATH.
- [ ] `/Lang` present on the final bytes of every export.
- [ ] Export handler does no CPU work on the event loop.
