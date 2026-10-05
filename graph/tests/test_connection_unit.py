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
