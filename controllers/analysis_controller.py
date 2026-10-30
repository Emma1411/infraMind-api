import logging
from typing import Any
from fastapi import APIRouter, HTTPException
from openai import OpenAIError
from pydantic import BaseModel
from config.settings import get_settings
from models.project_spec import ProjectSpec
from models.question import Question
from services.llm.client import LLMNotConfigured
from services.llm.extraction import ExtractionError, extract_spec
from services.questions.answers import AnswerError, apply_answers
from services.questions.builder import build_questions
from services.questions.coverage import compute_coverage
from utils.sanitize import mask_secrets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class ExtractRequest(BaseModel):
    text: str


class ExtractResponse(BaseModel):
    spec: ProjectSpec
    missing: list[str]
    domain_status: dict[str, str]
    secrets_masked: bool


class QuestionsRequest(BaseModel):
    spec: ProjectSpec


class QuestionsResponse(BaseModel):
    questions: list[Question]
    domain_status: dict[str, str]


class AnswersRequest(BaseModel):
    spec: ProjectSpec
    answers: dict[str, Any]


class AnswersResponse(BaseModel):
    spec: ProjectSpec
    missing: list[str]
    domain_status: dict[str, str]
    is_complete: bool


@router.post("/extract", response_model=ExtractResponse)
async def extract(payload: ExtractRequest) -> ExtractResponse:
    settings = get_settings()
    text = payload.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Le cahier des charges est vide.")
    if len(text) > settings.max_input_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Texte trop long : {settings.max_input_chars} caractères maximum.",
        )

    clean_text = mask_secrets(text)

    try:
        spec = await extract_spec(clean_text)
    except LLMNotConfigured:
        raise HTTPException(status_code=503, detail="Le service d'IA n'est pas configuré.")
    except ExtractionError:
        raise HTTPException(
            status_code=422,
            detail="L'IA n'a pas pu structurer ce texte. Précise ton projet et réessaie.",
        )
    except OpenAIError:
        logger.exception("Erreur lors de l'appel au service d'IA")
        raise HTTPException(status_code=502, detail="Le service d'IA est indisponible.")

    report = compute_coverage(spec)
    return ExtractResponse(
        spec=spec,
        missing=[f.path for f in report.missing],
        domain_status=report.domain_status(),
        secrets_masked=clean_text != text,
    )


@router.post("/questions", response_model=QuestionsResponse)
def questions(payload: QuestionsRequest) -> QuestionsResponse:
    report = compute_coverage(payload.spec)
    return QuestionsResponse(
        questions=build_questions([f.path for f in report.missing]),
        domain_status=report.domain_status(),
    )


@router.post("/answers", response_model=AnswersResponse)
def answers(payload: AnswersRequest) -> AnswersResponse:
    try:
        spec = apply_answers(payload.spec, payload.answers)
    except AnswerError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    report = compute_coverage(spec)
    return AnswersResponse(
        spec=spec,
        missing=[f.path for f in report.missing],
        domain_status=report.domain_status(),
        is_complete=report.is_complete,
    )