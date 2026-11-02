from typing import Literal
from pydantic import BaseModel, Field


class ArchNote(BaseModel):
    arch_id: str
    text: str


class Report(BaseModel):
    summary: str
    why_this_one: list[str] = Field(default_factory=list)
    why_not_others: list[ArchNote] = Field(default_factory=list)
    watch_out: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


FallbackReason = Literal["not_configured", "service_error", "invalid_output", "no_recommendation"]


class ReportResponse(BaseModel):
    recommended_id: str | None = None
    source: Literal["ai", "template"]
    fallback_reason: FallbackReason | None = None
    report: Report


class RawReport(BaseModel):
    """Ce que l'IA renvoie, avant validation."""

    summary: str
    why_this_one: list[str] = Field(default_factory=list)
    why_not_others: dict[str, str] = Field(default_factory=dict)
    watch_out: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)