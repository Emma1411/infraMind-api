import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openai import OpenAIError

from main import app
from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable
from services.llm.client import LLMNotConfigured
from services.report.payload import build_payload
from services.report.service import build_report
from services.report.template import template_report

NO_FX = FxTable(per_usd={"USD": 1.0, "CAD": None, "EUR": None})
SPEC = {"traffic": {"daily_users": "between_100_1000"}, "data": {"data_size": "gb_1_10"}}
client = TestClient(app)


class FakeCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        item = self.contents.pop(0)
        if isinstance(item, Exception):
            raise item
        message = SimpleNamespace(content=item)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, contents):
        self.completions = FakeCompletions(contents)
        self.chat = SimpleNamespace(completions=self.completions)


class Boom(OpenAIError):
    pass


def spec(**extra) -> ProjectSpec:
    return ProjectSpec.model_validate({**SPEC, **extra})


def good_json(**changes) -> str:
    template = template_report(evaluate(spec(), fx=NO_FX))
    data = {
        "summary": template.summary,
        "why_this_one": template.why_this_one[:4],
        "why_not_others": {note.arch_id: note.text for note in template.why_not_others},
        "watch_out": template.watch_out,
        "next_steps": template.next_steps,
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


def run(contents, **extra):
    fake = FakeClient(contents)
    response = asyncio.run(build_report(spec(**extra), client=fake, fx=NO_FX))
    return response, fake


def test_valid_output_is_used_as_the_ai_report():
    response, fake = run([good_json()])
    assert response.source == "ai"
    assert response.fallback_reason is None
    assert fake.completions.calls == 1
    assert response.recommended_id is not None
    assert len(response.report.why_not_others) == 4


def test_invalid_output_is_corrected_once():
    bad = good_json(summary="Ça coûte environ 4999 $ par mois.")
    response, fake = run([bad, good_json()])
    assert response.source == "ai"
    assert fake.completions.calls == 2


def test_two_invalid_outputs_fall_back_to_the_template():
    bad = good_json(summary="Lance `docker compose up` maintenant.")
    response, fake = run([bad, "pas du json"])
    assert response.source == "template"
    assert response.fallback_reason == "invalid_output"
    assert fake.completions.calls == 2
    assert response.report.summary


def test_missing_architecture_is_completed_by_the_template():
    result = evaluate(spec(), fx=NO_FX)
    payload = build_payload(result)
    notes = {a: f"Texte pour {a}." for a in payload["others_to_explain"][1:]}
    response, _ = run([good_json(why_not_others=notes)])
    assert response.source == "ai"
    ids = [note.arch_id for note in response.report.why_not_others]
    assert ids == payload["others_to_explain"]


def test_unknown_architecture_keys_are_dropped():
    result = evaluate(spec(), fx=NO_FX)
    payload = build_payload(result)
    notes = {a: f"Texte pour {a}." for a in payload["others_to_explain"]}
    notes["inconnue"] = "ne doit pas apparaître"
    response, _ = run([good_json(why_not_others=notes)])
    assert "inconnue" not in {note.arch_id for note in response.report.why_not_others}


def test_missing_key_falls_back_without_calling_the_service(monkeypatch):
    async def not_configured(*args, **kwargs):
        raise LLMNotConfigured("DEEPSEEK_API_KEY manquante")

    monkeypatch.setattr("services.report.service.write_report", not_configured)
    response = asyncio.run(build_report(spec(), fx=NO_FX))
    assert response.source == "template"
    assert response.fallback_reason == "not_configured"


def test_service_error_falls_back_to_the_template():
    response, _ = run([Boom("indisponible")])
    assert response.source == "template"
    assert response.fallback_reason == "service_error"


def test_no_recommendation_never_calls_the_model():
    fake = FakeClient([good_json()])
    response = asyncio.run(
        build_report(
            spec(constraints={"budget_max_monthly": 5, "budget_currency": "USD"}), client=fake, fx=NO_FX
        )
    )
    assert response.source == "template"
    assert response.fallback_reason == "no_recommendation"
    assert response.recommended_id is None
    assert fake.completions.calls == 0


def test_endpoint_falls_back_when_the_ai_is_not_configured(monkeypatch):
    async def not_configured(*args, **kwargs):
        raise LLMNotConfigured("DEEPSEEK_API_KEY manquante")

    monkeypatch.setattr("services.report.service.write_report", not_configured)
    response = client.post("/api/report", json={"spec": SPEC})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "template"
    assert body["fallback_reason"] == "not_configured"
    assert "« " in body["report"]["summary"]


def test_endpoint_requires_a_spec():
    assert client.post("/api/report", json={}).status_code == 422