import pytest
from fastapi.testclient import TestClient

from main import app
from models.project_spec import ProjectSpec
from services.engine.catalog import get_catalog
from services.engine.evaluate import evaluate
from services.guides.hetzner import ALLOWED_PARAMS, slugify
from services.guides.loader import get_guides
from services.guides.render import placeholders_in, youtube_search_url
from services.guides.service import build_guide

client = TestClient(app)


def all_steps(guide):
    return guide.steps + guide.cleanup


def test_hetzner_guide_is_loaded():
    assert "hetzner_vps" in get_guides()


def test_every_step_is_explained_and_has_help():
    for step in all_steps(get_guides()["hetzner_vps"]):
        assert step.why.strip(), step.id
        assert step.expect.strip(), step.id
        assert step.help.common_cause.strip(), step.id
        assert step.help.search_query.strip(), step.id


def test_every_step_with_commands_or_checklist_is_actionable():
    for step in all_steps(get_guides()["hetzner_vps"]):
        assert step.commands or step.checklist, step.id


def test_documentation_links_are_official_hetzner_pages():
    guide = get_guides()["hetzner_vps"]
    for step in all_steps(guide):
        if step.help.doc_url is not None:
            assert step.help.doc_url.startswith("https://docs.hetzner.com/cloud/"), step.id
            assert step.help.doc_label, step.id
    for source in guide.sources:
        assert source.url.startswith("https://docs.hetzner.com/cloud/")


def test_placeholders_are_all_allowed():
    guide = get_guides()["hetzner_vps"]
    assert placeholders_in(guide.model_dump_json()) <= ALLOWED_PARAMS


def test_commands_never_use_the_square_bracket_placeholder_syntax_by_mistake():
    for step in all_steps(get_guides()["hetzner_vps"]):
        for block in step.commands:
            assert "[[" not in block.code.replace("[[app_slug]]", ""), step.id


def test_guide_is_not_marked_as_tested():
    assert get_guides()["hetzner_vps"].tested_on is None


def test_rendered_guide_has_no_placeholder_left():
    response = build_guide("hetzner_vps", ProjectSpec.model_validate({"traffic": {"daily_users": "between_100_1000"}}))
    assert response.available
    assert "[[" not in response.guide.model_dump_json()


def test_rendered_guide_uses_the_evaluated_server_and_cost():
    spec = ProjectSpec.model_validate({"traffic": {"daily_users": "between_100_1000"}})
    response = build_guide("hetzner_vps", spec)
    params = response.guide.parameters
    assert params["server_type"] == "CPX21"
    assert params["included_traffic"] == "2 To"
    arch = next(r for r in evaluate(spec, with_sensitivity=False).ranking if r.id == "hetzner_vps")
    assert params["monthly_total"] == f"{arch.cost_low:.2f}"
    assert params["backup_cost"] == "7.50"
    assert "CPX21" in response.guide.intro


def test_rendered_guide_follows_a_bigger_project():
    spec = ProjectSpec.model_validate({"traffic": {"daily_users": "over_10000"}})
    assert build_guide("hetzner_vps", spec).guide.parameters["server_type"] == "CPX41"


def test_unknown_traffic_quota_is_flagged_not_invented():
    spec = ProjectSpec.model_validate({"traffic": {"daily_users": "over_10000"}})
    params = build_guide("hetzner_vps", spec).guide.parameters
    assert params["included_traffic"] == "4 To"
    assert get_catalog().item("hetzner.ccx43").included_traffic_tb is None


def test_every_step_gets_a_youtube_search_link():
    response = build_guide("hetzner_vps", ProjectSpec())
    for step in all_steps(response.guide):
        assert step.help.youtube_url.startswith("https://www.youtube.com/results?search_query=")


def test_youtube_url_is_encoded():
    url = youtube_search_url("Hetzner Cloud créer un serveur")
    assert " " not in url
    assert url.startswith("https://www.youtube.com/results?search_query=Hetzner+Cloud")


def test_status_label_says_not_tested():
    label = build_guide("hetzner_vps", ProjectSpec()).guide.status_label
    assert "pas encore testé en réel" in label
    assert "2026-10-31" in label


def test_slugify():
    assert slugify("Salon de coiffure Élégance !") == "salon-de-coiffure-elegance"
    assert slugify(None) == "mon-application"
    assert slugify("???") == "mon-application"


def test_architecture_without_guide_returns_fallback():
    response = build_guide("aws_ec2_rds", ProjectSpec())
    assert not response.available
    assert response.guide is None
    assert response.fallback.youtube_url.startswith("https://www.youtube.com/results")


def test_available_endpoint_lists_guides():
    response = client.get("/api/guides/available")
    assert response.status_code == 200
    assert "hetzner_vps" in response.json()


def test_guide_endpoint_returns_a_rendered_guide():
    response = client.post(
        "/api/guides/hetzner_vps",
        json={"spec": {"name": "Salon Élégance", "traffic": {"daily_users": "between_100_1000"}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["guide"]["parameters"]["app_slug"] == "salon-elegance"
    assert len(body["guide"]["steps"]) >= 10


def test_guide_endpoint_fallback_for_missing_guide():
    response = client.post("/api/guides/azure_vm_postgres", json={"spec": {}})
    assert response.status_code == 200
    assert response.json()["available"] is False

def test_guide_endpoint_unknown_architecture_is_404():
    assert client.post("/api/guides/inexistante", json={"spec": {}}).status_code == 404

