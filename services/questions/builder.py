from models.project_spec import DOMAINS
from models.question import Question
from services.questions.bank import QUESTION_BANK


def build_questions(paths: list[str]) -> list[Question]:
    """Questions pour les champs manquants : essentielles d'abord, puis par domaine."""
    questions = [QUESTION_BANK[p] for p in paths if p in QUESTION_BANK]
    return sorted(questions, key=lambda q: (q.priority, DOMAINS.index(q.domain)))