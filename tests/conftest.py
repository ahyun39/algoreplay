import pytest

from algoreplay import db as database
from algoreplay.config import ROOT
from algoreplay.sandbox import docker_available

EXAMPLES = ROOT / "examples"

needs_docker = pytest.mark.skipif(not docker_available(), reason="Docker is not running")


@pytest.fixture
def db(tmp_path):
    conn = database.connect(str(tmp_path / "test.db"))
    yield conn
    conn.close()
