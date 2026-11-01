from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CommandBlock(BaseModel):
    label: str
    language: Literal["powershell", "bash", "yaml", "text"] = "bash"
    code: str = Field(min_length=1)
    os: Literal["windows", "macos_linux"] | None = None


class StepHelp(BaseModel):
    common_cause: str = Field(min_length=1)
    doc_url: str | None = None
    doc_label: str | None = None
    search_query: str = Field(min_length=1)
    youtube_url: str | None = None  # calculé au rendu


class GuideStep(BaseModel):
    id: str
    title: str
    where: Literal["console", "local", "server"]
    why: str = Field(min_length=1)
    checklist: list[str] = Field(default_factory=list)
    commands: list[CommandBlock] = Field(default_factory=list)
    expect: str = Field(min_length=1)
    warning: str | None = None
    optional: bool = False
    only_if: Literal["database", "no_database"] | None = None
    help: StepHelp



class GuideSource(BaseModel):
    label: str
    url: str


class GuideDef(BaseModel):
    arch_id: str
    title: str
    intro: str
    prerequisites: list[str]
    steps: list[GuideStep]
    cleanup: list[GuideStep]
    limits: list[str]
    sources: list[GuideSource]
    written_from_docs_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    tested_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def _unique_ids(self) -> "GuideDef":
        ids = [step.id for step in self.steps + self.cleanup]
        if len(ids) != len(set(ids)):
            raise ValueError("Identifiants d'étapes en double")
        return self


class RenderedGuide(GuideDef):
    parameters: dict[str, str]
    status_label: str


class GuideFallback(BaseModel):
    message: str
    youtube_url: str


class GuideResponse(BaseModel):
    arch_id: str
    available: bool
    guide: RenderedGuide | None = None
    fallback: GuideFallback | None = None