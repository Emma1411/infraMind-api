from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.guide import GuideResponse
from models.project_spec import ProjectSpec
from services.guides.loader import get_guides
from services.guides.service import UnknownArchitecture, build_guide

router = APIRouter(prefix="/api/guides", tags=["guides"])


class GuideRequest(BaseModel):
    spec: ProjectSpec


@router.get("/available", response_model=list[str])
def available() -> list[str]:
    return sorted(get_guides())


@router.post("/{arch_id}", response_model=GuideResponse)
def guide(arch_id: str, payload: GuideRequest) -> GuideResponse:
    try:
        return build_guide(arch_id, payload.spec)
    except UnknownArchitecture:
        raise HTTPException(status_code=404, detail="Architecture inconnue.")