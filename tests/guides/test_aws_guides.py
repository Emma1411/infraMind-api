import pytest
from fastapi.testclient import TestClient

from main import app
from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.guides.aws import ALLOWED_PARAMS_EC2, ALLOWED_PARAMS_FARGATE
from services.guides.loader import GUIDES_DIR, get_guides
from services.guides.render import malformed_placeholders, placeholders_in
from services.guides.service import build_guide

ARCHS = ["aws_ec2_rds", "aws_fargate_rds"]
ALLOWED = {"aws_ec2_rds": ALLOWED_PARAMS_EC2, "aws_fargate_rds": ALLOWED_PARAMS_FARGATE}
DB_STEPS = {
    "aws_ec2_rds": {"base", "sauvegardes-base", "suppr-donnees", "suppr-base"},
    "aws_fargate_rds": {"base", "reseau-base", "sauvegardes-base", "suppr-donnees", "suppr-base"},
}
OFFICIAL = ("https://docs.aws.amazon.com/", "https://aws.amazon.com/")
SPEC_S = {"traffic": {"daily_users": "between_100_1000"}, "data": {"data_size": "gb_1_10"}}

client = TestClient(app)


def make(**extra) -> ProjectSpec:
    return ProjectSpec.model_validate({**SPEC_S, **extra})


def ids(guide) -> set[str]:
    return {step.id for step in guide.steps + guide.cleanup}


def step(guide, step_id):
    return next(s for s in guide.steps + guide.cleanup if s.id == step_id)


def arch_result(spec, arch_id):
    return next(r for r in evaluate(spec, with_sensitivity=False).ranking if r.id == arch_id)


@pytest.mark.parametrize("arch", ARCHS)
def test_guide_is_loaded(arch):
    assert arch in get_guides()


@pytest.mark.parametrize("arch", ARCHS)
def test_every_step_is_explained_and_actionable(arch):
    guide = get_guides()[arch]
    for s in guide.steps + guide.cleanup:
        assert s.why.strip(), s.id
        assert s.expect.strip(), s.id
        assert s.help.common_cause.strip(), s.id
        assert s.help.search_query.strip(), s.id
        assert s.commands or s.checklist, s.id


@pytest.mark.parametrize("arch", ARCHS)
def test_documentation_links_are_official_aws_pages(arch):
    guide = get_guides()[arch]
    for s in guide.steps + guide.cleanup:
        if s.help.doc_url is not None:
            assert s.help.doc_url.startswith(OFFICIAL), s.id
            assert s.help.doc_label, s.id
    for source in guide.sources:
        assert source.url.startswith(OFFICIAL)


@pytest.mark.parametrize("arch", ARCHS)
def test_placeholders_are_well_formed_and_allowed(arch):
    raw = (GUIDES_DIR / f"{arch}.json").read_text(encoding="utf-8")
    assert malformed_placeholders(raw) == set()
    assert placeholders_in(get_guides()[arch].model_dump_json()) <= ALLOWED[arch]


@pytest.mark.parametrize("arch", ARCHS)
def test_database_steps_depend_on_the_database(arch):
    with_db = ids(build_guide(arch, make()).guide)
    without_db = ids(build_guide(arch, make(data={"database_type": "none"})).guide)
    assert DB_STEPS[arch] <= with_db
    assert not (DB_STEPS[arch] & without_db)
    assert "couts" in without_db and "verification" in without_db


@pytest.mark.parametrize("arch", ARCHS)
def test_rendered_guide_has_no_placeholder_left(arch):
    for spec in (make(), make(data={"database_type": "none"})):
        assert "[[" not in build_guide(arch, spec).guide.model_dump_json()


@pytest.mark.parametrize("arch", ARCHS)
def test_parameters_without_database_are_empty_not_missing(arch):
    params = build_guide(arch, make(data={"database_type": "none"})).guide.parameters
    assert params["rds_class"] == ""
    assert params["db_cost"] == "0.00"
    assert params["region"] == "us-east-1"


@pytest.mark.parametrize("arch", ARCHS)
def test_status_label_says_not_tested(arch):
    assert "pas encore testé en réel" in build_guide(arch, make()).guide.status_label


@pytest.mark.parametrize("arch", ARCHS)
def test_guide_endpoint_returns_the_guide(arch):
    response = client.post(f"/api/guides/{arch}", json={"spec": {**SPEC_S, "name": "Salon Élégance"}})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["guide"]["parameters"]["app_slug"] == "salon-elegance"


def test_ec2_parameters_tier_s():
    params = build_guide("aws_ec2_rds", make()).guide.parameters
    assert params["ec2_type"] == "t3.small"
    assert params["ec2_vcpu"] == "2"
    assert params["ec2_ram_gb"] == "2"
    assert params["rds_class"] == "db.t4g.small"
    assert params["rds_storage_gb"] == "20"
    assert params["disk_gb"] == "30"


def test_ec2_parameters_tier_l():
    params = build_guide("aws_ec2_rds", make(traffic={"daily_users": "over_10000"})).guide.parameters
    assert params["ec2_type"] == "m7i.large"
    assert params["ec2_ram_gb"] == "8"
    assert params["rds_class"] == "db.t4g.medium"


def test_ec2_costs_match_the_evaluation():
    spec = make()
    params = build_guide("aws_ec2_rds", spec).guide.parameters
    arch = arch_result(spec, "aws_ec2_rds")
    db = sum(line.monthly for line in arch.lines if line.item_id.startswith("aws.rds."))
    assert params["monthly_total"] == f"{arch.cost_low:.2f}"
    assert params["db_cost"] == f"{db:.2f}"
    assert params["ipv4_cost"] == "3.65"


def test_ec2_connection_uses_the_ubuntu_user_and_the_key_file():
    code = "\n".join(block.code for block in step(build_guide("aws_ec2_rds", make()).guide, "connexion").commands)
    assert "ubuntu@VOTRE_IP_SERVEUR" in code
    assert "chmod 400" in code


def test_fargate_parameters_by_tier():
    small = build_guide("aws_fargate_rds", make(traffic={"daily_users": "under_100"})).guide.parameters
    assert (small["task_vcpu"], small["task_cpu_units"]) == ("0.5", "512")
    assert (small["task_memory_gib"], small["task_memory_mib"]) == ("1", "1024")
    middle = build_guide("aws_fargate_rds", make()).guide.parameters
    assert (middle["task_vcpu"], middle["task_memory_gib"], middle["tasks"]) == ("1", "2", "1")
    large = build_guide("aws_fargate_rds", make(traffic={"daily_users": "over_10000"})).guide.parameters
    assert (large["task_vcpu"], large["task_memory_gib"], large["tasks"]) == ("2", "4", "2")
    assert large["task_cpu_units"] == "2048"


def test_fargate_costs_match_the_evaluation():
    spec = make()
    params = build_guide("aws_fargate_rds", spec).guide.parameters
    arch = arch_result(spec, "aws_fargate_rds")
    alb = sum(line.monthly for line in arch.lines if line.item_id.startswith("aws.alb"))
    assert params["alb_cost"] == f"{alb:.2f}"
    assert params["monthly_total"] == f"{arch.cost_low:.2f}"


def test_fargate_image_step_uses_ecr_and_a_fargate_compatible_build():
    guide = build_guide("aws_fargate_rds", make(name="Salon Élégance")).guide
    code = "\n".join(block.code for block in step(guide, "image").commands)
    assert "aws ecr create-repository --repository-name salon-elegance --region us-east-1" in code
    assert "aws ecr get-login-password" in code
    assert "--platform linux/amd64" in code
    assert "docker push" in code


def test_fargate_cleanup_removes_the_repository_and_the_cli_user():
    guide = build_guide("aws_fargate_rds", make()).guide
    assert "suppr-image" in ids(guide) and "suppr-iam" in ids(guide)
    assert "--force" in step(guide, "suppr-image").commands[0].code