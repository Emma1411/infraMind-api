import pytest
from models.project_spec import ProjectSpec
from services.questions.answers import AnswerError, apply_answers
from services.questions.coverage import FieldStatus, compute_coverage


def test_choice_answer_is_applied():
    spec = apply_answers(ProjectSpec(), {"data.data_size": "gb_1_10"})
    assert spec.data.data_size.value == "gb_1_10"


def test_boolean_answer_is_applied():
    spec = apply_answers(ProjectSpec(), {"application.has_background_jobs": True})
    assert spec.application.has_background_jobs is True


def test_multi_choice_answer_is_applied():
    spec = apply_answers(ProjectSpec(), {"delivery.environments": ["dev", "prod"]})
    assert len(spec.delivery.environments) == 2


def test_unknown_answer_is_recorded():
    spec = apply_answers(ProjectSpec(), {"traffic.daily_users": "unknown"})
    assert "traffic.daily_users" in spec.unknown
    status = {f.path: f.status for f in compute_coverage(spec).fields}
    assert status["traffic.daily_users"] == FieldStatus.UNKNOWN


def test_real_answer_clears_previous_unknown():
    spec = apply_answers(ProjectSpec(), {"traffic.daily_users": "unknown"})
    spec = apply_answers(spec, {"traffic.daily_users": "under_100"})
    assert "traffic.daily_users" not in spec.unknown


def test_invalid_value_is_rejected():
    with pytest.raises(AnswerError):
        apply_answers(ProjectSpec(), {"data.data_size": "énorme"})


def test_unknown_question_is_rejected():
    with pytest.raises(AnswerError):
        apply_answers(ProjectSpec(), {"inconnu.champ": "x"})