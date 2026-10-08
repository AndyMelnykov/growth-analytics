# Memgraph Dependency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pinned, authenticated, persistent single-node Memgraph (with MAGE) to the repo as an optional dependency, with a small Python connection module, tests, and docs. No graph model.

**Architecture:** Memgraph runs from the published `memgraph/memgraph-mage` image via `docker-compose.yml` (Docker Desktop, WSL2 backend on Windows). Python access goes through the generic `neo4j` Bolt driver, declared as an optional `graph` extra in a new `pyproject.toml`, so the rest of the repo never needs Docker or the driver. All settings come from `MEMGRAPH_*` environment variables shared by compose and Python.

**Tech Stack:** Docker Compose, `memgraph/memgraph-mage`, `memgraph/lab`, Python >= 3.10 (3.13.7 on this machine), `neo4j` driver, pytest, setuptools.

**Spec:** `docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md`

## Global Constraints

- Image `memgraph/memgraph-mage` pinned to an explicit version tag, never `latest` (D1, D3).
- Persistence: named volume on `/var/lib/memgraph`, WAL enabled (`--storage-wal-enabled=true`), snapshots via `--storage-snapshot-interval-sec` (D3).
- Bolt (7687) published on `127.0.0.1` only; Lab (3000) on `127.0.0.1` only, behind compose profile `ui`, off by default (D3).
- Healthcheck is a Bolt-level `RETURN 1`; `mem_limit` set in compose with Memgraph `--memory-limit` set below it; `restart: unless-stopped` (D3).
- Env vars: `MEMGRAPH_HOST`, `MEMGRAPH_PORT`, `MEMGRAPH_USER`, `MEMGRAPH_PASSWORD`, `MEMGRAPH_IMAGE_TAG`. No hard-coded hosts or credentials anywhere. `.env.example` committed with placeholders, `.env` gitignored (D4).
- Authentication enabled; admin user created at first start by an init step using the password from `.env` (D4).
- Driver: `neo4j`, pinned to a minor range, in optional extra `graph`; existing repo must install and run without it (D5).
- `graph/connection.py` builds the driver from env and exposes `healthcheck()`; no graph-model code (D5).
- Integration test marked `integration`, skipped when Memgraph is unreachable; unit tests never require Docker (D6).
- ADR numbered `0008`, same format as ADRs 0001-0007 (Status / Context / Decision / Consequences) (D7).
- Packaging decision (made after the spec): **`pyproject.toml` with a `graph` extra**, not `requirements-graph.txt`.
- Licensing finding (made after the spec): community Memgraph is BSL; Enterprise (MEL) adds HA, multi-tenancy, fine-grained access control, SSO, encryption in transit, backup/restore. The ADR must record this.
- Out of scope: graph schema, loader, example Cypher, clustering/HA, TLS, off-host backup, CI, feeding from Delta layers.

## Review Focus

- `MEMGRAPH_PASSWORD` unset or empty: `from_env` fails loudly naming the missing variable; it never connects unauthenticated by default.
- `MEMGRAPH_PORT` non-numeric or out of range: clear config error, not a raw `ValueError`.
- `healthcheck()` against an unreachable server returns `False` (does not raise) so callers can poll it.
- `import graph` / `import graph.connection` works with the `graph` extra NOT installed; the error appears only when a driver is requested.
- Password containing characters special to YAML/shell/Cypher (`$`, `'`, `"`, `#`): `.env.example` documents the allowed set; the init step rejects or escapes the rest rather than silently creating the wrong password.
- Data survives `docker compose restart` and `down`/`up` (volume not removed); `docker compose down -v` is the documented reset.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, `graph` and `dev` extras, pytest config and markers |
| `.gitignore` | Ignore `.env`, venv, caches, build artifacts |
| `.env.example` | Documented placeholders for all `MEMGRAPH_*` variables |
| `docker-compose.yml` | `memgraph`, `memgraph-init`, `lab` (profile `ui`) services and volume |
| `graph/__init__.py` | Package marker; imports nothing heavy |
| `graph/connection.py` | `MemgraphSettings`, `MemgraphConfigError`, `get_driver`, `healthcheck` |
| `graph/tests/conftest.py` | `.env` loading and the `driver` fixture that skips when unreachable |
| `graph/tests/test_connection_unit.py` | Docker-free tests of config parsing and healthcheck logic |
| `graph/tests/test_connection.py` | `integration` smoke test against a live Memgraph |
| `graph/README.md` | Windows setup, start/stop/reset, Lab, running tests |
| `docs/adr/0008-memgraph-graph-analysis.md` | Decision record |
| `README.md`, `references.md` | Pointers to the new pieces |
| `docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md` | Record resolved open questions |

Branch: create `feat/memgraph-dependency` from the current `docs/memgraph-dependency-spec` (the spec commit `6e9d70d` is already there). Never stage `.vscode/settings.json`; it has unrelated local changes.

---

### Task 1: Packaging, ignore rules and env template

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `graph/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable project with extras `graph` and `dev`; registered pytest marker `integration`; `.env.example` variable names used verbatim by Tasks 2-3.

- [ ] **Step 1: Create the branch and a virtualenv**

```bash
cd /c/Projects/analytics/growth-analytics
git switch -c feat/memgraph-dependency
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
```

- [ ] **Step 2: Find the current `neo4j` driver version to pin**

```bash
.venv/Scripts/python -m pip install neo4j
.venv/Scripts/python -m pip show neo4j
```
Expected: a `Version: X.Y.Z` line. Use `X.Y` for the range in Step 3 (`>=X.Y,<X.(Y+1)`). Check Memgraph's driver docs (https://memgraph.com/docs/client-libraries/python) that this major version is supported; if not, pick the newest supported major.

- [ ] **Step 3: Write `pyproject.toml`**

Replace `5.28` / `5.29` below with the range from Step 2.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "growth-analytics"
version = "0.1.0"
description = "AI product analytics graph: synthetic growth data, analytics and graph analysis"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
graph = ["neo4j>=5.28,<5.29"]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["graph*"]

[tool.pytest.ini_options]
testpaths = ["graph/tests"]
markers = [
    "integration: needs a running Memgraph (docker compose up -d)",
]
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
# secrets and local config
.env

# python
.venv/
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
```

- [ ] **Step 5: Write `.env.example`**

```dotenv
# Copy to .env and edit. .env is gitignored; never commit real credentials.
# docker compose reads .env automatically; Python reads the same names.

# Pinned memgraph-mage image tag (see https://hub.docker.com/r/memgraph/memgraph-mage/tags).
# Never use "latest". Bump deliberately and snapshot before upgrading.
MEMGRAPH_IMAGE_TAG=CHANGE_ME

# Where Python clients connect (compose publishes Bolt on 127.0.0.1 only).
MEMGRAPH_HOST=127.0.0.1
MEMGRAPH_PORT=7687

# Admin account created at first start by the memgraph-init service.
MEMGRAPH_USER=admin
# Letters, digits and _ - . only: the value is embedded in a Cypher statement
# and a shell command, so quotes, $, # and spaces are rejected by the init step.
MEMGRAPH_PASSWORD=CHANGE_ME_STRONG_PASSWORD
```

- [ ] **Step 6: Create the empty package**

`graph/__init__.py` containing only:

```python
"""Memgraph access for graph analysis. Requires the optional `graph` extra."""
```

- [ ] **Step 7: Verify install and that the base install does not need the driver**

```bash
.venv/Scripts/python -m pip install -e ".[graph,dev]"
.venv/Scripts/python -m pytest --collect-only -q
```
Expected: install succeeds; pytest reports "no tests collected" without error. Then:
```bash
.venv/Scripts/python -m pip install -e .
```
Expected: succeeds with no driver requirement. Reinstall `.[graph,dev]` afterwards.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example graph/__init__.py
git commit -m "build: add pyproject with optional graph extra and env template

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Connection module (TDD, no Docker)

**Files:**
- Create: `graph/connection.py`, `graph/tests/__init__.py`, `graph/tests/test_connection_unit.py`

**Interfaces:**
- Consumes: env var names from Task 1.
- Produces:
  - `class MemgraphConfigError(ValueError)`
  - `@dataclass(frozen=True) class MemgraphSettings(host: str, port: int, user: str, password: str)` with property `uri -> str` (`"bolt://host:port"`) and classmethod `from_env(env: Mapping[str, str] | None = None) -> MemgraphSettings`
  - `get_driver(settings: MemgraphSettings | None = None) -> neo4j.Driver`
  - `healthcheck(driver) -> bool`

- [ ] **Step 1: Write the failing tests**

`graph/tests/__init__.py` empty. `graph/tests/test_connection_unit.py`:

```python
import pytest

from graph.connection import (
    MemgraphConfigError,
    MemgraphSettings,
    healthcheck,
)

GOOD = {
    "MEMGRAPH_HOST": "127.0.0.1",
    "MEMGRAPH_PORT": "7687",
    "MEMGRAPH_USER": "admin",
    "MEMGRAPH_PASSWORD": "s3cret",
}


def test_from_env_reads_all_fields():
    s = MemgraphSettings.from_env(GOOD)
    assert (s.host, s.port, s.user, s.password) == ("127.0.0.1", 7687, "admin", "s3cret")
    assert s.uri == "bolt://127.0.0.1:7687"


@pytest.mark.parametrize("missing", list(GOOD))
def test_missing_variable_is_named_in_error(missing):
    env = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(MemgraphConfigError, match=missing):
        MemgraphSettings.from_env(env)


def test_empty_password_is_rejected():
    with pytest.raises(MemgraphConfigError, match="MEMGRAPH_PASSWORD"):
        MemgraphSettings.from_env({**GOOD, "MEMGRAPH_PASSWORD": ""})


@pytest.mark.parametrize("port", ["abc", "0", "70000", "-1", ""])
def test_bad_port_is_a_config_error(port):
    with pytest.raises(MemgraphConfigError, match="MEMGRAPH_PORT"):
        MemgraphSettings.from_env({**GOOD, "MEMGRAPH_PORT": port})


def test_repr_does_not_leak_password():
    assert "s3cret" not in repr(MemgraphSettings.from_env(GOOD))


class FakeDriver:
    def __init__(self, error=None):
        self.error = error

    def verify_connectivity(self):
        if self.error:
            raise self.error


def test_healthcheck_true_when_reachable():
    assert healthcheck(FakeDriver()) is True


def test_healthcheck_false_when_unreachable_does_not_raise():
    assert healthcheck(FakeDriver(error=OSError("connection refused"))) is False


def test_importing_package_does_not_require_driver(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "neo4j", None)  # simulate extra not installed
    import importlib

    import graph.connection

    importlib.reload(graph.connection)  # must not raise
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest graph/tests/test_connection_unit.py -v`
Expected: collection ERROR, `ModuleNotFoundError: graph.connection`.

- [ ] **Step 3: Implement `graph/connection.py`**

```python
"""Connection helpers for Memgraph over Bolt.

Settings come only from MEMGRAPH_* environment variables. The `neo4j` driver
is imported lazily so that importing this module works without the optional
`graph` extra installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

_REQUIRED = ("MEMGRAPH_HOST", "MEMGRAPH_PORT", "MEMGRAPH_USER", "MEMGRAPH_PASSWORD")


class MemgraphConfigError(ValueError):
    """Raised when MEMGRAPH_* environment configuration is missing or invalid."""


@dataclass(frozen=True)
class MemgraphSettings:
    host: str
    port: int
    user: str
    password: str = field(repr=False)

    @property
    def uri(self) -> str:
        return f"bolt://{self.host}:{self.port}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MemgraphSettings":
        env = os.environ if env is None else env
        missing = [name for name in _REQUIRED if not env.get(name)]
        if missing:
            raise MemgraphConfigError(
                "Missing required environment variable(s): " + ", ".join(missing)
            )
        raw_port = env["MEMGRAPH_PORT"]
        try:
            port = int(raw_port)
        except ValueError:
            raise MemgraphConfigError(
                f"MEMGRAPH_PORT must be an integer, got {raw_port!r}"
            ) from None
        if not 1 <= port <= 65535:
            raise MemgraphConfigError(f"MEMGRAPH_PORT out of range: {port}")
        return cls(
            host=env["MEMGRAPH_HOST"],
            port=port,
            user=env["MEMGRAPH_USER"],
            password=env["MEMGRAPH_PASSWORD"],
        )


def get_driver(settings: MemgraphSettings | None = None):
    """Build a neo4j Bolt driver for Memgraph. Caller must close it."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ImportError(
            "The neo4j driver is not installed. Install with: pip install -e '.[graph]'"
        ) from exc
    settings = settings or MemgraphSettings.from_env()
    return GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))


def healthcheck(driver) -> bool:
    """True if the server answers over Bolt with valid credentials; never raises."""
    try:
        driver.verify_connectivity()
        return True
    except Exception:
        return False
```

Note on `port=""`: the empty string is caught by the `missing` check first, so the error names `MEMGRAPH_PORT`, which satisfies the parametrized test.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest graph/tests/test_connection_unit.py -v`
Expected: all PASS. If `test_importing_package_does_not_require_driver` fails, the neo4j import has leaked to module top level; keep it inside `get_driver`.

- [ ] **Step 5: Commit**

```bash
git add graph/connection.py graph/tests/__init__.py graph/tests/test_connection_unit.py
git commit -m "feat(graph): add env-driven Memgraph connection module

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Compose stack and integration smoke test

**Files:**
- Create: `docker-compose.yml`, `graph/tests/conftest.py`, `graph/tests/test_connection.py`
- Modify: `.env.example` (real image tag), local untracked `.env`

**Interfaces:**
- Consumes: `MemgraphSettings`, `get_driver`, `healthcheck` from Task 2; env names from Task 1.
- Produces: `docker compose up -d` brings up a healthy, authenticated Memgraph; fixture `driver` for integration tests.

- [ ] **Step 1: Confirm Docker is running and pick the image tags**

```bash
docker info --format '{{.ServerVersion}}'
curl -s "https://hub.docker.com/v2/repositories/memgraph/memgraph-mage/tags?page_size=25&ordering=last_updated"
curl -s "https://hub.docker.com/v2/repositories/memgraph/lab/tags?page_size=10&ordering=last_updated"
```
Expected: a server version; tag lists. The earlier web search showed conflicting versions (MAGE release page: 3.7.2; Docker Hub: 3.9.0), so choose the newest plain numeric tag (`X.Y.Z`, no `-malloc`, `-relwithdebinfo`, `-memgraph-*` suffix) from this live output. Write it into `.env.example` (`MEMGRAPH_IMAGE_TAG=`) and copy to `.env`:
```bash
cp .env.example .env
```
Then edit `.env`: set the real tag and a strong password (allowed characters only). Add `LAB_IMAGE_TAG=<lab tag>` to both files with a comment "pinned Memgraph Lab tag".

- [ ] **Step 2: Check the image's CLI flags and tools before relying on them**

```bash
docker run --rm --entrypoint sh memgraph/memgraph-mage:<TAG> -c "which mgconsole; /usr/lib/memgraph/memgraph --help-xml | grep -E 'storage-wal-enabled|storage-snapshot-interval-sec|memory-limit' | head"
```
Expected: `mgconsole` path printed and the three flags found. If the binary path differs, adjust. Also check the Memgraph docs for startup environment variables `MEMGRAPH_USER` / `MEMGRAPH_PASSWORD`: if the pinned version creates the initial user from them, the `memgraph-init` service below can be dropped and the two variables passed to the `memgraph` service instead; record whichever is used in the ADR.

- [ ] **Step 3: Write `docker-compose.yml`**

`mem_limit` is 4g and Memgraph's `--memory-limit` (in MB) is 3072, below it, so the database throttles before the OOM killer acts.

```yaml
name: growth-analytics

services:
  memgraph:
    image: memgraph/memgraph-mage:${MEMGRAPH_IMAGE_TAG:?set MEMGRAPH_IMAGE_TAG in .env}
    command:
      - "--memory-limit=3072"
      - "--storage-wal-enabled=true"
      - "--storage-snapshot-interval-sec=300"
      - "--log-level=WARNING"
      - "--also-log-to-stderr=true"
    ports:
      - "127.0.0.1:${MEMGRAPH_PORT:-7687}:7687"
    volumes:
      - memgraph_data:/var/lib/memgraph
    environment:
      MEMGRAPH_USER: ${MEMGRAPH_USER:?set MEMGRAPH_USER in .env}
      MEMGRAPH_PASSWORD: ${MEMGRAPH_PASSWORD:?set MEMGRAPH_PASSWORD in .env}
    mem_limit: 4g
    restart: unless-stopped
    healthcheck:
      test:
        - CMD-SHELL
        - echo 'RETURN 1;' | mgconsole --username "$$MEMGRAPH_USER" --password "$$MEMGRAPH_PASSWORD" || exit 1
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 20s

  # One-shot: creates the admin user on first start. Idempotent.
  memgraph-init:
    image: memgraph/memgraph-mage:${MEMGRAPH_IMAGE_TAG}
    depends_on:
      memgraph:
        condition: service_started
    restart: "no"
    entrypoint: ["/bin/sh", "-c"]
    environment:
      MEMGRAPH_USER: ${MEMGRAPH_USER}
      MEMGRAPH_PASSWORD: ${MEMGRAPH_PASSWORD}
    command:
      - |
        case "$$MEMGRAPH_PASSWORD$$MEMGRAPH_USER" in
          *[!A-Za-z0-9_.-]*) echo "MEMGRAPH_USER/PASSWORD may only contain letters, digits, _ . -" >&2; exit 1;;
        esac
        for i in $$(seq 1 30); do
          echo "CREATE USER IF NOT EXISTS $$MEMGRAPH_USER IDENTIFIED BY '$$MEMGRAPH_PASSWORD'; GRANT ALL PRIVILEGES TO $$MEMGRAPH_USER;" \
            | mgconsole --host memgraph --username "$$MEMGRAPH_USER" --password "$$MEMGRAPH_PASSWORD" && exit 0
          sleep 2
        done
        echo "memgraph-init: could not reach memgraph" >&2; exit 1

  lab:
    image: memgraph/lab:${LAB_IMAGE_TAG:?set LAB_IMAGE_TAG in .env}
    profiles: ["ui"]
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      QUICK_CONNECT_MG_HOST: memgraph
      QUICK_CONNECT_MG_PORT: "7687"
    depends_on:
      memgraph:
        condition: service_healthy
    restart: unless-stopped

volumes:
  memgraph_data:
```

Caveats to verify in Step 4 and adjust the file if they fail: (a) on a fresh volume the healthcheck runs before any user exists, and `mgconsole` with credentials must still succeed while auth is unconfigured; (b) `GRANT ALL PRIVILEGES` and `CREATE USER IF NOT EXISTS` must be valid on the pinned version.

- [ ] **Step 4: Bring the stack up and verify on a fresh volume**

```bash
docker compose config --quiet && echo "compose file valid"
docker compose down -v
docker compose up -d
docker compose ps
docker compose logs memgraph-init
```
Expected: `memgraph` reaches `healthy` within about a minute; `memgraph-init` exited with code 0 (`docker compose ps -a`). Then confirm auth is enforced:
```bash
docker compose exec memgraph sh -c "echo 'RETURN 1;' | mgconsole --username nobody --password wrong"
```
Expected: authentication failure. And confirm Bolt is bound to localhost only:
```bash
docker compose port memgraph 7687
```
Expected: `127.0.0.1:7687`.

- [ ] **Step 5: Write the integration fixtures**

`graph/tests/conftest.py`:

```python
"""Shared fixtures. Integration tests skip cleanly when Memgraph is unavailable."""

import os
from pathlib import Path

import pytest

from graph.connection import MemgraphConfigError, MemgraphSettings, get_driver, healthcheck


def _load_dotenv() -> None:
    """Populate os.environ from the repo-root .env without overriding real env vars."""
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()


@pytest.fixture(scope="session")
def driver():
    try:
        settings = MemgraphSettings.from_env()
    except MemgraphConfigError as exc:
        pytest.skip(f"Memgraph not configured: {exc}")
    try:
        drv = get_driver(settings)
    except ImportError as exc:
        pytest.skip(str(exc))
    if not healthcheck(drv):
        drv.close()
        pytest.skip(f"Memgraph not reachable at {settings.uri}")
    yield drv
    drv.close()
```

- [ ] **Step 6: Write the integration test**

`graph/tests/test_connection.py`:

```python
import pytest

pytestmark = pytest.mark.integration


def test_return_one(driver):
    with driver.session() as session:
        assert session.run("RETURN 1 AS n").single()["n"] == 1


def test_write_access_via_throwaway_constraint(driver):
    create = "CREATE CONSTRAINT ON (n:SmokeTest) ASSERT n.id IS UNIQUE"
    drop = "DROP CONSTRAINT ON (n:SmokeTest) ASSERT n.id IS UNIQUE"
    with driver.session() as session:
        session.run(create).consume()
        try:
            names = session.run("SHOW CONSTRAINT INFO").data()
            assert any("SmokeTest" in str(row) for row in names)
        finally:
            session.run(drop).consume()
```

- [ ] **Step 7: Run integration tests against the live stack, then without it**

```bash
.venv/Scripts/python -m pytest -m integration graph/tests -v
```
Expected: 2 PASSED. Then:
```bash
docker compose stop memgraph
.venv/Scripts/python -m pytest -m integration graph/tests -v
```
Expected: 2 SKIPPED ("not reachable"), exit code 0. Then `docker compose start memgraph`. Run the full suite once: `.venv/Scripts/python -m pytest -v` (unit tests pass; integration pass or skip).

- [ ] **Step 8: Verify persistence**

```bash
.venv/Scripts/python - <<'EOF'
from graph.tests.conftest import _load_dotenv; _load_dotenv()
from graph.connection import get_driver
d = get_driver()
with d.session() as s: s.run("MERGE (:Persist {id: 1})").consume()
d.close()
EOF
docker compose restart memgraph
# wait for healthy, then:
.venv/Scripts/python - <<'EOF'
from graph.tests.conftest import _load_dotenv; _load_dotenv()
from graph.connection import get_driver
d = get_driver()
with d.session() as s:
    print(s.run("MATCH (n:Persist) RETURN count(n) AS c").single()["c"])
    s.run("MATCH (n:Persist) DELETE n").consume()  # cleanup
d.close()
EOF
```
Expected: prints `1`. If it prints `0`, WAL/snapshot settings are not taking effect: check `docker compose logs memgraph` and the flag names from Step 2.

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml .env.example graph/tests/conftest.py graph/tests/test_connection.py
git commit -m "feat(graph): add Memgraph compose stack and integration smoke test

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Confirm `git status` shows `.env` is not staged and `git check-ignore .env` prints `.env`.

---

### Task 4: Documentation and spec update

**Files:**
- Create: `docs/adr/0008-memgraph-graph-analysis.md`, `graph/README.md`
- Modify: `README.md` (status and Documentation sections), `references.md`, `docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md`

**Interfaces:**
- Consumes: the final file names, tag choices and any deviations discovered in Task 3 (for example whether the init service or startup env vars create the user).
- Produces: documentation consistent with the implemented stack.

- [ ] **Step 1: Write the ADR**

`docs/adr/0008-memgraph-graph-analysis.md`, same structure as ADR 0007:

```markdown
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
to an explicit tag, via `docker-compose.yml` (Docker Desktop on Windows with the
WSL2 backend). Access it from Python with the generic `neo4j` Bolt driver,
declared as the optional `graph` extra in `pyproject.toml`.

- Memgraph is a derived store; the lakehouse and `data/raw/` remain the source
  of truth and the graph can be rebuilt.
- Bolt is published on 127.0.0.1 only; authentication is enabled; credentials
  come from `MEMGRAPH_*` environment variables (`.env`, gitignored).
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
- Image tags are bumped deliberately, with a snapshot first.
- The loader (later spec) must be idempotent (`MERGE` with constraints and
  indexes) so the graph can be dropped and rebuilt.
```

If Task 3 Step 2 found that startup env vars replace the init service, add one sentence stating which mechanism creates the admin user.

- [ ] **Step 2: Write `graph/README.md`**

```markdown
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
3. Create your config: `cp .env.example .env`, then set `MEMGRAPH_IMAGE_TAG`,
   `LAB_IMAGE_TAG` and a strong `MEMGRAPH_PASSWORD` (letters, digits, `_ . -`).
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

## Test

`pytest -m integration graph/tests` runs the smoke test against the running
stack. It skips (does not fail) when Memgraph is not reachable.
`pytest` alone also runs the Docker-free unit tests.

## Notes

- Bolt is bound to 127.0.0.1 only. Do not publish it wider without TLS.
- The graph is rebuildable from `data/raw/`; snapshots live in the
  `memgraph_data` volume and are not an off-host backup.
```

- [ ] **Step 3: Update `README.md`**

In "Current status", change "the executable transformation pipeline, graph model, chatbot, ..." so it says the graph *model* is not added yet but the Memgraph infrastructure is. In "Documentation", extend the ADR bullet list ("...semantic metrics, and the chatbot" becomes "..., the chatbot, and the Memgraph graph backend") and add:

```markdown
- [Graph backend](graph/README.md): optional Memgraph setup (Docker Compose,
	Python connection module, smoke test).
```

- [ ] **Step 4: Update `references.md`**

Add under the existing Memgraph and Neo4j links:

```
https://hub.docker.com/r/memgraph/memgraph-mage
https://memgraph.com/docs/client-libraries/python
https://memgraph.com/docs/getting-started/install-memgraph/docker
```

- [ ] **Step 5: Update the spec's open questions**

In `docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md`, change `Status:` to "Approved; implemented by plan 2026-10-04" and replace the two bullets under "Open questions" with the resolved decisions: packaging is `pyproject.toml` with a `graph` extra; image tag is resolved at implementation time (record the tag used). Add a short "Findings after review" paragraph: community is BSL, Enterprise (MEL) features, and that TLS and backup/restore are Enterprise.

- [ ] **Step 6: Final verification (success criteria from the spec)**

```bash
docker compose down -v && docker compose up -d     # 1. healthy and authenticated
.venv/Scripts/python -m pytest -m integration graph/tests -v   # 2. passes
git grep -n -i "password" -- ':!docs' ':!graph/README.md' ':!.env.example'   # 4. no committed credentials
git ls-files .env                                   # 4. prints nothing
```
For criterion 3, in a fresh venv run `pip install -e .` then `python -c "import graph.connection"`; expected: no error and no neo4j installed. Re-check the docs for relative-link correctness.

- [ ] **Step 7: Commit**

```bash
git add docs/adr/0008-memgraph-graph-analysis.md graph/README.md README.md references.md docs/superpowers/specs/2026-10-03-memgraph-dependency-design.md docs/superpowers/plans/2026-10-04-memgraph-dependency.md
git commit -m "docs: add Memgraph ADR, graph README and update references

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** D1 (image, no fork) and D2 (Docker Desktop, `.wslconfig`) in Tasks 3-4; D3 compose in Task 3; D4 env/secrets in Tasks 1 and 3; D5 driver, extra, `connection.py` in Tasks 1-2; D6 smoke test and skip behavior in Task 3 (CI explicitly out of scope per spec); D7 docs in Task 4; success criteria 1-4 verified in Task 3 Steps 4/7/8 and Task 4 Step 6. Both open questions are resolved (packaging by decision, tag by Task 3 Step 1).
- **Placeholders:** the only values deferred are the `neo4j` version range and the image tags, each with an explicit command that produces them. This is deliberate: the spec forbids guessing them.
- **Type consistency:** `MemgraphSettings.from_env`, `get_driver`, `healthcheck`, `MemgraphConfigError` are used with the same names in Tasks 2-3; `driver` fixture name matches both integration tests.
- **Known unverified assumptions (flagged in-plan):** `CREATE USER IF NOT EXISTS` / `GRANT ALL PRIVILEGES` syntax, unauthenticated `mgconsole` healthcheck on a fresh volume, `mgconsole` presence and flag names in the pinned image, and `SHOW CONSTRAINT INFO` output shape. Task 3 Steps 2 and 4 are where these get confirmed against the real image.
