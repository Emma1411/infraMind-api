import pytest

from main import app
from middlewares.api_key import require_api_key


@pytest.fixture(autouse=True)
def _bypass_api_key():
    """Les tests existants n'envoient pas de clé : l'authentification est testée dans test_api_key.py."""
    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)