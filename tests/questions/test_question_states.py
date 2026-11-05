from fastapi.testclient import TestClient

from main import app
from models.project_spec import ProjectSpec
from services.questions.builder import build_question_states, build_questions
from services.questions.coverage import compute_coverage

client = TestClient(app)


def states(**overrides):
    return build_question_states(ProjectSpec.model_validate(overrides))


def by_path(items):
    return {item.path: item for item in items}


def test_empty_spec_has_only_missing_questions():
    items = states()
    assert items
    assert all(item.status.value == "missing" for item in items)
    assert all(item.value in (None, []) for item in items)


def test_known_value_is_returned_with_its_status():
    item = by_path(states(traffic={"daily_users": "between_100_1000"}))["traffic.daily_users"]
    assert item.status.value == "known"
    assert item.value == "between_100_1000"


def test_false_counts_as_a_known_value():
    item = by_path(states(data={"has_file_uploads": False}))["data.has_file_uploads"]
    assert item.status.value == "known"
    assert item.value is False


def test_list_value_is_returned():
    item = by_path(states(delivery={"environments": ["dev", "prod"]}))["delivery.environments"]
    assert item.status.value == "known"
    assert item.value == ["dev", "prod"]


def test_unknown_answer_has_its_own_status():
    item = by_path(states(unknown=["traffic.daily_users"]))["traffic.daily_users"]
    assert item.status.value == "unknown"


def test_inapplicable_questions_are_left_out():
    items = by_path(states(data={"database_type": "none", "has_file_uploads": False}))
    assert "backups.acceptable_data_loss" not in items
    assert "data.data_size" not in items


def test_missing_states_match_the_old_missing_list():
    spec = ProjectSpec.model_validate(
        {"traffic": {"daily_users": "under_100"}, "application": {"app_type": "web_app"}}
    )
    missing = [field.path for field in compute_coverage(spec).missing]
    from_states = [item.path for item in build_question_states(spec) if item.status.value == "missing"]
    assert sorted(from_states) == sorted(missing)
    assert sorted(question.path for question in build_questions(missing)) == sorted(missing)


def test_essential_questions_come_first():
    priorities = [item.priority for item in states()]
    assert priorities == sorted(priorities)


def test_endpoint_returns_status_and_value():
    response = client.post(
        "/api/analysis/question-states", json={"spec": {"traffic": {"daily_users": "under_100"}}}
    )
    assert response.status_code == 200
    body = response.json()
    item = next(question for question in body["questions"] if question["path"] == "traffic.daily_users")
    assert item["status"] == "known"
    assert item["value"] == "under_100"
    assert "domain_status" in body