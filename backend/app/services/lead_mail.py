"""Copy and markup for the newsletter confirmation mail (#76).

Kept apart from `app/api/leads.py` on purpose. The notification mail
that lives there is an internal dump of form fields for the operator;
this one is public-facing copy that a visitor reads, in a moment where
they are deciding whether this tool is trustworthy. Different audience,
different change cadence — and copy is easier to edit when it is not
interleaved with HTTP error mapping.

What the copy has to do, and why:

* **Not mention any brand but WOO Buddy, and no list name.** The mail
  this replaces did both (see `app/api/leads.py`); the landing page sells
  "geen nieuwsbrief, alleen een bericht als er écht iets te melden is".
* **Name the operator.** Bureau Bolster B.V. is the entity on the
  privacy page, so it belongs here too — someone checking who is about
  to mail them should find the same name in both places.
* **Say what "updates" means.** A frequency ("hooguit een paar keer per
  jaar") and a subject ("teamfuncties, de NL-gehoste versie, een grote
  nieuwe feature") beat the word "nieuwsbrief", which promises a rhythm
  we have no intention of keeping.
* **Survive a plain-text client.** Both parts carry the bare link, so
  the mail works when the button does not render.

The styling is inline because mail clients strip `<style>` blocks. The
colours are the site's own tokens (`frontend/src/app.css`), copied
rather than imported — a mail cannot read a stylesheet, and pinning them
here means an accidental theme change on the site cannot silently
restyle a mail nobody is looking at.
"""

from __future__ import annotations

import html
from typing import Any

from app.config import settings

# Site tokens, mirrored from `frontend/src/app.css`.
_INK = "#1a1f2c"
_INK_SOFT = "#4a5160"
_INK_MUTE = "#7a8190"
_PRIMARY = "#0f4c5c"
_BG = "#fafaf7"
_BORDER = "#e5e1d8"

_SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif"
_SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Inline styles, named so the template below stays readable. Mail clients
# strip `<style>` blocks, so every rule has to travel on its element.
_PAGE_STYLE = f"margin:0;padding:24px 12px;background:{_BG};font-family:{_SANS};"
_CARD_STYLE = (
    f"max-width:520px;margin:0 auto;background:#ffffff;"
    f"border:1px solid {_BORDER};border-radius:8px;padding:32px;"
)
_H1_STYLE = (
    f"margin:0 0 16px;font-family:{_SERIF};font-size:24px;"
    f"line-height:1.25;color:{_INK};font-weight:normal;"
)
_BODY_STYLE = f"margin:0 0 16px;font-size:15px;line-height:1.6;color:{_INK_SOFT};"
_BODY_LAST_STYLE = f"margin:0 0 24px;font-size:15px;line-height:1.6;color:{_INK_SOFT};"
_BUTTON_STYLE = (
    f"display:inline-block;background:{_INK};color:#ffffff;text-decoration:none;"
    f"font-size:15px;font-weight:500;padding:12px 22px;border-radius:6px;"
)
_FALLBACK_STYLE = (
    f"margin:0 0 28px;font-size:13px;line-height:1.6;color:{_INK_MUTE};word-break:break-all;"
)
_FOOTER_STYLE = (
    f"margin:0;padding-top:20px;border-top:1px solid {_BORDER};"
    f"font-size:13px;line-height:1.6;color:{_INK_MUTE};"
)
_LINK_STYLE = f"color:{_PRIMARY};"

SUBJECT = "Bevestig je e-mailadres voor updates over WOO Buddy"


def confirmation_url(token: str) -> str:
    """The link the recipient clicks. Lands on the site, not on the API."""
    return f"{settings.public_site_url.rstrip('/')}/nieuwsbrief/bevestigen?t={token}"


def _text_body(link: str) -> str:
    return "\n".join(
        [
            "Je hebt op woobuddy.nl aangevinkt dat je af en toe een update wilt",
            "over WOO Buddy. Bevestig je e-mailadres via deze link:",
            "",
            link,
            "",
            "Wat je krijgt: een bericht als er iets te melden is — teamfuncties,",
            "de NL-gehoste versie, of een grote nieuwe functie. Geen vast ritme,",
            "hooguit een paar keer per jaar. Uitschrijven kan met één klik.",
            "",
            "Heb je dit niet zelf aangevraagd? Doe dan niets. Zonder die klik",
            "gebeurt er niets en bewaren we je adres niet.",
            "",
            "WOO Buddy is gemaakt door Bureau Bolster B.V.",
            f"Privacy: {settings.public_site_url.rstrip('/')}/privacy",
        ]
    )


def _html_body(link: str) -> str:
    escaped = html.escape(link, quote=True)
    site = html.escape(settings.public_site_url.rstrip("/"), quote=True)
    return f"""\
<div style="{_PAGE_STYLE}">
  <div style="{_CARD_STYLE}">
    <h1 style="{_H1_STYLE}">
      Bevestig je e-mailadres
    </h1>
    <p style="{_BODY_STYLE}">
      Je hebt op woobuddy.nl aangevinkt dat je af en toe een update wilt over
      WOO&nbsp;Buddy. Eén klik en het staat genoteerd.
    </p>
    <p style="margin:0 0 28px;">
      <a href="{escaped}" style="{_BUTTON_STYLE}">Bevestig e-mailadres</a>
    </p>
    <p style="{_FALLBACK_STYLE}">
      Werkt de knop niet? Plak deze link in je browser:<br />
      <a href="{escaped}" style="{_LINK_STYLE}">{escaped}</a>
    </p>
    <p style="{_BODY_STYLE}">
      <strong style="color:{_INK};">Wat je krijgt:</strong> een bericht als er iets
      te melden is — teamfuncties, de NL-gehoste versie, of een grote nieuwe
      functie. Geen vast ritme, hooguit een paar keer per jaar. Uitschrijven kan
      met één klik.
    </p>
    <p style="{_BODY_LAST_STYLE}">
      Heb je dit niet zelf aangevraagd? Doe dan niets. Zonder die klik gebeurt er
      niets en bewaren we je adres niet.
    </p>
    <p style="{_FOOTER_STYLE}">
      WOO&nbsp;Buddy is gemaakt door Bureau Bolster B.V.
      <a href="{site}/privacy" style="{_LINK_STYLE}">Hoe we met je gegevens omgaan</a>.
    </p>
  </div>
</div>"""


def build_confirmation_payload(email: str, token: str) -> dict[str, Any]:
    """Scaleway TEM `/emails` payload for the double opt-in mail.

    Unlike the operator notification this one carries no Reply-To: the
    From address is already a monitored alias, so a reply lands in the
    right place without a header saying so.
    """
    link = confirmation_url(token)
    return {
        "from": {"email": settings.tem_from_email, "name": settings.tem_from_name},
        "to": [{"email": email}],
        "subject": SUBJECT,
        "html": _html_body(link),
        "text": _text_body(link),
        "project_id": settings.scaleway_project_id,
    }


__all__ = ["SUBJECT", "build_confirmation_payload", "confirmation_url"]
