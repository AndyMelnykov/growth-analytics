# Graph (igraph)

In-process graph analysis on top of the DuckDB warehouse. See
[ADR 0010](../docs/adr/0010-igraph-replaces-memgraph.md) for why igraph. The
rest of the repository does not need any of this.

## Setup

```bash
pip install -e ".[graph,funnels,dev]"
```

Windows needs nothing else: igraph installs from a prebuilt wheel.

## Usage

`graph.build.build_graph` turns `(source, target, weight)` rows into an
`igraph.Graph` with vertex attribute `name` and edge attribute `weight`:

```python
import duckdb

from graph.build import build_graph

rows = duckdb.connect().execute(
    "select * from (values ('a','b',3),('b','c',1),('c','a',1)) t(src, dst, n)"
).fetchall()

g = build_graph(rows)
print(g.vs["name"])                      # ['a', 'b', 'c']
print(g.pagerank(weights="weight"))      # one score per vertex
```

In real use, replace the `values` query with a query against the `funnels`
warehouse that returns the same three columns.

## Tests

```bash
pytest graph/tests
```

Every `pytest` run writes a JUnit report to `docs/test-reports/junit.xml`
(tracked in git, overwritten by the latest run). Commit it when you want to
record a result.

## Notes

- The graph is in memory and rebuilt on demand; nothing is persisted.
- `build_graph` creates vertices in first-seen order, sums the weights of
  duplicate edges (for `directed=False`, `(a, b)` and `(b, a)` are the same
  edge) and keeps self-loops.
- Missing endpoints and NULL, NaN, infinite or negative weights raise
  `GraphInputError`. `int` and `Decimal` weights, as DuckDB returns them, are
  stored as float.
- igraph is imported when `build_graph` is called, so `import graph.build`
  works without the extra; calling it without igraph raises an `ImportError`
  that names the install command.

## Usage-to-purchase analysis

`graph.usage_conversion` measures which free-period usage patterns raise or
lower purchases (and expansion, contraction and cancellation after purchase)
from `feature_usage_events`, `conversions` and `subscription_events`:

```bash
python -m graph.usage_conversion --out usage_conversion.json \
    --deck docs/reports/usage-to-purchase-deck.html
```

- Time-aware: a behaviour counts only from the day after it first happens, so
  usage after a purchase never explains it. Rates are compared within
  days-since-signup band x signup month and pooled as a Mantel-Haenszel rate
  ratio with a 95% interval, plus a stricter Bonferroni-style flag.
- Journey graph: pre-purchase event sequences are built with `build_graph`
  and solved as an absorbing Markov chain (P(buy) per feature, removal effect).
- `--deck` fills `graph/report/usage_conversion_deck.html` with the results and
  writes a self-contained HTML slide deck. Needs the `graph` and `funnels` extras.

## Migrating from Memgraph

Earlier checkouts shipped a Memgraph Docker Compose stack. If you ran it,
remove its resources from a checkout that still has `docker-compose.yml`:

```bash
docker compose --profile ui down -v --rmi all --remove-orphans
```

If the compose file is already gone, remove the leftovers directly:

```bash
docker volume rm growth-analytics_memgraph_data
docker rmi memgraph/memgraph-mage:3.13.1 memgraph/lab:3.13.2
```

You can also delete your local `.env` (it held `MEMGRAPH_*` settings).
