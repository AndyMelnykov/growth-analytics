"""Registration of checks under stable IDs."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from data_checks.config import CheckConfig
from data_checks.model import Check, Finding, Severity
from data_checks.snapshot import Snapshot

F = TypeVar("F", bound=Callable[[Snapshot, CheckConfig], Finding])

_REGISTRY: dict[str, Check] = {}


def check(check_id: str, title: str, severity: Severity) -> Callable[[F], F]:
    """Decorator: register `fn` as check `check_id` and return it unchanged."""

    def register(fn: F) -> F:
        if check_id in _REGISTRY:
            raise ValueError(f"duplicate check id: {check_id}")
        _REGISTRY[check_id] = Check(check_id, title, severity, fn)
        return fn

    return register


def all_checks() -> list[Check]:
    return [_REGISTRY[check_id] for check_id in sorted(_REGISTRY)]


def get_check(check_id: str) -> Check:
    return _REGISTRY[check_id]
