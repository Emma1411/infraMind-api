from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models.export import QuoteResponse
from models.project_spec import ProjectSpec
from services.export.quote import NoRecommendation, UnknownQuoteArchitecture, build_quote

router = APIRouter(prefix="/api/export", tags=["export"])


class QuoteRequest(BaseModel):
    spec: ProjectSpec
    arch_id: str | None = None
    client_name: str | None = Field(default=None, max_length=120)
    validity_days: int = Field(default=30, ge=1, le=365)
    margin_percent: float = Field(default=20.0, ge=0, le=100)
    include_alternatives: bool = True


@router.post("/quote", response_model=QuoteResponse)
def quote(payload: QuoteRequest) -> QuoteResponse:
    try:
        return build_quote(
            payload.spec,
            arch_id=payload.arch_id,
            client_name=payload.client_name,
            validity_days=payload.validity_days,
            margin_percent=payload.margin_percent,
            include_alternatives=payload.include_alternatives,
        )
    except UnknownQuoteArchitecture:
        raise HTTPException(status_code=404, detail="Architecture inconnue.")
    except NoRecommendation as exc:
        raise HTTPException(status_code=422, detail=str(exc))