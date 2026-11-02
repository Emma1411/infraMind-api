from typing import Any

from openai import OpenAIError

from models.project_spec import ProjectSpec
from models.report import ArchNote, RawReport, Report, ReportResponse
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable
from services.llm.client import LLMNotConfigured
from services.llm.report_writer import ReportWriterError, write_report
from services.report.payload import build_payload
from services.report.template import template_report
from services.report.validate import validate_raw


def _finalize(raw: RawReport, payload: dict, template: Report) -> Report:
    """Clés inconnues écartées, phrases manquantes complétées par le gabarit, ordre du moteur."""
    fallback = {note.arch_id: note.text for note in template.why_not_others}
    notes = [
        ArchNote(arch_id=arch_id, text=raw.why_not_others.get(arch_id) or fallback[arch_id])
        for arch_id in payload["others_to_explain"]
    ]
    return Report(
        summary=raw.summary.strip(),
        why_this_one=[text.strip() for text in raw.why_this_one],
        why_not_others=notes,
        watch_out=[text.strip() for text in raw.watch_out],
        next_steps=[text.strip() for text in raw.next_steps],
    )


async def build_report(spec: ProjectSpec, client: Any = None, fx: FxTable | None = None) -> ReportResponse:
    result = evaluate(spec, fx=fx)
    payload = build_payload(result)
    template = template_report(result)

    if result.recommended_id is None:
        return ReportResponse(
            recommended_id=None, source="template", fallback_reason="no_recommendation", report=template
        )

    try:
        raw = await write_report(payload, lambda candidate: validate_raw(candidate, payload), client=client)
    except LLMNotConfigured:
        reason = "not_configured"
    except ReportWriterError:
        reason = "invalid_output"
    except OpenAIError:
        reason = "service_error"
    else:
        return ReportResponse(
            recommended_id=result.recommended_id,
            source="ai",
            report=_finalize(raw, payload, template),
        )

    return ReportResponse(
        recommended_id=result.recommended_id, source="template", fallback_reason=reason, report=template
    )