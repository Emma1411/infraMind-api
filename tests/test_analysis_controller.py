from fastapi.testclient import TestClient
from controllers import analysis_controller
from main import app
from models.project_spec import ProjectSpec

client = TestClient(app)


def test_empty_text_is_rejected():
    response = client.post("/api/analysis/extract", json={"text": "   "})
    assert response.status_code == 400


def test_too_long_text_is_rejected():
    response = client.post("/api/analysis/extract", json={"text": "a" * 9000})
    assert response.status_code == 413


def test_extract_returns_spec_and_missing_fields(monkeypatch):
    async def fake_extract(text: str) -> ProjectSpec:
        return ProjectSpec.model_validate({"application": {"app_type": "web_app"}})

    monkeypatch.setattr(analysis_controller, "extract_spec", fake_extract)

    response = client.post("/api/analysis/extract", json={"text": "Un site de réservation"})
    assert response.status_code == 200
    data = response.json()
    assert "application.has_background_jobs" in data["missing"]
    assert "application.app_type" not in data["missing"]
    assert data["secrets_masked"] is False