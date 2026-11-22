"""Turn (source, target, weight) rows into an igraph.Graph.

igraph is imported lazily so the repo installs and runs without the optional
`graph` extra; the error appears only when `build_graph` is called.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import igraph


class GraphInputError(ValueError):
    """Raised when an edge row has a missing endpoint or an unusable weight."""


def _validated_weight(weight: object, edge: tuple) -> float:
    try:
        value = float(weight)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise GraphInputError(f"invalid weight {weight!r} in edge {edge!r}: not a number") from exc
    if not math.isfinite(value) or value < 0:
        raise GraphInputError(f"invalid weight {weight!r} in edge {edge!r}: must be finite and >= 0")
    return value


def build_graph(
    edges: Iterable[tuple[Hashable, Hashable, float]], directed: bool = True
) -> "igraph.Graph":
    """Build a graph with vertex attribute `name` and edge attribute `weight`.

    Vertices are created in first-seen order. Duplicate edges are merged by
    summing weights (for undirected graphs `(a, b)` and `(b, a)` are the same
    edge). Self-loops are kept. Empty input gives an empty graph.
    """
    try:
        import igraph
    except ImportError as exc:
        raise ImportError(
            'The igraph package is not installed. Install with: pip install -e ".[graph]"'
        ) from exc

    ids: dict[Hashable, int] = {}
    totals: dict[object, float] = {}
    pairs: dict[object, tuple[int, int]] = {}

    for edge in edges:
        source, target, raw_weight = edge
        if source is None or target is None:
            raise GraphInputError(f"missing endpoint in edge {edge!r}")
        weight = _validated_weight(raw_weight, edge)

        u = ids.setdefault(source, len(ids))
        v = ids.setdefault(target, len(ids))
        key = (u, v) if directed else frozenset((u, v))
        if key in totals:
            totals[key] += weight
        else:
            totals[key] = weight
            pairs[key] = (u, v)

    graph = igraph.Graph(n=len(ids), edges=list(pairs.values()), directed=directed)
    graph.vs["name"] = list(ids)
    graph.es["weight"] = list(totals.values())
    return graph
