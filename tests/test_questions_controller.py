from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_questions_for_empty_spec_start_with_essentials():
    response = client.post("/api/analysis/questions", json={"spec": {}})
    assert response.status_code == 200
    questions = response.json()["questions"]
    paths = [q["path"] for q in questions]
    assert "application.app_type" in paths
    priorities = [q["priority"] for q in questions]
    assert priorities == sorted(priorities)


def test_answers_update_missing_fields():
    response = client.post(
        "/api/analysis/answers",
        json={"spec": {}, "answers": {"application.app_type": "web_app"}},
    )
    assert response.status_code == 200
    assert "application.app_type" not in response.json()["missing"]


def test_invalid_answer_returns_422():
    response = client.post(
        "/api/analysis/answers",
        json={"spec": {}, "answers": {"data.data_size": "énorme"}},
    )
    assert response.status_code == 422