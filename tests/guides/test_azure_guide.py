from fastapi.testclient import TestClient

from main import app
from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.guides.azure import ALLOWED_PARAMS
from services.guides.loader import GUIDES_DIR, get_guides
from services.guides.render import malformed_placeholders, placeholders_in
from services.guides.service import build_guide

ARCH = "azure_vm_postgres"
DB_STEPS = {"base", "sauvegardes-base", "suppr-donnees"}
SPEC_S = {"traffic": {"daily_users": "between_100_1000"}, "data": {"data_size": "gb_1_10"}}

client = TestClient(app)


def make(**extra) -> ProjectSpec:
    return ProjectSpec.model_validate({**SPEC_S, **extra})


def ids(guide) -> set[str]:
    return {step.id for step in guide.steps + guide.cleanup}


def step(guide, step_id):
    return next(s for s in guide.steps + guide.cleanup if s.id == step_id)


def code_of(guide, step_id) -> str:
    return "\n".join(block.code for block in step(guide, step_id).commands)


def test_azure_guide_is_loaded():
    assert ARCH in get_guides()


def test_every_step_is_explained_and_actionable():
    for s in get_guides()[ARCH].steps + get_guides()[ARCH].cleanup:
        assert s.why.strip(), s.id
        assert s.expect.strip(), s.id
        assert s.help.common_cause.strip(), s.id
        assert s.help.search_query.strip(), s.id
        assert s.commands or s.checklist, s.id


def test_documentation_links_are_official_microsoft_pages():
    guide = get_guides()[ARCH]
    for s in guide.steps + guide.cleanup:
        if s.help.doc_url is not None:
            assert s.help.doc_url.startswith("https://learn.microsoft.com/"), s.id
            assert s.help.doc_label, s.id
    for source in guide.sources:
        assert source.url.startswith("https://learn.microsoft.com/")


def test_placeholders_are_well_formed_and_allowed():
    raw = (GUIDES_DIR / f"{ARCH}.json").read_text(encoding="utf-8")
    assert malformed_placeholders(raw) == set()
    assert placeholders_in(get_guides()[ARCH].model_dump_json()) <= ALLOWED_PARAMS


def test_database_steps_depend_on_the_database():
    with_db = ids(build_guide(ARCH, make()).guide)
    without_db = ids(build_guide(ARCH, make(data={"database_type": "none"})).guide)
    assert DB_STEPS <= with_db
    assert not (DB_STEPS & without_db)
    assert {"vm", "ports", "couts", "suppr-groupe"} <= without_db


def test_rendered_guide_has_no_placeholder_left():
    for spec in (make(), make(data={"database_type": "none"})):
        assert "[[" not in build_guide(ARCH, spec).guide.model_dump_json()


def test_parameters_tier_s():
    params = build_guide(ARCH, make()).guide.parameters
    assert params["region"] == "eastus"
    assert params["vm_size"] == "Standard_B2s"
    assert params["pg_sku"] == "Standard_B2s"
    assert params["pg_storage_gb"] == "32"
    assert params["resource_group"] == "mon-application-rg"


def test_parameters_tier_l():
    params = build_guide(ARCH, make(traffic={"daily_users": "over_10000"})).guide.parameters
    assert params["vm_size"] == "Standard_D4s_v5"
    assert params["pg_sku"] == "Standard_B4ms"


def test_storage_follows_the_standard_azure_size():
    params = build_guide(ARCH, make(data={"data_size": "gb_10_100"})).guide.parameters
    assert params["pg_storage_gb"] == "128"


def test_names_are_built_from_the_project_name():
    params = build_guide(ARCH, make(name="Salon Élégance")).guide.parameters
    assert params["resource_group"] == "salon-elegance-rg"
    assert params["pg_server_name"] == "salon-elegance-pg"


def test_parameters_without_database_are_empty_not_missing():
    params = build_guide(ARCH, make(data={"database_type": "none"})).guide.parameters
    assert params["pg_sku"] == ""
    assert params["db_cost"] == "0.00"


def test_costs_match_the_evaluation():
    spec = make()
    params = build_guide(ARCH, spec).guide.parameters
    arch = next(r for r in evaluate(spec, with_sensitivity=False).ranking if r.id == ARCH)
    db = sum(line.monthly for line in arch.lines if line.item_id.startswith("azure.postgresql."))
    assert params["monthly_total"] == f"{arch.cost_low:.2f}"
    assert params["db_cost"] == f"{db:.2f}"


def test_vm_and_database_commands_use_the_confirmed_options():
    guide = build_guide(ARCH, make(name="Salon Élégance")).guide
    assert "az group create --name salon-elegance-rg --location eastus" in code_of(guide, "groupe")
    vm = code_of(guide, "vm")
    assert "--image Ubuntu2204" in vm and "--generate-ssh-keys" in vm and "--size Standard_B2s" in vm
    db = code_of(guide, "base")
    assert "--tier Burstable" in db and "--public-access None" in db and "--database-name appdb" in db
    assert "firewall-rule create" in db


def test_ports_are_opened_with_distinct_priorities():
    code = code_of(build_guide(ARCH, make()).guide, "ports")
    assert "--port 80 --priority 900" in code
    assert "--port 443 --priority 901" in code


def test_cleanup_deletes_the_resource_group():
    code = code_of(build_guide(ARCH, make(name="Salon Élégance")).guide, "suppr-groupe")
    assert "az group delete --name salon-elegance-rg --yes --no-wait" in code


def test_costs_step_warns_about_the_system_disk_difference():
    text = " ".join(step(build_guide(ARCH, make()).guide, "couts").checklist)
    assert "Premium SSD v2" in text


def test_status_label_says_not_tested():
    assert "pas encore testé en réel" in build_guide(ARCH, make()).guide.status_label


def test_guide_endpoint_returns_the_azure_guide():
    response = client.post(f"/api/guides/{ARCH}", json={"spec": SPEC_S})
    assert response.status_code == 200
    assert response.json()["available"] is True