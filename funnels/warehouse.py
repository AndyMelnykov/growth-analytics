"""Build the analytics warehouse: params table + the SQL files in order."""
from __future__ import annotations

from pathlib import Path

import duckdb

from funnels.config import DEFAULT_RAW_DIR, Params

SQL_DIR = Path(__file__).parent / "sql"
RAW_DIR_TOKEN = "{{RAW_DIR}}"


def _create_params_table(con: duckdb.DuckDBPyConnection, p: Params) -> None:
    con.execute(
        """
        create or replace table params as select
            cast(? as INTEGER) as early_window_days,
            cast(? as INTEGER) as outcome_window_days,
            cast(? as INTEGER) as retained_from_day,
            cast(? as INTEGER) as retained_to_day,
            cast(? as INTEGER) as retained_min_active_days,
            cast(? as DOUBLE)  as habit_target_retention,
            cast(? as INTEGER) as min_group_size,
            cast(? as DATE)    as usage_end,
            cast(? as DATE)    as conversion_end
        """,
        [
            p.early_window_days,
            p.outcome_window_days,
            p.retained_from_day,
            p.retained_to_day,
            p.retained_min_active_days,
            p.habit_target_retention,
            p.min_group_size,
            p.usage_end,
            p.conversion_end,
        ],
    )


def build(
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    params: Params | None = None,
    db_path: Path | str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Return a connection with every Bronze/Silver/Gold object created.

    The warehouse is in memory unless db_path is given. Raw files are only read.
    """
    raw = Path(raw_dir)
    if not raw.is_dir():
        raise FileNotFoundError(f"raw data directory not found: {raw}")
    raw_posix = raw.resolve().as_posix().replace("'", "''")

    con = duckdb.connect(str(db_path) if db_path else ":memory:")
    _create_params_table(con, params or Params())
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8").replace(RAW_DIR_TOKEN, raw_posix))
    return con
