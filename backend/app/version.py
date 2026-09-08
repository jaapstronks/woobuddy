"""The running WOO Buddy version.

Read from the installed package metadata rather than from a constant, so
there is exactly one place the number lives: `VERSION` in the repository
root, which release-please keeps in step with `backend/pyproject.toml`.
See `docs/reference/versioning.md`.

The production image does `pip install .`, so the metadata is present
there. A development virtualenv that runs uvicorn against the source tree
without installing the package has no metadata to read; that reports
"dev", which is the honest answer and keeps `/api/health` a 200.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

DEV_VERSION = "dev"


def get_version() -> str:
    """Return the installed version, or `"dev"` when not installed."""
    try:
        return package_version("woobuddy-backend")
    except PackageNotFoundError:
        return DEV_VERSION
