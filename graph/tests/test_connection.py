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
