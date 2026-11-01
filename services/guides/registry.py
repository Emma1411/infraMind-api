from collections.abc import Callable
from dataclasses import dataclass

from models.evaluation import ArchitectureResult
from models.project_spec import ProjectSpec
from services.engine.catalog import Catalog
from services.guides import aws, azure, gcp, hetzner

ParamBuilder = Callable[[ArchitectureResult, ProjectSpec, Catalog], dict[str, str]]
FlagBuilder = Callable[[ProjectSpec], frozenset[str]]


def _no_flags(spec: ProjectSpec) -> frozenset[str]:
    return frozenset()


@dataclass(frozen=True)
class GuideProvider:
    build_params: ParamBuilder
    allowed_params: frozenset[str]
    build_flags: FlagBuilder = _no_flags


GUIDE_PROVIDERS: dict[str, GuideProvider] = {
    "hetzner_vps": GuideProvider(hetzner.build_params, hetzner.ALLOWED_PARAMS),
    "gcp_cloud_run_sql": GuideProvider(gcp.build_params, gcp.ALLOWED_PARAMS, gcp.build_flags),
    "aws_ec2_rds": GuideProvider(aws.build_params_ec2, aws.ALLOWED_PARAMS_EC2, aws.build_flags),
    "aws_fargate_rds": GuideProvider(aws.build_params_fargate, aws.ALLOWED_PARAMS_FARGATE, aws.build_flags),
    "azure_vm_postgres": GuideProvider(azure.build_params, azure.ALLOWED_PARAMS, azure.build_flags),
}