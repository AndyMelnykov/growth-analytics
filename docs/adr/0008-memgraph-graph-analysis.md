# ADR 0008: Memgraph for graph analysis

## Status

Accepted

## Context

Growth questions (which campaigns, features and subscriptions depend on each
other, and which paths lead to conversion) are relationship questions. The
raw data in `data/raw/` and the planned lakehouse layers are tabular; a graph
database makes multi-hop traversals and graph algorithms (PageRank, community
detection) direct rather than recursive SQL. The work is exploratory today and
may become a service, so the dependency is built production-style from the
start. This ADR covers infrastructure only; the graph model is a later decision.

## Decision

Run Memgraph with MAGE from the published `memgraph/memgraph-mage` image, pinned
to an explicit tag (`3.13.1`, with Memgraph Lab `3.13.2` behind the `ui` compose
profile), via `docker-compose.yml` (Docker Desktop on Windows with the WSL2
backend). Access it from Python with the generic `neo4j` Bolt driver, declared
as the optional `graph` extra in `pyproject.toml`.

- Memgraph is a derived store; the lakehouse and `data/raw/` remain the source
  of truth and the graph can be rebuilt.
- Bolt is published on 127.0.0.1 only; authentication is enabled; credentials
  come from `MEMGRAPH_*` environment variables (`.env`, gitignored).
- The admin user is created by Memgraph itself at first start from the
  `MEMGRAPH_USER` / `MEMGRAPH_PASSWORD` variables passed to the `memgraph`
  service, so no separate init service is needed. This only happens on an empty
  data volume; changing the variables later does not change an existing user.
- Persistence via a named volume with WAL and periodic snapshots; memory is
  capped in compose with Memgraph's own limit set lower.

### Alternatives considered

- **Fork or submodule of memgraph/memgraph:** a large C++ codebase we would
  consume, not modify.
- **Neo4j:** also Bolt-compatible, and the generic driver keeps the code
  portable to it; Memgraph chosen for in-memory performance and bundled
  algorithms (MAGE).
- **Postgres recursive queries:** workable for shallow paths, awkward for
  algorithms and variable-depth traversal.
- **Do nothing:** keeps relationship analysis in ad-hoc SQL and notebooks.

### Licensing

Community Memgraph is licensed under BSL; Memgraph Enterprise under MEL.
Enterprise adds high availability, multi-tenancy, fine-grained access control,
SSO, encryption in transit, and backup/restore. Internal analytical use falls
within community terms, but confirm the BSL terms against the intended use
before offering the graph as a service to third parties. Docker Desktop is free
for personal use and for organizations under 250 employees and $10M revenue.

## Consequences

- The rest of the repo installs and runs without Docker or the driver.
- TLS, HA and managed backups are not available on community; localhost-only
  binding is the security boundary until a reverse proxy or a license is added.
- The password must use letters, digits and `_ - .` only. Compose, the
  container shell and the Python `.env` loader parse other characters
  differently; nothing enforces this, it is documented in `.env.example`.
- Image tags are bumped deliberately, with a snapshot first.
- The loader (later spec) must be idempotent (`MERGE` with constraints and
  indexes) so the graph can be dropped and rebuilt.
