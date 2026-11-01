from functools import lru_cache
from pathlib import Path

from models.guide import GuideDef
from services.guides.registry import GUIDE_PROVIDERS
from services.guides.render import malformed_placeholders, placeholders_in

GUIDES_DIR = Path(__file__).resolve().parents[2] / "data" / "guides"


@lru_cache
def get_guides() -> dict[str, GuideDef]:
    guides: dict[str, GuideDef] = {}
    for path in sorted(GUIDES_DIR.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        malformed = malformed_placeholders(raw)
        if malformed:
            raise ValueError(f"{path.name} : paramètres mal formés {sorted(malformed)}")

        guide = GuideDef.model_validate_json(raw)
        if guide.arch_id != path.stem:
            raise ValueError(f"{path.name} : arch_id doit être « {path.stem} »")
        if guide.arch_id not in GUIDE_PROVIDERS:
            raise ValueError(f"{guide.arch_id} : aucun fournisseur de paramètres")

        allowed = GUIDE_PROVIDERS[guide.arch_id].allowed_params
        unknown = placeholders_in(guide.model_dump_json()) - allowed
        if unknown:
            raise ValueError(f"{path.name} : paramètres inconnus {sorted(unknown)}")
        guides[guide.arch_id] = guide
    return guides