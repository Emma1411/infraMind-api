from collections.abc import Callable

from models.evaluation import ArchitectureResult
from models.project_spec import ProjectSpec
from services.engine.catalog import Catalog
from services.guides import hetzner

ParamBuilder = Callable[[ArchitectureResult, ProjectSpec, Catalog], dict[str, str]]

# arch_id -> (constructeur de paramètres, paramètres autorisés dans le guide)
PARAM_BUILDERS: dict[str, tuple[ParamBuilder, frozenset[str]]] = {
    "hetzner_vps": (hetzner.build_params, hetzner.ALLOWED_PARAMS),
}