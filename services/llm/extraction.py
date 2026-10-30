from typing import Any
from pydantic import ValidationError
from config.settings import get_settings
from models.project_spec import ProjectSpec
from services.llm.client import get_llm_client
from services.llm.prompts.extraction import EXTRACTION_SYSTEM_PROMPT

MAX_ATTEMPTS = 2  # un appel + une seule correction


class ExtractionError(Exception):
    """L'IA n'a pas produit un JSON exploitable."""


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err["loc"]) or "racine"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


async def extract_spec(text: str, client: Any = None) -> ProjectSpec:
    settings = get_settings()
    client = client or get_llm_client()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    last_error = "réponse vide"

    for _ in range(MAX_ATTEMPTS):
        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1500,
        )
        content = response.choices[0].message.content or ""
        try:
            spec = ProjectSpec.model_validate_json(content)
        except ValidationError as exc:
            last_error = _summarize(exc)
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Ce json est invalide ({last_error}). Corrige-le : valeurs autorisées "
                        "uniquement, null si inconnu. Réponds uniquement avec le json."
                    ),
                }
            )
            continue

        spec.unknown = []  # seul l'utilisateur peut répondre « je ne sais pas »
        return spec

    raise ExtractionError(last_error)