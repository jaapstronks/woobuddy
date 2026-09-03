"""Round-trip tests for the newsletter confirmation token (#76).

The token is the only thing standing between "someone typed an address
into a form" and "that address is on a mailing list", so the cases that
matter are the ones where it must *refuse*: a tampered payload, a
signature from a different secret, and a link that sat in an inbox too
long.

`make_token` / `read_token` both take an explicit `now`, so expiry is
tested by arithmetic rather than by sleeping.
"""

from __future__ import annotations

import base64
import json

import pytest

from app.services.lead_tokens import (
    DEFAULT_TTL_SECONDS,
    ExpiredTokenError,
    InvalidTokenError,
    make_token,
    read_token,
)

SECRET = "test-confirm-secret"
NOW = 1_756_800_000


def _payload_of(token: str) -> dict[str, object]:
    encoded = token.split(".", 1)[0]
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded))
    assert isinstance(decoded, dict)
    return decoded


def _retoken(payload: dict[str, object], signature: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"{encoded}.{signature}"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_round_trip_returns_the_original_address() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, now=NOW)
    assert read_token(token, secret=SECRET, now=NOW + 60) == "jaap@example.nl"


def test_token_is_url_safe() -> None:
    """It travels in a query string, so no padding and no +/ characters."""
    token = make_token("a+b@example.nl", secret=SECRET, now=NOW)
    assert "=" not in token
    assert "+" not in token
    assert "/" not in token


def test_payload_carries_only_address_and_expiry() -> None:
    """No source, no name, no organization — the list only needs an address."""
    payload = _payload_of(make_token("jaap@example.nl", secret=SECRET, now=NOW))
    assert payload == {"e": "jaap@example.nl", "x": NOW + DEFAULT_TTL_SECONDS}


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


def test_token_is_valid_up_to_the_last_second() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, ttl_seconds=100, now=NOW)
    assert read_token(token, secret=SECRET, now=NOW + 99) == "jaap@example.nl"


def test_token_expires_exactly_at_its_expiry() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, ttl_seconds=100, now=NOW)
    with pytest.raises(ExpiredTokenError):
        read_token(token, secret=SECRET, now=NOW + 100)


def test_default_ttl_is_two_days() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, now=NOW)
    read_token(token, secret=SECRET, now=NOW + DEFAULT_TTL_SECONDS - 1)
    with pytest.raises(ExpiredTokenError):
        read_token(token, secret=SECRET, now=NOW + DEFAULT_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Tampering
# ---------------------------------------------------------------------------


def test_swapping_the_address_invalidates_the_signature() -> None:
    """The attack the HMAC exists to stop: subscribe someone else's address."""
    token = make_token("jaap@example.nl", secret=SECRET, now=NOW)
    payload = _payload_of(token)
    payload["e"] = "victim@example.nl"
    forged = _retoken(payload, token.split(".", 1)[1])

    with pytest.raises(InvalidTokenError):
        read_token(forged, secret=SECRET, now=NOW + 60)


def test_extending_the_expiry_invalidates_the_signature() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, ttl_seconds=100, now=NOW)
    payload = _payload_of(token)
    assert isinstance(payload["x"], int)
    payload["x"] = payload["x"] + 10_000
    forged = _retoken(payload, token.split(".", 1)[1])

    with pytest.raises(InvalidTokenError):
        read_token(forged, secret=SECRET, now=NOW + 60)


def test_a_different_secret_does_not_verify() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, now=NOW)
    with pytest.raises(InvalidTokenError):
        read_token(token, secret="another-secret", now=NOW + 60)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "no-separator",
        ".onlysignature",
        "onlypayload.",
        "!!!not-base64!!!.abc",
        "payload.sign\u00e9ture",
        "p\u00e9yload.signature",
    ],
)
def test_malformed_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        read_token(token, secret=SECRET, now=NOW)


def test_correctly_signed_but_shapeless_payloads_are_rejected() -> None:
    """A signed payload is still checked: the secret could leak one day."""
    from app.services.lead_tokens import _b64encode, _sign  # noqa: PLC0415

    for raw in (b'"a string"', b"[1,2]", b'{"x":123}', b'{"e":""}', b'{"e":"a@b.nl","x":true}'):
        encoded = _b64encode(raw)
        with pytest.raises(InvalidTokenError):
            read_token(f"{encoded}.{_sign(SECRET, encoded)}", secret=SECRET, now=NOW)


# ---------------------------------------------------------------------------
# Missing configuration
# ---------------------------------------------------------------------------


def test_minting_without_a_secret_raises() -> None:
    """Fail loudly rather than hand out a token anyone could forge."""
    with pytest.raises(ValueError):
        make_token("jaap@example.nl", secret="")


def test_reading_without_a_secret_is_invalid_not_a_crash() -> None:
    token = make_token("jaap@example.nl", secret=SECRET, now=NOW)
    with pytest.raises(InvalidTokenError):
        read_token(token, secret="", now=NOW + 60)
