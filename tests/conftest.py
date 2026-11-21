import pytest

from app.main import create_app
from app.modules.archive.pipeline import run_shift
from app.modules.archive.service import sample_plan, sample_sources
from app.shift import load_shift


@pytest.fixture(scope='session')
def sources():
    return sample_sources()


@pytest.fixture(scope='session')
def shift(sources):
    return load_shift(sources['shift'])


@pytest.fixture(scope='session')
def snapshot(sources):
    return run_shift(sources, sample_plan())


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'shift.sqlite3')


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def run_id(client):
    return client.get('/api/runs').json['manifest']['id']
