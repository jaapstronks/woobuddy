"""Generate a short, large-font PDF tailored for a <8 second screencast demo.

The doc is intentionally sparse: a fictional internal memo from gemeente
Duinenburg with one Tier-1 BSN, one Tier-1 phone number, two Tier-2 names
(to demo "bevestig hoog-vertrouwen Trap 2"), one publiek-functionaris name
(filtered by the rule engine), and one deliberately-creative phrase that no
wordlist will catch — perfect for demoing the manual redaction flow.

Run from the repo root after activating the backend venv:

    cd backend && source .venv/bin/activate
    python ../tests/fixtures/generate_demo_video_sample.py
"""

from __future__ import annotations

from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "fixtures" / "demo-video.pdf"

A4_WIDTH, A4_HEIGHT = 595, 842
MARGIN = 50
CONTENT_RECT = fitz.Rect(MARGIN, MARGIN, A4_WIDTH - MARGIN, A4_HEIGHT - MARGIN)

CSS = """
body { font-family: sans-serif; color: #111; font-size: 19pt; line-height: 1.5; }
h1 { font-size: 30pt; margin: 0 0 4pt 0; letter-spacing: 0.5pt; }
h2 { font-size: 20pt; margin: 16pt 0 6pt 0; color: #333; }
.meta { color: #555; font-size: 14pt; margin: 0 0 14pt 0; }
p { margin: 0 0 10pt 0; }
.row { margin: 0 0 4pt 0; }
.label { color: #666; }
.sig { color: #444; font-size: 16pt; margin-top: 14pt; }
"""

HTML = """
<h1>NOTITIE</h1>
<div class="meta">Gemeente Duinenburg &middot; 15 april 2026 &middot; dossier DB-2026-0142</div>

<h2>Klacht geluidsoverlast</h2>

<p>Klaagster <strong>Jolanda Klaverstein</strong> belde gisteravond
om 21:45 in paniek over aanhoudende geluidsoverlast.</p>

<p class="row"><span class="label">BSN:</span> 123456782 &nbsp;&nbsp; <span class="label">Mobiel:</span> 06-12345678</p>

<p>Als getuige noemt zij haar buurvrouw <strong>Tineke Bakker</strong>,
die al maandenlang dezelfde overlast ervaart.</p>

<p>Bijzonderheid: de hond van de klaagster staat in de buurt bekend
als &ldquo;Opera op vier poten&rdquo;.</p>

<p class="sig">Wethouder P. Hoogvliet neemt het dossier in behandeling.</p>
"""


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    mediabox = fitz.Rect(0, 0, A4_WIDTH, A4_HEIGHT)
    story = fitz.Story(html=f"<style>{CSS}</style>{HTML}")
    writer = fitz.DocumentWriter(str(OUT_PATH))
    more = 1
    while more:
        dev = writer.begin_page(mediabox)
        more, _filled = story.place(CONTENT_RECT)
        story.draw(dev)
        writer.end_page()
    writer.close()
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
