"""Every threshold the checks use, in one place.

Defaults were calibrated on the 2024 snapshot in data/raw (see
docs/superpowers/plans/2026-11-26-data-consistency-checks.md) so that a clean
snapshot raises nothing; override per run with dataclasses.replace().
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"


@dataclass(frozen=True)
class CheckConfig:
    # E4: every date must fall in [window_start, min(window_end, as_of or today)].
    window_start: date = date(2023, 12, 1)
    window_end: date = date(2024, 12, 31)
    as_of: date | None = None
    # E1: first touch may precede signup by at most this many days.
    max_touch_lag_days: int = 30
    # F5: inclusive MRR range per plan.
    plan_mrr_bands: Mapping[str, tuple[int, int]] = field(
        default_factory=lambda: {"pro": (29, 1986), "enterprise": (199, 9957)}
    )
    # G1: previous row counts per source (None = no baseline) and the allowed relative change.
    baseline_row_counts: Mapping[str, int] | None = None
    row_count_tolerance: float = 0.20
    # G2: sources expected to have rows every day, the longest allowed run of empty days,
    # and how many times the median daily count counts as a spike.
    dense_sources: tuple[str, ...] = ("user_signups", "feature_usage_events")
    max_gap_days: int = 2
    spike_factor: float = 5.0
    # G3, G4, G5, D5: shares measured on the data, with their allowed band or maximum.
    unattributed_share_band: tuple[float, float] = (0.03, 0.07)
    max_converters_without_usage_share: float = 0.15
    max_usage_after_cancel_share: float = 0.60
    max_rtc_first_use_after_conversion_share: float = 0.15
    # G6: engineered signal direction (ADR 0004); None disables the check.
    best_channel: str | None = "referral"
    worst_channels: tuple[str, ...] | None = ("outbound", "paid_social")
    # How many violation examples a result keeps.
    sample_size: int = 5
