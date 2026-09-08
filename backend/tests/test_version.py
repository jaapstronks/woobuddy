"""The running version is readable and reported (#101).

`deploy/deploy.sh` asserts against `/api/health` after a deploy, so a
missing or malformed `version` field is a deploy that reports success
while nobody can tell what is live.
"""

import re
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.version import DEV_VERSION, get_version

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_get_version_returns_semver_or_dev() -> None:
    version = get_version()
    assert version == DEV_VERSION or SEMVER.match(version), version


def test_get_version_falls_back_to_dev_without_package_metadata() -> None:
    """A dev virtualenv running uvicorn against the source tree has no
    installed distribution to read, and must still answer."""
    from importlib.metadata import PackageNotFoundError

    with patch("app.version.package_version", side_effect=PackageNotFoundError):
        assert get_version() == DEV_VERSION


@pytest.mark.asyncio
async def test_health_reports_the_version() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == get_version()
