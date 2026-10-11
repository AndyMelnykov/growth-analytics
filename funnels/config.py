"""Tunable definitions for the funnel analytics.

Every window and threshold the SQL uses lives here, so changing a definition is
a one-line edit and tests can override it. Day indexes count days since signup:
day 0 is the signup date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"


@dataclass(frozen=True)
class Params:
    # "Early behavior" is what a user did on day 0 .. early_window_days - 1.
    early_window_days: int = 14
    # Conversion outcome horizon, both from signup and from the landmark.
    outcome_window_days: int = 30
    # Habit outcome: active on >= retained_min_active_days distinct days in
    # [retained_from_day, retained_to_day).
    retained_from_day: int = 28
    retained_to_day: int = 56
    retained_min_active_days: int = 2
    # Habit moment = smallest early-activity bucket whose retention interval
    # lower bound reaches this level.
    habit_target_retention: float = 0.80
    # Groups smaller than this are flagged low_n.
    min_group_size: int = 30
    # Observation ends. None means "use the latest event / conversion date in
    # the data". Windows that extend past these dates are treated as unobserved.
    usage_end: date | None = None
    conversion_end: date | None = None
