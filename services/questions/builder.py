from models.project_spec import DOMAINS, ProjectSpec
from models.question import Question, QuestionState, QuestionStatus
from services.questions.bank import QUESTION_BANK
from services.questions.coverage import compute_coverage


def build_questions(paths: list[str]) -> list[Question]:
    """Questions pour les champs manquants : essentielles d'abord, puis par domaine."""
    questions = [QUESTION_BANK[p] for p in paths if p in QUESTION_BANK]
    return sorted(questions, key=lambda q: (q.priority, DOMAINS.index(q.domain)))


def build_question_states(spec: ProjectSpec) -> list[QuestionState]:
    """Toutes les questions applicables au projet, avec la valeur déjà connue de chacune."""
    report = compute_coverage(spec)
    data = spec.model_dump(mode="json")
    states: list[QuestionState] = []
    for item in report.fields:
        question = QUESTION_BANK.get(item.path)
        if question is None:
            continue
        states.append(
            QuestionState(
                **question.model_dump(),
                status=QuestionStatus(item.status.value),
                value=data[item.domain][item.field],
            )
        )
    return sorted(states, key=lambda state: (state.priority, DOMAINS.index(state.domain)))