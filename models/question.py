from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    boolean = "boolean"
    number = "number"


class Option(BaseModel):
    value: str
    label: str


class Question(BaseModel):
    path: str
    domain: str
    type: QuestionType
    text: str
    why: str
    options: list[Option] = Field(default_factory=list)
    priority: int = 1  # 1 = essentiel, 2 = détail
    allow_unknown: bool = True


class QuestionStatus(str, Enum):
    known = "known"      # la valeur est déjà dans le projet (détectée dans le texte ou répondue)
    missing = "missing"
    unknown = "unknown"  # l'utilisateur a répondu « je ne sais pas »


class QuestionState(Question):
    """Une question avec la valeur qu'elle a déjà : pour afficher le pré-rempli."""

    status: QuestionStatus
    value: Any = None