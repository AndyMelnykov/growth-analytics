"""Shared fixtures. Integration tests skip cleanly when Memgraph is unavailable."""

import os
from pathlib import Path

import pytest

from graph.connection import MemgraphConfigError, MemgraphSettings, get_driver, healthcheck


def _load_dotenv() -> None:
    """Populate os.environ from the repo-root .env without overriding real env vars."""
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()


@pytest.fixture(scope="session")
def driver():
    try:
        settings = MemgraphSettings.from_env()
    except MemgraphConfigError as exc:
        pytest.skip(f"Memgraph not configured: {exc}")
    try:
        drv = get_driver(settings)
    except ImportError as exc:
        pytest.skip(str(exc))
    if not healthcheck(drv):
        drv.close()
        pytest.skip(f"Memgraph not reachable at {settings.uri}")
    yield drv
    drv.close()
