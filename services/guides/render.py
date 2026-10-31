
import re
from typing import Any
from urllib.parse import quote_plus

from models.guide import GuideDef, RenderedGuide

PLACEHOLDER = re.compile(r"\[\[([a-zA-Z0-9_]+)\]\]")

ALLOWED_PARAMS = frozenset({
    "server_type",
    "vcpu",
    "ram_gb",
    "disk_gb",
    "location",
    "app_slug",
    "monthly_total",
    "backup_cost",
    "ipv4_cost",
    "included_traffic",
    "extra_traffic",
})


class GuideRenderError(ValueError):
    """Un paramètre du guide est inconnu ou non fourni."""


def youtube_search_url(query: str) -> str:
    return (
        "https://www.youtube.com/results?search_query="
        + quote_plus(query)
    )


def placeholders_in(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def _substitute(value: Any, params: dict[str, str]) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)

            if key not in ALLOWED_PARAMS:
                raise GuideRenderError(
                    f"Placeholder non autorisé : {key}"
                )

            if key not in params:
                raise GuideRenderError(
                    f"Paramètre manquant : {key}"
                )

            return str(params[key])

        return PLACEHOLDER.sub(replace, value)

    if isinstance(value, list):
        return [
            _substitute(item, params)
            for item in value
        ]

    if isinstance(value, dict):
        return {
            key: _substitute(item, params)
            for key, item in value.items()
        }

    return value


def validate_rendered_guide(guide: RenderedGuide) -> RenderedGuide:
    serialized = guide.model_dump_json()

    remaining = PLACEHOLDER.findall(serialized)

    if remaining:
        raise GuideRenderError(
            f"Placeholders non remplacés : {sorted(set(remaining))}"
        )

    return guide


def render_guide(
    guide: GuideDef,
    params: dict[str, str]
) -> RenderedGuide:

    # 1. Remplacer les placeholders dans toutes les données
    data = _substitute(
        guide.model_dump(mode="json"),
        params
    )

    # 2. Générer les liens YouTube
    for step in data["steps"] + data["cleanup"]:
        step["help"]["youtube_url"] = youtube_search_url(
            step["help"]["search_query"]
        )

    # 3. Générer le statut
    if data["tested_on"]:
        status = f"Testé en réel le {data['tested_on']}"
    else:
        status = (
            f"Rédigé d'après la documentation officielle consultée "
            f"le {data['written_from_docs_on']} · "
            "pas encore testé en réel"
        )

    # 4. Construire le guide final
    rendered = RenderedGuide.model_validate({
        **data,
        "parameters": params,
        "status_label": status
    })

    # 5. Vérifier qu'aucun placeholder ne reste
    return validate_rendered_guide(rendered)
