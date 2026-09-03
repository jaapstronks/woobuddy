"""Stateless confirmation tokens for the newsletter double opt-in (#76).

WOO Buddy sends its own confirmation mail rather than letting Listmonk
send one (Listmonk's opt-in mail, sender and public pages are
instance-global, and the instance is shared with another brand). That
means we need to recognise the address again when the recipient clicks
the link in that mail, minutes or hours later.

We do that **without storing anything**. The token carries the address
and an expiry, signed with an HMAC over a server-side secret:

    <base64url(payload json)>.<base64url(hmac-sha256)>

Nothing about it needs a database row, which keeps the promise the repo
makes elsewhere: Listmonk is the system of record for the audience list,
and no visitor PII lands in Postgres. The trade-off is that a token
cannot be revoked before it expires — acceptable for a 48-hour window
whose only power is "add this address to a mailing list".

The signature covers the encoded payload, not the raw JSON, so there is
no room for an encoder that renders two different payloads identically.
Verification is constant-time and rejects the expired case separately,
because the confirmation page says something different for a link that
merely went stale than for one that never was ours.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

# Two days is long enough that a mail read the next morning still works,
# short enough that a forwarded link does not stay live indefinitely.
DEFAULT_TTL_SECONDS = 48 * 60 * 60


class TokenError(Exception):
    """Base for every reason a confirmation token is not usable."""


class InvalidTokenError(TokenError):
    """Malformed, truncated, or signed with a different secret."""


class ExpiredTokenError(TokenError):
    """Well-formed and correctly signed, but past its expiry."""


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 without padding — the token travels in a query string."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    """Reverse `_b64encode`, restoring the padding it stripped."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(secret: str, encoded_payload: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def make_token(
    email: str,
    *,
    secret: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """Mint a confirmation token for `email`, valid for `ttl_seconds`.

    Raises `ValueError` on an empty secret rather than signing with one:
    an unsigned token would be forgeable by anyone who can read the URL
    shape, which is the whole thing the HMAC exists to prevent.
    """
    if not secret:
        raise ValueError("cannot mint a confirmation token without a secret")

    issued_at = int(time.time()) if now is None else now
    payload = json.dumps(
        {"e": email, "x": issued_at + ttl_seconds},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = _b64encode(payload)
    return f"{encoded}.{_sign(secret, encoded)}"


def read_token(token: str, *, secret: str, now: int | None = None) -> str:
    """Return the address inside `token`, or raise.

    Raises `InvalidTokenError` when the shape, the signature or the payload is
    wrong, and `ExpiredTokenError` when a genuine token has aged out.
    """
    if not secret:
        raise InvalidTokenError("no confirmation secret configured")

    encoded, separator, signature = token.partition(".")
    if not separator or not encoded or not signature:
        raise InvalidTokenError("token is not <payload>.<signature>")

    if not hmac.compare_digest(signature, _sign(secret, encoded)):
        raise InvalidTokenError("signature mismatch")

    # Only now is the payload worth parsing: it is attacker-supplied until
    # the signature says otherwise.
    try:
        payload = json.loads(_b64decode(encoded))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidTokenError("payload is not decodable JSON") from exc

    if not isinstance(payload, dict):
        raise InvalidTokenError("payload is not an object")

    email = payload.get("e")
    expires_at = payload.get("x")
    if not isinstance(email, str) or not email:
        raise InvalidTokenError("payload carries no address")
    # `bool` is an `int` subclass; exclude it so `{"x": true}` cannot pass.
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise InvalidTokenError("payload carries no expiry")

    if (int(time.time()) if now is None else now) >= expires_at:
        raise ExpiredTokenError("token has expired")

    return email


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ExpiredTokenError",
    "InvalidTokenError",
    "TokenError",
    "make_token",
    "read_token",
]
