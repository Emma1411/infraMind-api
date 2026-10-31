from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ARCHITECTURES_PATH = Path(__file__).resolve().parents[2] / "data" / "architectures.json"

# Critères notés à la main. La disponibilité est notée à part (application et base).
RATED_CRITERIA = ("security", "performance", "scalability", "maintenance", "portability", "rollback")

# Ordre d'affichage des scores
SCORE_ORDER = (
    "cost",
    "security",
    "performance",
    "availability",
    "scalability",
    "maintenance",
    "portability",
    "rollback",
)


class Rating(BaseModel):
    score: int = Field(ge=1, le=5)
    why: str = Field(min_length=1)


class ArchitectureDef(BaseModel):
    id: str
    provider: str
    label: str
    summary: str
    ratings: dict[str, Rating]
    availability_app: Rating
    availability_db: Rating
    rpo_class: Literal["daily", "point_in_time"]
    requires_ops: bool
    maintenance_hours_per_month: float = Field(ge=0)

    @model_validator(mode="after")
    def _all_criteria_rated(self) -> "ArchitectureDef":
        if set(self.ratings) != set(RATED_CRITERIA):
            raise ValueError(f"{self.id} : les critères notés doivent être {RATED_CRITERIA}")
        return self


class ArchitecturesFile(BaseModel):
    architectures: list[ArchitectureDef]


@lru_cache
def get_architectures() -> list[ArchitectureDef]:
    data = ArchitecturesFile.model_validate_json(ARCHITECTURES_PATH.read_text(encoding="utf-8"))
    return data.architectures