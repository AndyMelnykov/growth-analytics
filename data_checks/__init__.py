"""Consistency checks for the raw files in data/raw.

This package only defines the checks and how to load and evaluate them; running
them (cron, CI, an exit code) is left to the caller. See docs/data_checks.md.
"""
from data_checks import checks  # noqa: F401  (registers every check)
from data_checks.config import DEFAULT_RAW_DIR, CheckConfig
from data_checks.model import Check, CheckResult, Finding, Severity, SkipCheck, Status
from data_checks.registry import all_checks, check, get_check
from data_checks.snapshot import Snapshot, load_snapshot, row_counts

__all__ = [
    "DEFAULT_RAW_DIR",
    "Check",
    "CheckConfig",
    "CheckResult",
    "Finding",
    "Severity",
    "SkipCheck",
    "Snapshot",
    "Status",
    "all_checks",
    "check",
    "get_check",
    "load_snapshot",
    "row_counts",
]
