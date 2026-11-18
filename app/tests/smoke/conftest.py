import pytest

from app.integrations.telegram.router import build_dispatcher


@pytest.fixture(scope="session")
def dispatcher():
    return build_dispatcher()
