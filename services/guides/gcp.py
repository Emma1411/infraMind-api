from models.evaluation import ArchitectureResult
from models.project_spec import ProjectSpec
from services.engine.assumptions import build_sizing
from services.engine.catalog import Catalog
from services.engine.costing import GCP_RUN_INSTANCE, GCP_SQL
from services.guides.hetzner import slugify

REGION = "us-central1"
MAX_INSTANCES = "2"
MAX_NAME_LENGTH = 40

ALLOWED_PARAMS = frozenset(
    {
        "region",
        "app_slug",
        "service_name",
        "instance_name",
        "run_vcpu",
        "run_memory",
        "run_extra_flags",
        "billing_mode_text",
        "max_instances",
        "db_vcpu",
        "db_memory_gib",
        "db_storage_gb",
        "monthly_total",
        "run_cost",
        "sql_cost",
        "egress_cost",
    }
)


def gcp_safe_name(slug: str, suffix: str = "") -> str:
    """Nom valide pour Cloud Run et Cloud SQL : commence par une lettre, 40 caractères au plus."""
    base = slug if slug[:1].isalpha() else f"app-{slug}"
    room = MAX_NAME_LENGTH - len(suffix)
    return base[:room].rstrip("-") + suffix


def _sum(result: ArchitectureResult, prefix: str) -> float:
    return sum(line.monthly for line in result.lines if line.item_id.startswith(prefix))


def build_flags(spec: ProjectSpec) -> frozenset[str]:
    return frozenset({"database"} if build_sizing(spec).has_database else {"no_database"})


def build_params(result: ArchitectureResult, spec: ProjectSpec, catalog: Catalog) -> dict[str, str]:
    sizing = build_sizing(spec)
    run_vcpu, run_gib = GCP_RUN_INSTANCE[sizing.tier]
    db_vcpu, db_ram = GCP_SQL[sizing.tier]
    slug = slugify(spec.name)

    if sizing.instance_billing:
        extra_flags = " --no-cpu-throttling"
        billing_mode = (
            "CPU alloué en permanence (facturation à l'instance), parce que ton application a des "
            "tâches en arrière-plan ou du temps réel"
        )
    else:
        extra_flags = ""
        billing_mode = "CPU alloué seulement pendant les requêtes (facturation à la requête)"

    return {
        "region": REGION,
        "app_slug": slug,
        "service_name": gcp_safe_name(slug),
        "instance_name": gcp_safe_name(slug, "-db"),
        "run_vcpu": f"{run_vcpu:g}",
        "run_memory": f"{run_gib:g}Gi",
        "run_extra_flags": extra_flags,
        "billing_mode_text": billing_mode,
        "max_instances": MAX_INSTANCES,
        "db_vcpu": str(db_vcpu),
        "db_memory_gib": f"{db_ram:g}",
        "db_storage_gb": f"{max(10.0, sizing.db_gb):.0f}",
        "monthly_total": f"{result.cost_low:.2f}",
        "run_cost": f"{_sum(result, 'gcp.cloud_run.'):.2f}",
        "sql_cost": f"{_sum(result, 'gcp.cloud_sql.'):.2f}",
        "egress_cost": f"{_sum(result, 'gcp.egress.'):.2f}",
    }