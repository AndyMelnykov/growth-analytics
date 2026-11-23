# Replace Memgraph with igraph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Memgraph/Docker/Bolt stack and make `igraph` the repo's graph-analysis dependency, with a small tested helper that turns query rows into an `igraph.Graph`.

**Architecture:** igraph runs in-process: no server, no credentials, no Docker. DuckDB (the `funnels` warehouse) stays the source of rows; the graph is rebuilt in memory on demand and nothing is persisted. `graph/build.py` is the single seam between rows and `igraph.Graph`, so a later move to NetworkX or back to a graph database touches one module. igraph is imported lazily so the repo still installs and runs without the optional `graph` extra.

**Tech Stack:** Python >= 3.10 (3.13.7 on this machine, Windows), `igraph` (pinned to a minor range, optional extra `graph`), DuckDB (existing `funnels` extra), pytest, setuptools.

**Spec:** No separate design doc. Requirements come from the conversation that produced this plan ("simpler option than Memgraph for graph and dependency analysis on the project data, runnable on Windows"). The decision is recorded as ADR 0010 in Task 3. The code this replaces is described by [the Memgraph plan](2026-10-04-memgraph-dependency.md) and [ADR 0008](../../adr/0008-memgraph-graph-analysis.md), both kept as history.

## Global Constraints

- Base the work on `origin/main`, not on the old `feat/memgraph-dependency` branch: `main` already contains the funnel work, and ADR 0009 is taken, so the new ADR is **0010**.
- Package `igraph` (PyPI name `igraph`, import name `igraph`), pinned to a minor range `>=X.Y,<X.(Y+1)` in optional extra `graph`. It must install from a prebuilt Windows wheel on Python 3.13 (`pip install --only-binary=:all:`), never from source.
- The base install (`pip install -e .`) must not require igraph. `import graph` and `import graph.build` must work without it; the error appears only when `build_graph` is called.
- Graph shape: vertex attribute `name`, edge attribute `weight` (float). No graph model, schema, loader or algorithms beyond what Task 2 specifies (out of scope: feature-transition or co-usage analysis, Cypher, persistence, NetworkX comparison).
- No Docker, compose, `.env`, `MEMGRAPH_*` or `neo4j` references remain in code, config or current docs. Historical documents (ADR 0008, the 2026-10-03 spec, the 2026-10-04 plan) keep their text and gain only a "superseded" note.
- ADR 0010 uses the existing format (Status / Context / Decision / Consequences) and marks ADR 0008 as superseded.
- Never stage `.vscode/settings.json`; it has unrelated local changes.
- `pytest` writes `docs/test-reports/junit.xml` on every run (tracked; `addopts` in `pyproject.toml`). Commit a fresh copy in Task 3 only.

## Review Focus

- Docker teardown order: `docker compose down -v --rmi all` must run **before** `docker-compose.yml` is deleted, otherwise the `growth-analytics_memgraph_data` volume and the Memgraph images are orphaned on the user's disk with no compose file left to remove them. Task 1 Step 2.
- Empty edge list: `build_graph([])` returns an empty graph (0 vertices, 0 edges), not an error. Task 2.
- Duplicate edges and self-loops from SQL (`A -> A` transitions are real behavior): duplicates sum their weights, self-loops are kept. Task 2.
- NULL endpoints, and NULL / NaN / infinite / negative weights coming out of SQL: rejected with a `GraphInputError` naming the problem, never silently dropped or turned into a bad graph. Task 2.
- DuckDB returns weights as `int` (counts) or `Decimal`: they must be accepted and stored as float. Task 2.
- `import graph.build` with igraph not installed: succeeds; `build_graph` raises an `ImportError` that tells the user to install the `graph` extra. Task 2.
- A leftover reference to Memgraph in current docs or config would send a new reader to a stack that no longer exists. Task 3 Step 6 greps for it.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | `graph` extra becomes igraph; `integration` marker removed |
| `graph/__init__.py` | Package marker with updated docstring; imports nothing heavy |
| `graph/build.py` | `GraphInputError`, `build_graph` |
| `graph/tests/test_build.py` | Docker-free tests of `build_graph` |
| `graph/README.md` | igraph setup, usage, migration note (rewritten) |
| `docs/adr/0010-igraph-replaces-memgraph.md` | Decision record (new) |
| `docs/adr/0008-memgraph-graph-analysis.md` | Status line only |
| `docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md`, `docs/superpowers/plans/2026-10-04-memgraph-dependency.md` | One superseded note each |
| `README.md`, `references.md` | Pointers updated |
| Deleted | `docker-compose.yml`, `.env.example`, `graph/connection.py`, `graph/tests/conftest.py`, `graph/tests/test_connection.py`, `graph/tests/test_connection_unit.py`, local untracked `.env` |

---

### Task 1: Retire the Memgraph stack and swap the dependency

**Files:**
- Delete: `docker-compose.yml`, `.env.example`, `graph/connection.py`, `graph/tests/conftest.py`, `graph/tests/test_connection.py`, `graph/tests/test_connection_unit.py`, local `.env`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable project whose `graph` extra is igraph, a `.venv` with igraph and without neo4j, and a green `pytest` run (funnels tests only; `graph/tests` has no tests yet).

- [ ] **Step 1: Create an isolated branch from `origin/main`**

The main checkout has unrelated local changes (`.vscode/settings.json`) and untracked copies of two files that now exist on `origin/main`, which blocks switching branches there. Use a worktree (superpowers:using-git-worktrees):

```bash
cd /c/Projects/analytics/growth-analytics
git fetch origin
git worktree add ../growth-analytics-igraph -b feat/igraph-replace-memgraph origin/main
cd ../growth-analytics-igraph
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
cp ../growth-analytics/docs/superpowers/plans/2026-11-22-replace-memgraph-with-igraph.md docs/superpowers/plans/
```
Expected: the worktree is on `feat/igraph-replace-memgraph` at the `origin/main` commit and contains `funnels/`, `docs/adr/0009-*.md` and `docker-compose.yml`. All later commands run from this worktree. The plan file copied in is committed in Task 3.

- [ ] **Step 2: Tear down the old Docker resources before deleting the compose file**

Start Docker Desktop first. The graph is empty (README: "no graph model or data has been loaded"); confirm by looking before deleting:

```bash
docker compose ps -a
docker compose --profile ui down -v --rmi all --remove-orphans
docker volume ls --filter name=growth-analytics
docker images "memgraph/*"
```
Expected: the last two commands list nothing. If Docker is not installed or you choose not to start it, skip this step and record the leftovers for the user: volume `growth-analytics_memgraph_data` and images `memgraph/memgraph-mage:3.13.1`, `memgraph/lab:3.13.2`, removable later with `docker volume rm` and `docker rmi`.

- [ ] **Step 3: Delete the Memgraph files**

```bash
git rm docker-compose.yml .env.example graph/connection.py graph/tests/conftest.py graph/tests/test_connection.py graph/tests/test_connection_unit.py
rm -f ../growth-analytics/.env
```
Keep `graph/tests/__init__.py` and the `.env` line in `.gitignore` (a harmless guard for future secrets). `graph/README.md` and `graph/__init__.py` are rewritten in later tasks.

- [ ] **Step 4: Find the igraph version to pin**

```bash
.venv/Scripts/python -m pip install --only-binary=:all: igraph
.venv/Scripts/python -m pip show igraph
```
Expected: a `Version: X.Y.Z` line and an install from a wheel with no compiler. If pip tries to build from source or reports no matching wheel, stop: pick the newest igraph release that has a `cp313` `win_amd64` wheel. Use `X.Y` for the range in Step 5.

- [ ] **Step 5: Update `pyproject.toml`**

Replace the `graph` extra with `graph = ["igraph>=X.Y,<X.(Y+1)"]` (range from Step 4). Delete the whole `markers = [...]` entry (the `integration` marker is used only by the deleted tests; `funnels` tests use `skipif` and `parametrize` only). Leave `testpaths`, `addopts`, `funnels` and `dev` extras unchanged. Update the `description` only if it mentions Memgraph (it does not today).

- [ ] **Step 6: Verify the install and the remaining tests**

```bash
.venv/Scripts/python -m pip uninstall -y neo4j
.venv/Scripts/python -m pip install -e ".[graph,funnels,dev]"
.venv/Scripts/python -c "import igraph; print(igraph.__version__)"
.venv/Scripts/python -m pytest -q
```
Expected: install succeeds, the version prints, pytest passes all funnels tests and collects none from `graph/tests`. Then `.venv/Scripts/python -m pip install -e .` must also succeed with no igraph requirement; reinstall `.[graph,funnels,dev]` afterwards.

- [ ] **Step 7: Commit**

```bash
git add -A
git status --short   # confirm .vscode/settings.json and docs/test-reports/junit.xml are NOT staged
git restore --staged docs/test-reports/junit.xml 2>/dev/null; git checkout -- docs/test-reports/junit.xml
git commit -m "build: remove Memgraph Docker stack and switch graph extra to igraph

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: igraph builder (TDD, no Docker)

**Files:**
- Create: `graph/build.py`, `graph/tests/test_build.py`
- Modify: `graph/__init__.py` (docstring only)

**Interfaces:**
- Consumes: `igraph` (lazy import), and `duckdb` in one test (`pytest.importorskip`).
- Produces:
  - `class GraphInputError(ValueError)`
  - `build_graph(edges: Iterable[tuple[Hashable, Hashable, float]], directed: bool = True) -> igraph.Graph`: vertex attribute `name`, edge attribute `weight` (float).
  - Semantics: vertices are created in first-seen order; duplicate edges are merged by summing weights (for `directed=False`, `(a, b)` and `(b, a)` are the same edge); self-loops are kept; empty input gives a graph with 0 vertices and 0 edges.

- [ ] **Step 1: Write the failing tests**

`graph/tests/test_build.py` (every test name below, with these assertions; `build_graph` imported from `graph.build`, `GraphInputError` likewise):

```python
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
```

Note: the module-level `pytest.importorskip("igraph")` would skip the last test too when igraph is absent, which is fine for CI without the extra; the import of `graph.build` itself at the top must not need igraph, which the last test proves when igraph is present.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest graph/tests/test_build.py -v`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'graph.build'`.

- [ ] **Step 3: Implement `graph/build.py`**

Define `class GraphInputError(ValueError)` and `def build_graph(edges: Iterable[tuple[Hashable, Hashable, float]], directed: bool = True) -> "igraph.Graph"`, with `from __future__ import annotations` and `import igraph` **inside** `build_graph` (on `ImportError`, re-raise `ImportError('The igraph package is not installed. Install with: pip install -e ".[graph]"')` chained from the original). Approach: one pass over `edges`; validate each endpoint (not `None`) and weight (`float(weight)` must be finite and `>= 0`; `None`, NaN, inf and negatives raise `GraphInputError` whose message contains the word "endpoint" or "weight" as the tests require); accumulate weights in a dict keyed by `(u, v)` for directed and `frozenset({u, v})` for undirected, remembering the first-seen orientation; assign vertex ids in first-seen order; construct with `igraph.Graph(n=..., edges=..., directed=...)` and set `vs["name"]` and `es["weight"]`. Update the `graph/__init__.py` docstring to `"""Graph analysis helpers built on igraph. Requires the optional `graph` extra."""`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest graph/tests/test_build.py -v`
Expected: all PASS. If the last test fails, igraph leaked to module top level; keep the import inside `build_graph`.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: graph and funnels tests all pass.

- [ ] **Step 6: Commit**

```bash
git add graph/build.py graph/__init__.py graph/tests/test_build.py
git commit -m "feat(graph): add igraph builder with input validation

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Documentation, supersede the old ADR, final verification

**Files:**
- Create: `docs/adr/0010-igraph-replaces-memgraph.md`
- Modify: `graph/README.md` (rewrite), `README.md`, `references.md`, `docs/adr/0008-memgraph-graph-analysis.md` (status line only), `docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md` and `docs/superpowers/plans/2026-10-04-memgraph-dependency.md` (one note each), `docs/test-reports/junit.xml` (regenerated)

**Interfaces:**
- Consumes: the final names from Tasks 1-2 (`graph` extra, `graph.build.build_graph`, `GraphInputError`), the igraph version range chosen in Task 1.
- Produces: documentation consistent with the code; no current document mentions Memgraph, Docker or Bolt except as history.

- [ ] **Step 1: Write ADR 0010**

`docs/adr/0010-igraph-replaces-memgraph.md`, same structure as ADR 0009. Status: "Accepted. Supersedes ADR 0008." Content to include, in the ADR's own words:
- **Context:** ADR 0009 right-sized the analytics to the data (62,617 rows, about 8 MB). The same reasoning applies to the graph: it fits in memory many times over, the work is exploratory, and Memgraph required Docker Desktop, WSL2, credentials, a pinned image and a licence review (BSL; TLS, HA, backup are Enterprise) for no capability the data size needs. No graph model or data had been loaded into it.
- **Decision:** igraph, in-process, in the optional `graph` extra pinned to the Task 1 range; DuckDB stays the source of rows; the graph is rebuilt on demand and never persisted; `graph.build.build_graph` is the only seam.
- **Alternatives considered:** NetworkX (pure Python, simpler to install, slower; igraph chosen for its C core, and the single seam makes switching cheap); DuckPGQ (graph SQL in DuckDB; community extension, maturity and Windows availability unverified); an embedded graph database such as Kuzu (Cypher without a server; project maintenance status unverified); keep Memgraph.
- **Consequences:** no persistence, no concurrent users, no Cypher or pattern-query engine; Windows install is `pip install` only. **Revisit when** the graph no longer fits in RAM (tens of millions of edges), several people or a service need one shared persistent graph, or pattern queries become awkward in Python. ADR 0008 and its plan stay as the reference for that case.

- [ ] **Step 2: Mark the old documents as superseded**

In `docs/adr/0008-memgraph-graph-analysis.md` change only the status body to `Superseded by [ADR 0010](0010-igraph-replaces-memgraph.md).` In the 2026-10-03 spec and the 2026-10-04 plan, add one line directly under the title: `> Superseded by [ADR 0010](../../adr/0010-igraph-replaces-memgraph.md); kept as history.` Change nothing else in them.

- [ ] **Step 3: Rewrite `graph/README.md`**

Title "Graph (igraph)". Sections: purpose and link to ADR 0010; setup (`pip install -e ".[graph,funnels,dev]"`; Windows needs nothing else); a short usage example that runs a DuckDB query returning `(source, target, weight)` rows and calls `build_graph(rows)`, then `g.pagerank(weights="weight")`; test command (`pytest graph/tests`); a short "Notes" section: the graph is in memory and rebuilt on demand, nothing is persisted, and `build_graph` semantics (duplicates summed, self-loops kept, invalid input raises `GraphInputError`); a "Migrating from Memgraph" note giving `docker compose down -v --rmi all` for anyone who ran the old stack from an older checkout, and `docker volume rm growth-analytics_memgraph_data` if the compose file is already gone. The usage example must be executed once to make sure it runs as written.

- [ ] **Step 4: Update `README.md`**

In "Current status" (about lines 22-24) replace the Memgraph sentence with: the graph model and chatbot have not been added yet, and igraph, with a tested `graph.build.build_graph` helper, is in place for the future graph model. In "Documentation" (about lines 268-272) change "and the Memgraph graph backend" to "and the graph tooling", and replace the "Graph backend" bullet with `- [Graph helpers](graph/README.md): igraph setup and the row-to-graph builder.`

- [ ] **Step 5: Update `references.md`**

Remove the three lines `https://hub.docker.com/r/memgraph/memgraph-mage`, `https://memgraph.com/docs/client-libraries/python`, `https://memgraph.com/docs/getting-started/install-memgraph/docker`. Keep the two GitHub lines for memgraph and neo4j (background references in the project's design docs). Add `https://python.igraph.org/en/stable/` and `https://pypi.org/project/igraph/`.

- [ ] **Step 6: Final verification**

```bash
git grep -n -i "memgraph\|neo4j\|docker\|bolt" -- . ':!docs/adr/0008-memgraph-graph-analysis.md' ':!docs/adr/0010-igraph-replaces-memgraph.md' ':!docs/superpowers' ':!docs/adr/0006-contracts-semantic-layer-duckdb.md' ':!docs/test-reports' ':!data'
```
Expected: matches only in `references.md` (the two kept GitHub lines) and in the "Migrating from Memgraph" note in `graph/README.md`. Anything else is a stale reference: fix it. Then, in a fresh venv, prove criterion "base install works without igraph":

```bash
python -m venv ../igraph-check-venv
../igraph-check-venv/Scripts/python -m pip install -e .
../igraph-check-venv/Scripts/python -c "import graph, graph.build; print('import ok')"
```
Expected: `import ok`, and `pip list` shows no igraph. Remove `../igraph-check-venv` afterwards. Run `.venv/Scripts/python -m pytest -q` once more (all pass), and check that the relative links in the edited docs resolve.

- [ ] **Step 7: Commit and open the PR**

```bash
git add docs/adr/0010-igraph-replaces-memgraph.md docs/adr/0008-memgraph-graph-analysis.md graph/README.md README.md references.md docs/superpowers docs/test-reports/junit.xml
git commit -m "docs: add ADR 0010, supersede ADR 0008 and update graph docs for igraph

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Pushing and opening the PR are separate: do them only when asked.

---

## Self-Review

- **Spec coverage:** removing the Docker stack, env template, connection module and tests (Task 1); igraph dependency as an optional extra and Windows-wheel proof (Task 1); a tested builder (Task 2); ADR, README, references and history notes (Task 3); no-stale-reference and base-install checks (Task 3 Step 6). The "persistence" and "multi-user" capabilities are deliberately dropped and stated as ADR consequences.
- **Placeholders:** the only deferred value is the igraph minor range, produced by the Task 1 Step 4 command, as the Memgraph plan did for `neo4j`.
- **Type consistency:** `build_graph`, `GraphInputError`, the `name` and `weight` attributes and the `graph` extra name are identical across Tasks 1-3.
- **Known unverified assumptions:** igraph has a `cp313` `win_amd64` wheel (checked by Task 1 Step 4 with `--only-binary=:all:`); `Graph.is_loop()` returns a list of booleans in the pinned version (Task 2 Step 4 would show it); DuckDB returns `int` for the literal VALUES in the round-trip test.
