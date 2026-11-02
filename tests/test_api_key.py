import pytest
from fastapi.testclient import TestClient

from config.settings import Settings, get_settings
from main import app
from middlewares.api_key import API_KEY_HEADER, _matches, require_api_key

KEY = "cle-de-test-0123456789abcdef"
SPEC = {"traffic": {"daily_users": "between_100_1000"}}

PROTECTED = [
    ("POST", "/api/analysis/extract", {"text": "Un site de réservation"}),
    ("POST", "/api/analysis/questions", {"spec": {}}),
    ("POST", "/api/analysis/answers", {"spec": {}, "answers": {}}),
    ("POST", "/api/analysis/evaluate", {"spec": {}}),
    ("GET", "/api/guides/available", None),
    ("POST", "/api/guides/hetzner_vps", {"spec": {}}),
    ("POST", "/api/export/quote", {"spec": SPEC}),
    ("POST", "/api/report", {"spec": {}}),
]

client = TestClient(app)


@pytest.fixture
def auth(monkeypatch):
    """Active la vraie protection et permet de choisir la configuration."""
    app.dependency_overrides.pop(require_api_key, None)

    def configure(keys: str = KEY, enabled: bool = True) -> None:
        monkeypatch.setattr(
            "middlewares.api_key.get_settings",
            lambda: Settings(auth_enabled=enabled, api_keys=keys),
        )

    configure()
    return configure


def call(method, path, body, headers=None):
    return client.request(method, path, json=body, headers=headers)


def test_header_name_is_x_api_key():
    assert API_KEY_HEADER == "X-API-Key"


def test_keys_are_split_and_trimmed():
    assert Settings(api_keys=" a , b ,, c ").api_keys_list == ["a", "b", "c"]
    assert Settings(api_keys="").api_keys_list == []


def test_matching_checks_every_key():
    assert _matches("b", ["a", "b"])
    assert not _matches("c", ["a", "b"])
    assert not _matches("", ["a"])
    assert not _matches("a", [])


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_every_route_requires_a_key(auth, method, path, body):
    response = call(method, path, body)
    assert response.status_code == 401
    assert "Clé d'API" in response.json()["detail"]


def test_health_stays_open(auth):
    assert client.get("/health").status_code == 200


def test_wrong_key_is_rejected(auth):
    response = call("POST", "/api/analysis/questions", {"spec": {}}, {API_KEY_HEADER: "mauvaise"})
    assert response.status_code == 401


def test_right_key_is_accepted(auth):
    response = call("POST", "/api/analysis/questions", {"spec": {}}, {API_KEY_HEADER: KEY})
    assert response.status_code == 200


def test_any_configured_key_works_for_rotation(auth):
    auth(keys=f"ancienne-cle-0123456789,{KEY}")
    for key in ("ancienne-cle-0123456789", KEY):
        response = call("GET", "/api/guides/available", None, {API_KEY_HEADER: key})
        assert response.status_code == 200


def test_authentication_can_be_disabled_for_local_work(auth):
    auth(keys="", enabled=False)
    assert call("GET", "/api/guides/available", None).status_code == 200


def test_enabled_without_keys_refuses_everything(auth):
    auth(keys="", enabled=True)
    response = call("GET", "/api/guides/available", None, {API_KEY_HEADER: "n-importe-quoi"})
    assert response.status_code == 503


def test_browser_preflight_needs_no_key_and_allows_the_header(auth):
    origin = get_settings().cors_origins_list[0]
    response = client.options(
        "/api/analysis/evaluate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert response.status_code == 200
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


def test_docs_offer_an_authorize_button():
    schemes = app.openapi()["components"]["securitySchemes"]
    assert any(scheme.get("name") == API_KEY_HEADER for scheme in schemes.values())