from models.question import QuestionType
from services.questions.bank import QUESTION_BANK
from services.questions.builder import build_questions
from services.questions.coverage import REQUIRED_FIELDS


def test_every_required_field_has_a_question():
    for domain, fields in REQUIRED_FIELDS.items():
        for field in fields:
            assert f"{domain}.{field}" in QUESTION_BANK


def test_choice_questions_have_options():
    for question in QUESTION_BANK.values():
        if question.type in (QuestionType.single_choice, QuestionType.multi_choice):
            assert len(question.options) >= 2, question.path


def test_every_question_explains_why():
    for question in QUESTION_BANK.values():
        assert question.why.strip(), question.path


def test_essential_questions_come_first():
    questions = build_questions(list(QUESTION_BANK.keys()))
    priorities = [q.priority for q in questions]
    assert priorities == sorted(priorities)


def test_only_requested_paths_are_returned():
    questions = build_questions(["traffic.daily_users", "chemin.inexistant"])
    assert [q.path for q in questions] == ["traffic.daily_users"]