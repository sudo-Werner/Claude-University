import pytest

from backend import db


@pytest.fixture
def conn(tmp_path):
    c = db.get_connection(tmp_path / "test.db")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def client(tmp_path):
    from backend.app import create_app

    app = create_app(db_path=tmp_path / "test_api.db")
    app.config.update(TESTING=True)
    return app.test_client()
