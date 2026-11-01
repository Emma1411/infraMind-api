import re
from typing import Any
from urllib.parse import quote_plus

from models.guide import GuideDef, RenderedGuide

# Les clés peuvent contenir des chiffres (par exemple ipv4_cost)
PLACEHOLDER = re.compile(r"\[\[([a-z0-9_]+)\]\]")
ANY_DOUBLE_BRACKET = re.compile(r"\[\[[^\]]*\]\]")


class GuideRenderError(ValueError):
    """Un paramètre du guide est inconnu ou non fourni."""


def youtube_search_url(query: str) -> str:
    return "https://www.youtube.com/results?search_query=" + quote_plus(query)


def placeholders_in(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def malformed_placeholders(text: str) -> set[str]:
    """Tout [[...]] qui ne respecte pas la syntaxe stricte : il ne serait jamais remplacé."""
    return {found for found in ANY_DOUBLE_BRACKET.findall(text) if not PLACEHOLDER.fullmatch(found)}


def _substitute(value: Any, params: dict[str, str]) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in params:
                raise GuideRenderError(f"Paramètre manquant : {key}")
            return params[key]

        return PLACEHOLDER.sub(replace, value)
    if isinstance(value, list):
        return [_substitute(item, params) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, params) for key, item in value.items()}
    return value


def render_guide(guide: GuideDef, params: dict[str, str], flags: frozenset[str] = frozenset()) -> RenderedGuide:
    data = guide.model_dump(mode="json")

    # Les étapes conditionnelles dont la condition n'est pas remplie disparaissent
    for key in ("steps", "cleanup"):
        data[key] = [step for step in data[key] if step["only_if"] is None or step["only_if"] in flags]

    data = _substitute(data, params)

    for step in data["steps"] + data["cleanup"]:
        step["help"]["youtube_url"] = youtube_search_url(step["help"]["search_query"])

    if data["tested_on"]:
        status = f"Testé en réel le {data['tested_on']}"
    else:
        status = (
            f"Rédigé d'après la documentation officielle consultée le {data['written_from_docs_on']} · "
            "pas encore testé en réel"
        )

    return RenderedGuide.model_validate({**data, "parameters": params, "status_label": status})