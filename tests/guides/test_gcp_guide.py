import re

from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.guides.gcp import ALLOWED_PARAMS, MAX_NAME_LENGTH, gcp_safe_name
from services.guides.loader import GUIDES_DIR, get_guides
from services.guides.render import malformed_placeholders, placeholders_in
from services.guides.service import build_guide

ARCH = "gcp_cloud_run_sql"
SPEC_S = {"traffic": {"daily_users": "between_100_1000"}, "data": {"data_size": "gb_1_10"}}
DB_STEPS = {"base", "secret", "deploiement", "sauvegardes", "suppr-donnees"}


def make(**extra) -> ProjectSpec:
    return ProjectSpec.model_validate({**SPEC_S, **extra})


def ids(guide) -> set[str]:
    return {step.id for step in guide.steps + guide.cleanup}


def step(guide, step_id):
    return next(s for s in guide.steps + guide.cleanup if s.id == step_id)


def test_gcp_guide_is_loaded():
    assert ARCH in get_guides()


def test_every_step_is_explained_and_has_help():
    guide = get_guides()[ARCH]
    for s in guide.steps + guide.cleanup:
        assert s.why.strip(), s.id
        assert s.expect.strip(), s.id
        assert s.help.common_cause.strip(), s.id
        assert s.help.search_query.strip(), s.id
        assert s.commands or s.checklist, s.id


def test_documentation_links_are_official_google_pages():
    guide = get_guides()[ARCH]
    for s in guide.steps + guide.cleanup:
        if s.help.doc_url is not None:
            assert s.help.doc_url.startswith("https://cloud.google.com/"), s.id
            assert s.help.doc_label, s.id
    for source in guide.sources:
        assert source.url.startswith("https://cloud.google.com/")


def test_placeholders_are_all_allowed():
    guide = get_guides()[ARCH]
    assert placeholders_in(guide.model_dump_json()) <= ALLOWED_PARAMS


def test_no_guide_file_has_malformed_placeholders():
    for path in GUIDES_DIR.glob("*.json"):
        assert malformed_placeholders(path.read_text(encoding="utf-8")) == set(), path.name


def test_placeholder_keys_may_contain_digits():
    assert placeholders_in("prix [[ipv4_cost]] et [[ram_gb]]") == {"ipv4_cost", "ram_gb"}
    assert malformed_placeholders("[[Mauvais Nom]] et [[ok_1]]") == {"[[Mauvais Nom]]"}


def test_commands_use_single_lines_so_they_work_in_every_terminal():
    for guide in get_guides().values():
        for s in guide.steps + guide.cleanup:
            for block in s.commands:
                if block.language in ("bash", "powershell"):
                    assert "\\\n" not in block.code, (guide.arch_id, s.id)
                    assert "`\n" not in block.code, (guide.arch_id, s.id)


def test_database_steps_present_with_a_database():
    response = build_guide(ARCH, make())
    present = ids(response.guide)
    assert DB_STEPS <= present
    assert "deploiement-sans-base" not in present


def test_database_steps_removed_without_database():
    response = build_guide(ARCH, make(data={"database_type": "none"}))
    present = ids(response.guide)
    assert not (DB_STEPS & present)
    assert "deploiement-sans-base" in present
    assert "verification" in present and "couts" in present


def test_parameters_follow_tier_s():
    params = build_guide(ARCH, make()).guide.parameters
    assert params["region"] == "us-central1"
    assert params["run_vcpu"] == "1"
    assert params["run_memory"] == "2Gi"
    assert params["db_vcpu"] == "1"
    assert params["db_memory_gib"] == "4"
    assert params["db_storage_gb"] == "10"


def test_parameters_follow_a_bigger_project():
    params = build_guide(ARCH, make(traffic={"daily_users": "over_10000"})).guide.parameters
    assert params["run_vcpu"] == "2"
    assert params["run_memory"] == "4Gi"
    assert params["db_vcpu"] == "4"
    assert params["db_memory_gib"] == "16"


def test_background_jobs_switch_to_cpu_always_allocated():
    with_jobs = build_guide(ARCH, make(application={"has_background_jobs": True})).guide
    without_jobs = build_guide(ARCH, make()).guide
    assert with_jobs.parameters["run_extra_flags"] == " --no-cpu-throttling"
    assert "--no-cpu-throttling" in step(with_jobs, "deploiement").commands[0].code
    assert without_jobs.parameters["run_extra_flags"] == ""
    assert "--no-cpu-throttling" not in step(without_jobs, "deploiement").commands[0].code


def test_deploy_command_connects_the_service_to_the_database_instance():
    guide = build_guide(ARCH, make(name="Salon Élégance")).guide
    code = step(guide, "deploiement").commands[0].code
    instance = guide.parameters["instance_name"]
    assert "--add-cloudsql-instances" in code
    assert f"VOTRE_ID_PROJET:us-central1:{instance}" in code
    assert "--set-secrets DB_PASSWORD=db-password:latest" in code
    assert "--max-instances 2" in code


def test_names_are_built_from_the_project_name():
    params = build_guide(ARCH, make(name="Salon Élégance")).guide.parameters
    assert params["service_name"] == "salon-elegance"
    assert params["instance_name"] == "salon-elegance-db"


def test_safe_names_start_with_a_letter_and_stay_short():
    assert gcp_safe_name("3d-print") == "app-3d-print"
    long_name = gcp_safe_name("x" * 39 + "-y", "-db")
    assert len(long_name) <= MAX_NAME_LENGTH
    assert long_name.endswith("-db")
    assert "--" not in long_name
    assert len(gcp_safe_name("a" * 80)) <= MAX_NAME_LENGTH


def test_cost_parameters_match_the_evaluation():
    spec = make()
    params = build_guide(ARCH, spec).guide.parameters
    architecture = next(r for r in evaluate(spec, with_sensitivity=False).ranking if r.id == ARCH)
    sql = sum(line.monthly for line in architecture.lines if line.item_id.startswith("gcp.cloud_sql."))
    assert params["sql_cost"] == f"{sql:.2f}"
    assert params["monthly_total"] == f"{architecture.cost_low:.2f}"


def test_rendered_guide_has_no_placeholder_left():
    for spec in (make(), make(data={"database_type": "none"})):
        assert "[[" not in build_guide(ARCH, spec).guide.model_dump_json()


def test_status_label_says_not_tested():
    label = build_guide(ARCH, make()).guide.status_label
    assert "pas encore testé en réel" in label


def test_guide_endpoint_returns_the_gcp_guide():
    from fastapi.testclient import TestClient

    from main import app

    response = TestClient(app).post(f"/api/guides/{ARCH}", json={"spec": SPEC_S})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["guide"]["parameters"]["service_name"] == "mon-application"