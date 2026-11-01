from models.evaluation import ArchitectureResult
from models.project_spec import ProjectSpec
from services.engine.assumptions import Sizing, build_sizing
from services.engine.catalog import Catalog
from services.engine.costing import AWS_FARGATE
from services.guides.hetzner import slugify

REGION = "us-east-1"
EBS_ROOT_GB = "30"

_RDS_KEYS = {"rds_class", "rds_vcpu", "rds_ram_gb", "rds_storage_gb"}
_COMMON = {"region", "app_slug", "monthly_total", "db_cost", "network_cost", "files_cost"} | _RDS_KEYS

ALLOWED_PARAMS_EC2 = frozenset(
    _COMMON | {"ec2_type", "ec2_vcpu", "ec2_ram_gb", "disk_gb", "compute_cost", "ipv4_cost"}
)
ALLOWED_PARAMS_FARGATE = frozenset(
    _COMMON
    | {
        "task_vcpu",
        "task_memory_gib",
        "tasks",
        "task_cpu_units",
        "task_memory_mib",
        "fargate_cost",
        "alb_cost",
    }
)


def build_flags(spec: ProjectSpec) -> frozenset[str]:
    return frozenset({"database"} if build_sizing(spec).has_database else {"no_database"})


def _sum(result: ArchitectureResult, *prefixes: str) -> float:
    return sum(line.monthly for line in result.lines if line.item_id.startswith(prefixes))


def _instance_name(item_id: str) -> str:
    """aws.ec2.t3_small devient t3.small ; aws.rds.db_t4g_small devient db.t4g.small."""
    return item_id.split(".", 2)[2].replace("_", ".")


def _rds_params(result: ArchitectureResult, catalog: Catalog, sizing: Sizing) -> dict[str, str]:
    line = next((l for l in result.lines if l.item_id.startswith("aws.rds.db_")), None)
    if line is None:
        return {key: "" for key in _RDS_KEYS}
    item = catalog.item(line.item_id)
    return {
        "rds_class": _instance_name(line.item_id),
        "rds_vcpu": str(item.vcpu),
        "rds_ram_gb": f"{item.ram_gb:g}",
        "rds_storage_gb": f"{max(20.0, sizing.db_gb):.0f}",
    }


def _common(result: ArchitectureResult, spec: ProjectSpec) -> dict[str, str]:
    return {
        "region": REGION,
        "app_slug": slugify(spec.name),
        "monthly_total": f"{result.cost_low:.2f}",
        "db_cost": f"{_sum(result, 'aws.rds.'):.2f}",
        "network_cost": f"{_sum(result, 'aws.ipv4', 'aws.egress'):.2f}",
        "files_cost": f"{_sum(result, 'aws.s3.'):.2f}",
    }


def build_params_ec2(result: ArchitectureResult, spec: ProjectSpec, catalog: Catalog) -> dict[str, str]:
    sizing = build_sizing(spec)
    ec2_line = next((l for l in result.lines if l.item_id.startswith("aws.ec2.")), None)
    if ec2_line is None:
        raise ValueError("Aucune instance EC2 dans l'estimation.")
    ec2 = catalog.item(ec2_line.item_id)
    return {
        **_common(result, spec),
        **_rds_params(result, catalog, sizing),
        "ec2_type": _instance_name(ec2_line.item_id),
        "ec2_vcpu": str(ec2.vcpu),
        "ec2_ram_gb": f"{ec2.ram_gb:g}",
        "disk_gb": EBS_ROOT_GB,
        "compute_cost": f"{_sum(result, 'aws.ec2.', 'aws.ebs.'):.2f}",
        "ipv4_cost": f"{catalog.monthly_cost('aws.ipv4_public'):.2f}",
    }


def build_params_fargate(result: ArchitectureResult, spec: ProjectSpec, catalog: Catalog) -> dict[str, str]:
    sizing = build_sizing(spec)
    vcpu, gib, tasks = AWS_FARGATE[sizing.tier]
    return {
        **_common(result, spec),
        **_rds_params(result, catalog, sizing),
        "task_vcpu": f"{vcpu:g}",
        "task_memory_gib": f"{gib:g}",
        "tasks": str(tasks),
        "task_cpu_units": str(int(vcpu * 1024)),
        "task_memory_mib": str(int(gib * 1024)),
        "fargate_cost": f"{_sum(result, 'aws.fargate.'):.2f}",
        "alb_cost": f"{_sum(result, 'aws.alb'):.2f}",
    }