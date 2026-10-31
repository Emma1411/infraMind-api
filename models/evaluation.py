from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    recommended = "recommended"
    eligible = "eligible"
    eliminated = "eliminated"


class CostLine(BaseModel):
    item_id: str
    label: str
    monthly: float
    detail: str = ""
    to_verify: bool = False


class UnpricedLine(BaseModel):
    item_id: str
    label: str
    reason: str


class CriterionScore(BaseModel):
    criterion: str
    score: float
    weight: float
    why: str


class WeightInfo(BaseModel):
    criterion: str
    weight: float


class ArchitectureResult(BaseModel):
    id: str
    provider: str
    label: str
    summary: str
    verdict: Verdict
    eliminated_reasons: list[str] = Field(default_factory=list)
    cost_low: float
    cost_high: float
    cost_low_display: float | None = None
    cost_high_display: float | None = None
    estimate_complete: bool
    needs_verification: bool
    lines: list[CostLine] = Field(default_factory=list)
    unpriced: list[UnpricedLine] = Field(default_factory=list)
    scores: list[CriterionScore] = Field(default_factory=list)
    total_score: float
    requirements_unmet: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    maintenance_hours_per_month: float
    price_basis: str


class EvaluationResult(BaseModel):
    currency: str = "USD"
    display_currency: str | None = None
    fx_rate: float | None = None
    fx_as_of: str | None = None
    pricing_disclaimer: str
    tier: str
    tier_label: str
    assumptions: list[str]
    weights: list[WeightInfo]
    weight_reasons: list[str]
    global_warnings: list[str]
    ranking: list[ArchitectureResult]
    recommended_id: str | None = None
    coverage_missing: list[str] = Field(default_factory=list)