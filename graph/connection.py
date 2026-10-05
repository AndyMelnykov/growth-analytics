"""Connection helpers for Memgraph over Bolt.

Settings come only from MEMGRAPH_* environment variables. The `neo4j` driver
is imported lazily so that importing this module works without the optional
`graph` extra installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

_REQUIRED = ("MEMGRAPH_HOST", "MEMGRAPH_PORT", "MEMGRAPH_USER", "MEMGRAPH_PASSWORD")


class MemgraphConfigError(ValueError):
    """Raised when MEMGRAPH_* environment configuration is missing or invalid."""


@dataclass(frozen=True)
class MemgraphSettings:
    host: str
    port: int
    user: str
    password: str = field(repr=False)

    @property
    def uri(self) -> str:
        return f"bolt://{self.host}:{self.port}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MemgraphSettings":
        env = os.environ if env is None else env
        missing = [name for name in _REQUIRED if not env.get(name)]
        if missing:
            raise MemgraphConfigError(
                "Missing required environment variable(s): " + ", ".join(missing)
            )
        raw_port = env["MEMGRAPH_PORT"]
        try:
            port = int(raw_port)
        except ValueError:
            raise MemgraphConfigError(
                f"MEMGRAPH_PORT must be an integer, got {raw_port!r}"
            ) from None
        if not 1 <= port <= 65535:
            raise MemgraphConfigError(f"MEMGRAPH_PORT out of range: {port}")
        return cls(
            host=env["MEMGRAPH_HOST"],
            port=port,
            user=env["MEMGRAPH_USER"],
            password=env["MEMGRAPH_PASSWORD"],
        )


def get_driver(settings: MemgraphSettings | None = None):
    """Build a neo4j Bolt driver for Memgraph. Caller must close it."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ImportError(
            "The neo4j driver is not installed. Install with: pip install -e '.[graph]'"
        ) from exc
    settings = settings or MemgraphSettings.from_env()
    return GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))


def healthcheck(driver) -> bool:
    """True if the server answers over Bolt with valid credentials; never raises."""
    try:
        driver.verify_connectivity()
        return True
    except Exception:
        return False
