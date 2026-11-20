from __future__ import annotations

import pytest

from funnels.__main__ import main
from funnels.report import GOLD_VIEWS, format_table, render


def test_format_table_aligns_columns_and_formats_values():
    text = format_table(["name", "rate"], [("a", 0.5), ("longer", None), ("c", 3)])
    assert text.splitlines() == [
        "name    rate",
        "------  -----",
        "a       0.500",
        "longer  -",
        "c       3",
    ]


def test_format_table_with_no_rows_still_prints_headers():
    assert format_table(["x", "y"], []).splitlines() == ["x  y", "-  -"]


def test_render_prints_a_section_per_view(con):
    text = render(con)
    for view in GOLD_VIEWS:
        assert f"## {view}" in text


def test_render_single_view(con):
    text = render(con, ["gold_habit_threshold"])
    assert text.startswith("## gold_habit_threshold")
    assert "gold_acquisition_funnel" not in text


def test_gold_views_all_exist_and_are_queryable(query):
    for view in GOLD_VIEWS:
        query(f"select * from {view}")


def test_cli_prints_report(raw_dir, capsys):
    assert main(["--raw-dir", str(raw_dir)]) == 0
    out = capsys.readouterr().out
    assert "## gold_acquisition_funnel" in out
    assert "referral" in out


def test_cli_view_filter(raw_dir, capsys):
    assert main(["--raw-dir", str(raw_dir), "--view", "gold_activation_funnel"]) == 0
    out = capsys.readouterr().out
    assert "## gold_activation_funnel" in out
    assert "## gold_habit_curve" not in out


def test_cli_rejects_unknown_view(raw_dir):
    with pytest.raises(SystemExit):
        main(["--raw-dir", str(raw_dir), "--view", "users; drop table params"])


def test_cli_can_persist_the_warehouse(raw_dir, tmp_path, capsys):
    db = tmp_path / "wh.duckdb"
    assert main(["--raw-dir", str(raw_dir), "--db", str(db), "--view", "gold_habit_threshold"]) == 0
    capsys.readouterr()
    assert db.exists()
