import sys

import pytest

from graph.build import GraphInputError, build_graph

igraph = pytest.importorskip("igraph")


def test_builds_directed_graph_with_names_and_weights():
    g = build_graph([("a", "b", 2), ("b", "c", 1)])
    assert g.is_directed()
    assert g.vs["name"] == ["a", "b", "c"]
    assert [(g.vs[e.source]["name"], g.vs[e.target]["name"]) for e in g.es] == [("a", "b"), ("b", "c")]
    assert g.es["weight"] == [2.0, 1.0]


def test_duplicate_edges_sum_weights():
    g = build_graph([("a", "b", 1), ("a", "b", 2)])
    assert g.ecount() == 1 and g.es["weight"] == [3.0]


def test_directed_keeps_reverse_edges_separate():
    assert build_graph([("a", "b", 1), ("b", "a", 2)]).ecount() == 2


def test_undirected_merges_reverse_edges():
    g = build_graph([("a", "b", 1), ("b", "a", 2)], directed=False)
    assert not g.is_directed() and g.ecount() == 1 and g.es["weight"] == [3.0]


def test_self_loop_is_kept():
    g = build_graph([("a", "a", 4)])
    assert g.vcount() == 1 and g.ecount() == 1 and g.is_loop() == [True]


def test_empty_edges_gives_empty_graph():
    g = build_graph([])
    assert (g.vcount(), g.ecount()) == (0, 0)


@pytest.mark.parametrize("edge", [(None, "b", 1), ("a", None, 1)])
def test_null_endpoint_is_rejected(edge):
    with pytest.raises(GraphInputError, match="endpoint"):
        build_graph([edge])


@pytest.mark.parametrize("weight", [None, float("nan"), float("inf"), -1])
def test_bad_weight_is_rejected(weight):
    with pytest.raises(GraphInputError, match="weight"):
        build_graph([("a", "b", weight)])


def test_zero_weight_is_accepted():
    assert build_graph([("a", "b", 0)]).es["weight"] == [0.0]


def test_duckdb_rows_roundtrip_and_algorithms_run():
    duckdb = pytest.importorskip("duckdb")
    rows = duckdb.connect().execute(
        "select * from (values ('a','b',3),('b','c',1),('c','a',1)) t(src, dst, n)"
    ).fetchall()
    g = build_graph(rows)
    assert g.es["weight"] == [3.0, 1.0, 1.0]
    assert sum(g.pagerank(weights="weight")) == pytest.approx(1.0)


def test_decimal_weights_are_accepted():
    from decimal import Decimal

    assert build_graph([("a", "b", Decimal("2.5"))]).es["weight"] == [2.5]


def test_module_imports_without_igraph_and_build_graph_explains(monkeypatch):
    monkeypatch.setitem(sys.modules, "igraph", None)  # simulate the extra not installed
    with pytest.raises(ImportError, match=r"\.\[graph\]"):
        build_graph([("a", "b", 1)])
