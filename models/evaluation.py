from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    recommended = "recommended"
    eligible = "eligible"
    eliminated = "eliminated"


class BudgetRisk(str, Enum):
    none = "none"          # sous le budget, même au palier supérieur
    possible = "possible"  # sous le budget au palier courant, au-dessus au palier supérieur
    over = "over"          # au-dessus du budget dès le palier courant


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


class AvailabilityDetail(BaseModel):
    application_score: int
    application_why: str
    database_score: int | None = None
    database_why: str | None = None
    overall_score: int
    overall_why: str


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
    within_budget_low: bool | None = None
    within_budget_high: bool | None = None
    budget_risk: BudgetRisk | None = None
    estimate_complete: bool
    needs_verification: bool
    lines: list[CostLine] = Field(default_factory=list)
    unpriced: list[UnpricedLine] = Field(default_factory=list)
    scores: list[CriterionScore] = Field(default_factory=list)
    total_score: float
    availability: AvailabilityDetail
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