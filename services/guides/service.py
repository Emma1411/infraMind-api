from models.guide import GuideFallback, GuideResponse
from models.project_spec import ProjectSpec
from services.engine.architectures import get_architectures
from services.engine.catalog import Catalog, get_catalog
from services.engine.evaluate import evaluate
from services.guides.loader import get_guides
from services.guides.registry import GUIDE_PROVIDERS
from services.guides.render import render_guide, youtube_search_url


class UnknownArchitecture(KeyError):
    """Identifiant d'architecture absent de la définition des architectures."""


def build_guide(arch_id: str, spec: ProjectSpec, catalog: Catalog | None = None) -> GuideResponse:
    catalog = catalog or get_catalog()
    arch = next((a for a in get_architectures() if a.id == arch_id), None)
    if arch is None:
        raise UnknownArchitecture(arch_id)

    guide = get_guides().get(arch_id)
    if guide is None:
        return GuideResponse(
            arch_id=arch_id,
            available=False,
            fallback=GuideFallback(
                message=(
                    f"Le guide pas à pas pour « {arch.label} » n'est pas encore disponible. "
                    "Cherche un tutoriel vidéo ou la documentation officielle du fournisseur."
                ),
                youtube_url=youtube_search_url(f"{arch.label} déployer une application tutoriel"),
            ),
        )

    result = evaluate(spec, catalog=catalog, with_sensitivity=False)
    architecture = next(r for r in result.ranking if r.id == arch_id)
    provider = GUIDE_PROVIDERS[arch_id]
    params = provider.build_params(architecture, spec, catalog)
    flags = provider.build_flags(spec)
    return GuideResponse(arch_id=arch_id, available=True, guide=render_guide(guide, params, flags))