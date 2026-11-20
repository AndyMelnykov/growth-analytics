"""python -m funnels: build the warehouse and print the Gold views."""
from __future__ import annotations

import argparse
from pathlib import Path

from funnels.config import DEFAULT_RAW_DIR
from funnels.report import GOLD_VIEWS, render
from funnels.warehouse import build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m funnels",
        description="Build the funnel analytics warehouse and print the Gold views.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR,
                        help="directory with the raw files (default: data/raw)")
    parser.add_argument("--db", type=Path, default=None,
                        help="also persist the warehouse to this DuckDB file")
    parser.add_argument("--view", action="append", choices=GOLD_VIEWS,
                        help="print only this view (repeatable)")
    args = parser.parse_args(argv)

    con = build(args.raw_dir, db_path=args.db)
    try:
        print(render(con, args.view))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
