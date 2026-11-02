from fastapi import APIRouter
from pydantic import BaseModel

from models.project_spec import ProjectSpec
from models.report import ReportResponse
from services.report.service import build_report

router = APIRouter(prefix="/api/report", tags=["report"])


class ReportRequest(BaseModel):
    spec: ProjectSpec


@router.post("", response_model=ReportResponse)
async def report(payload: ReportRequest) -> ReportResponse:
    return await build_report(payload.spec)