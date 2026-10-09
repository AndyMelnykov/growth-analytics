# Graph (Memgraph)

Optional graph-analysis backend. See
[ADR 0008](../docs/adr/0008-memgraph-graph-analysis.md). The rest of the
repository does not need any of this.

## Windows setup

1. Install Docker Desktop; keep "Use WSL 2 based engine" enabled.
2. Optional: cap WSL2 memory in `%UserProfile%\.wslconfig`, then run
   `wsl --shutdown`:

   ```ini
   [wsl2]
   memory=8GB
   ```
3. Create your config: `cp .env.example .env`, then set a strong
   `MEMGRAPH_PASSWORD` (letters, digits, `_ . -`). The image tags in
   `.env.example` are already pinned; bump them deliberately.
4. Install the Python extra: `pip install -e ".[graph,dev]"`.

## Run

| Task | Command |
|---|---|
| Start | `docker compose up -d` |
| Start with Lab UI | `docker compose --profile ui up -d` then open http://127.0.0.1:3000 |
| Status | `docker compose ps` |
| Logs | `docker compose logs -f memgraph` |
| Stop (keeps data) | `docker compose stop` |
| Restart | `docker compose restart memgraph` |
| Reset (DELETES all graph data) | `docker compose down -v` |

The admin user is created at first start of an empty volume. Changing
`MEMGRAPH_USER` or `MEMGRAPH_PASSWORD` afterwards does not change it; reset the
volume or `ALTER` the user in Cypher.

## Test

`pytest -m integration graph/tests` runs the smoke test against the running
stack. It skips (does not fail) when Memgraph is not reachable.
`pytest` alone also runs the Docker-free unit tests.

Every run writes a JUnit report to `docs/test-reports/junit.xml` (tracked in git,
overwritten by the latest run). Commit it when you want to record a result; a run
with `-m integration` only reports the integration tests.

## Notes

- Bolt is bound to 127.0.0.1 only. Do not publish it wider without TLS.
- The graph is rebuildable from `data/raw/`; snapshots live in the
  `memgraph_data` volume and are not an off-host backup.
