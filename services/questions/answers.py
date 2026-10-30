from typing import Any
from pydantic import ValidationError
from models.project_spec import ProjectSpec
from services.questions.bank import QUESTION_BANK

UNKNOWN = "unknown"


class AnswerError(ValueError):
    """Une réponse est invalide ou ne correspond à aucune question."""


def apply_answers(spec: ProjectSpec, answers: dict[str, Any]) -> ProjectSpec:
    data = spec.model_dump(mode="json")
    unknown = set(data.get("unknown", []))

    for path, value in answers.items():
        if path not in QUESTION_BANK:
            raise AnswerError(f"Question inconnue : {path}")
        domain, field = path.split(".", 1)

        if isinstance(value, str) and value == UNKNOWN:
            unknown.add(path)
            continue

        data[domain][field] = value
        unknown.discard(path)

    data["unknown"] = sorted(unknown)

    try:
        return ProjectSpec.model_validate(data)
    except ValidationError as exc:
        raise AnswerError("Une des réponses a une valeur invalide.") from exc