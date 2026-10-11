from __future__ import annotations

import pytest

from funnels.tests.fixture_data import FIXTURE_PARAMS, write_raw
from funnels.warehouse import build


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("raw")
    write_raw(path)
    return path


@pytest.fixture(scope="session")
def con(raw_dir):
    connection = build(raw_dir, FIXTURE_PARAMS)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def query(con):
    def run(sql, *params):
        return con.execute(sql, list(params)).fetchall()

    return run
