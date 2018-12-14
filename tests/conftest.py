import pytest
from pyopereto.client import OperetoClient

@pytest.fixture
def opereto_client():
    return OperetoClient()

