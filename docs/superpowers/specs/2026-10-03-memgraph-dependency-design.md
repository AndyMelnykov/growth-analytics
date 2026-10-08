# Memgraph as a dependency: design

Date: 2026-10-03
Status: Approved; implemented by plan 2026-10-04

## Goal

Add Memgraph (graph database) to the repository as a production-grade
dependency, so graph analysis of the growth data (find logical dependencies
between campaigns, features, subscriptions and conversions) can be built on it.

This spec covers **infrastructure and dependency wiring only**. The graph
model (node and relationship types, loader mappings) is a separate, later
spec.

## Intent and assumptions

Stated by the owner:
- Use the memgraph/memgraph project to build analytical graphs over the data in `data/raw/`.
- Work is exploratory today but may become a production service, so build it
  the production way from the start.
- Windows 11 host; minimum impact on the machine; **Docker Desktop preferred**.
- Docker image plus a Python loader (approach chosen over fork/submodule).

Assumptions (correct me if wrong):
- Single-node Memgraph is sufficient; no clustering or HA in scope.
- Memgraph is a derived store: the source of truth stays in the lakehouse and
  `data/raw/`; the graph can always be rebuilt from them.
- The existing pipeline must not gain a hard dependency on Memgraph.

## Decisions

### D1. Use the published image, not a fork or submodule
Memgraph is a database server; we consume it, not modify it. Fork/submodule
would add a large C++ codebase with no benefit. We run `memgraph/memgraph-mage`
(database plus MAGE graph algorithms: PageRank, community detection, etc.).

### D2. Docker Desktop with the WSL2 backend (Windows)
- Install Docker Desktop and keep "Use WSL 2 based engine" enabled. WSL2 with
  Ubuntu and virtualization are already present on this machine, so no new
  VM is created.
- Licensing: Docker Desktop is free for personal use and for small businesses
  (fewer than 250 employees and under $10M annual revenue); larger
  organizations need a paid subscription. Confirm this applies before relying
  on it for production work.
- Optional hardening of footprint: cap WSL2 memory via `%UserProfile%\.wslconfig`
  (for example `memory=8GB`) so the engine does not take most of the 32 GB.
- `docker-compose.yml` is engine-agnostic; moving to Docker Engine in WSL,
  Linux servers or Kubernetes later needs no change to the definition.

### D3. Compose service definition
`docker-compose.yml` at repo root:
- Service `memgraph`: image `memgraph/memgraph-mage` pinned to an explicit
  version tag (never `latest`).
- Persistence: named volume for `/var/lib/memgraph`; snapshots and
  write-ahead log enabled (`--storage-snapshot-interval-sec`,
  `--storage-wal-enabled=true`) so data survives restarts.
- Network: Bolt (7687) published on `127.0.0.1` only.
- Healthcheck: a Bolt-level query (`RETURN 1`) with start period and retries.
- Resource limits: memory limit set via compose (`mem_limit`), with Memgraph's
  `--memory-limit` set below it so the database throttles before the OOM killer.
- Service `lab` (Memgraph Lab UI, port 3000, `127.0.0.1`) behind a compose
  profile `ui`, off by default.
- `restart: unless-stopped`.

### D4. Configuration and secrets
- All settings come from environment variables: `MEMGRAPH_HOST`,
  `MEMGRAPH_PORT`, `MEMGRAPH_USER`, `MEMGRAPH_PASSWORD`, `MEMGRAPH_IMAGE_TAG`.
- `.env.example` is committed with placeholders; `.env` is gitignored.
- The compose file and the Python code read the same variables. No hard-coded
  hosts or credentials anywhere.
- Authentication enabled; an admin user is created at first start by an init
  script, using the password from `.env`.

### D5. Python dependency
- Driver: the `neo4j` Bolt driver (Memgraph is Bolt-compatible), pinned to a
  compatible minor range. Choosing the generic driver over a Memgraph-specific
  client keeps the code portable to Neo4j, which is already listed in
  `references.md`.
- Declared in an optional dependency group (`graph`) so the existing pipeline
  installs and runs without it.
- A small module `graph/connection.py` builds the driver from environment
  variables and exposes a `healthcheck()` helper. No graph-model code here.

### D6. Smoke test and CI
- `graph/tests/test_connection.py`: connects, runs `RETURN 1`, creates and
  drops a throwaway constraint to prove write access.
- Marked `integration` and skipped when `MEMGRAPH_HOST` is unreachable, so
  local unit tests never require Docker.
- CI (when added) runs it against a Memgraph service container using the same
  pinned image tag.

### D7. Documentation
- `docs/adr/0008-memgraph-graph-analysis.md`: context, decision, alternatives
  (fork/submodule, Neo4j, Postgres recursive queries, doing nothing),
  consequences. Follows the format of existing ADRs.
- `graph/README.md`: Windows setup (Docker Desktop, `.wslconfig`), how to
  start/stop/reset, how to open Lab, and how to run the smoke test.
- Update `README.md` and `references.md` to point at the new pieces.

## Out of scope
- Graph schema, data loader, example Cypher queries (next spec).
- Clustering, replication, backups beyond snapshots, TLS termination.
- Feeding the graph from the Delta/medallion layers (revisit once the pipeline
  code exists in this repo).

## Production considerations recorded for later
- **Rebuildability:** loader will be idempotent (`MERGE` with uniqueness
  constraints and indexes), so the graph can be dropped and rebuilt.
- **Backups:** snapshots in the named volume; add off-host backup and a
  restore drill before treating the graph as serving infrastructure.
- **Upgrades:** pin and bump image tags deliberately; snapshot before upgrade.
- **TLS and network exposure:** localhost-only today; require TLS and a
  reverse proxy before exposing beyond the host.

## Files to add or change
- add `docker-compose.yml`, `.env.example`, `.gitignore` entries
- add `graph/connection.py`, `graph/tests/test_connection.py`, `graph/README.md`
- add `docs/adr/0008-memgraph-graph-analysis.md`
- add dependency declaration (`pyproject.toml` or `requirements-graph.txt`,
  depending on the repo's Python packaging; none exists yet, so decide at plan time)
- update `README.md`, `references.md`

## Success criteria
1. `docker compose up -d` on Windows 11 with Docker Desktop brings up a healthy,
   authenticated Memgraph; data survives `docker compose restart`.
2. `pytest -m integration graph/tests` passes against it.
3. The rest of the repo installs and runs without Docker or the `graph` extra.
4. No credentials are committed.

## Resolved decisions
- Packaging: `pyproject.toml` with an optional `graph` extra (`neo4j` pinned to
  a minor range), plus a `dev` extra for pytest.
- Image tag: resolved at implementation time. `memgraph/memgraph-mage:3.13.1`
  and `memgraph/lab:3.13.2`, both set in `.env.example`.
- Admin user: created by Memgraph itself at first start from `MEMGRAPH_USER` /
  `MEMGRAPH_PASSWORD` passed to the `memgraph` service, instead of a separate
  init service (D4 allowed either).

## Findings after review
Community Memgraph is licensed under BSL; Memgraph Enterprise (MEL) adds high
availability, multi-tenancy, fine-grained access control, SSO, encryption in
transit, and backup/restore. TLS and backup/restore are therefore Enterprise
features: the "TLS" and "backups" items under production considerations need a
license or a proxy/external tooling, not just configuration. Recorded in
[ADR 0008](../../adr/0008-memgraph-graph-analysis.md).
