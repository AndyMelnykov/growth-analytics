"""Plain-text rendering of the Gold views."""
from __future__ import annotations

import duckdb

GOLD_VIEWS = [
    "gold_acquisition_funnel",
    "gold_acquisition_cohorts",
    "gold_activation_funnel",
    "gold_aha_features",
    "gold_aha_feature_lift",
    "gold_aha_behaviors",
    "gold_habit_curve",
    "gold_habit_threshold",
    "gold_usage_retention",
]


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def format_table(columns: list[str], rows: list[tuple]) -> str:
    cells = [[_fmt(v) for v in row] for row in rows]
    widths = [max([len(col)] + [len(r[i]) for r in cells]) for i, col in enumerate(columns)]

    def line(parts: list[str]) -> str:
        return "  ".join(p.ljust(w) for p, w in zip(parts, widths)).rstrip()

    return "\n".join(
        [line(list(columns)), line(["-" * w for w in widths]), *[line(r) for r in cells]]
    )


def render(con: duckdb.DuckDBPyConnection, views: list[str] | None = None) -> str:
    blocks = []
    for view in views or GOLD_VIEWS:
        if view not in GOLD_VIEWS:  # view names are interpolated into SQL below
            raise ValueError(f"unknown view: {view}")
        cursor = con.execute(f"select * from {view}")
        columns = [d[0] for d in cursor.description]
        blocks.append(f"## {view}\n{format_table(columns, cursor.fetchall())}")
    return "\n\n".join(blocks)
