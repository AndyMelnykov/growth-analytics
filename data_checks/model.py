"""Result types and the Check wrapper. Check.evaluate never raises."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from data_checks.config import CheckConfig
from data_checks.snapshot import Snapshot


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    ERRORED = "errored"


class SkipCheck(Exception):
    """Raised by a check that cannot apply to this snapshot; the message is the reason."""


@dataclass(frozen=True)
class Finding:
    violations: list[str]
    metric: float | None = None


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    title: str
    severity: Severity
    status: Status
    violation_count: int
    samples: tuple[str, ...]
    metric: float | None
    detail: str


@dataclass(frozen=True)
class Check:
    check_id: str
    title: str
    severity: Severity
    fn: Callable[[Snapshot, CheckConfig], Finding]

    def evaluate(self, snap: Snapshot, cfg: CheckConfig) -> CheckResult:
        try:
            finding = self.fn(snap, cfg)
        except SkipCheck as reason:
            return self._result(Status.SKIPPED, detail=str(reason))
        except Exception as exc:  # a broken check must not hide the others
            return self._result(Status.ERRORED, detail=f"{type(exc).__name__}: {exc}")
        violations = finding.violations
        return self._result(
            Status.FAIL if violations else Status.PASS,
            violation_count=len(violations),
            samples=tuple(violations[: cfg.sample_size]),
            metric=finding.metric,
        )

    def _result(
        self,
        status: Status,
        violation_count: int = 0,
        samples: tuple[str, ...] = (),
        metric: float | None = None,
        detail: str = "",
    ) -> CheckResult:
        return CheckResult(
            self.check_id, self.title, self.severity, status, violation_count, samples, metric, detail
        )
