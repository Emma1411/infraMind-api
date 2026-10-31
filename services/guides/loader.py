from functools import lru_cache
from pathlib import Path

from models.guide import GuideDef
from services.guides.registry import PARAM_BUILDERS
from services.guides.render import placeholders_in

GUIDES_DIR = Path(__file__).resolve().parents[2] / "data" / "guides"


@lru_cache
def get_guides() -> dict[str, GuideDef]:
    guides: dict[str, GuideDef] = {}
    for path in sorted(GUIDES_DIR.glob("*.json")):
        guide = GuideDef.model_validate_json(path.read_text(encoding="utf-8"))
        if guide.arch_id != path.stem:
            raise ValueError(f"{path.name} : arch_id doit être « {path.stem} »")
        if guide.arch_id not in PARAM_BUILDERS:
            raise ValueError(f"{guide.arch_id} : aucun constructeur de paramètres")
        _, allowed = PARAM_BUILDERS[guide.arch_id]
        unknown = placeholders_in(guide.model_dump_json()) - allowed
        if unknown:
            raise ValueError(f"{path.name} : paramètres inconnus {sorted(unknown)}")
        guides[guide.arch_id] = guide
    return guides