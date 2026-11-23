# ADR 0010: igraph replaces Memgraph for graph analysis

## Status

Accepted. Supersedes ADR 0008.

## Context

ADR 0009 right-sized the analytics to the data: 62,617 rows in about 8 MB. The
same reasoning applies to the graph. It fits in memory many times over and the
work is exploratory. Memgraph needed Docker Desktop, WSL2, credentials, a
pinned image and a licence review (BSL; TLS, high availability and backup are
Enterprise features) for no capability this data size requires. No graph model
or data had been loaded into it.

## Decision

- Use `igraph`, in-process, as the optional `graph` extra, pinned to
  `igraph>=1.0,<1.1`. It installs from a prebuilt Windows wheel; there is no
  server, no credentials and no Docker.
- DuckDB (the `funnels` warehouse) stays the source of rows.
- The graph is rebuilt in memory on demand and never persisted.
- `graph.build.build_graph` is the only seam between query rows and
  `igraph.Graph`, so moving to another library or back to a graph database
  touches one module. igraph is imported lazily, so the base install works
  without the extra.

## Alternatives considered

- **NetworkX:** pure Python and the simplest to install, but slower. igraph was
  chosen for its C core; the single seam makes switching cheap.
- **DuckPGQ** (graph SQL inside DuckDB): a community extension whose maturity
  and Windows availability were not verified.
- **An embedded graph database such as Kuzu** (Cypher without a server): the
  project's maintenance status was not verified.
- **Keep Memgraph:** operational cost without a matching need.

## Consequences

- No persistence, no concurrent users, and no Cypher or pattern-query engine.
- Windows setup is `pip install` only.
- **Revisit when** the graph no longer fits in RAM (tens of millions of edges),
  several people or a service need one shared persistent graph, or pattern
  queries become awkward in Python. ADR 0008 and its plan remain the reference
  for that case.
